# services/common.mk - the systemd block every native service Makefile used
# to copy by hand (systemd-setup/-stop/-status/-restart/-logs). See ticket
# homelab-0017 and AGENTS.md section 2.
#
# A service Makefile sets SERVICE_NAME (and, unless it renders its own unit,
# UNIT_TEMPLATE and optionally UNIT_SED), then includes this file:
#
#   SERVICE_NAME = aicli-ai
#   UNIT_TEMPLATE = aicli.service.template
#   UNIT_SED = -e "s|{{PYTHON_BIN}}|$(PYTHON_BIN)|g"
#   include $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../../common.mk
#
# `SERVICE_NAME = ...` must stay a plain line in the service Makefile -
# services/AI/Makefile's `summary`/`verify` read it with sed.
#
# Scope (system vs. user) is picked inside each recipe by calling
# `sudo -n true`, never at parse time - so `make -n` and `make help` never
# shell out to sudo or systemctl. Every `sudo` call below is `sudo -n`, or
# sits inside a shell conditional that already tested `sudo -n true`.

# The directory of the Makefile that *included* common.mk, not the caller's
# cwd - MAKEFILE_LIST's first entry is always that top Makefile (make -C
# chdirs there first; make -f leaves it relative to the invocation dir, which
# abspath resolves against the same CURDIR), so both invocations land renders
# and installs in the service's own directory. `?=` lets a service keep its
# own longer-standing definition (e.g. services/status) unchanged.
CURR_DIR ?= $(patsubst %/,%,$(dir $(abspath $(firstword $(MAKEFILE_LIST)))))
USER ?= $(shell whoami)
HOME_DIR ?= $(HOME)
PATH_VAL ?= $(shell echo $$PATH)

# Overridable (tests point these at a sandbox so nothing real ever gets
# touched; services/tests/test_common_mk.sh does exactly that).
SYSTEM_UNIT_DIR ?= /etc/systemd/system
USER_UNIT_DIR ?= $(HOME_DIR)/.config/systemd/user

.PHONY: systemd-setup systemd-stop systemd-status systemd-restart systemd-logs systemd-restart-if-installed \
	timer-setup timer-stop timer-status timer-restart timer-logs

# ------------------------------------------------------------- service --- #
# SERVICE_NAME/UNIT_TEMPLATE/UNIT_SED drive these. A service whose unit needs
# shell logic to render (playwrightMcpAI reads its env file to build flags)
# simply does not set UNIT_TEMPLATE and defines its own systemd-render
# instead - guarding the default recipe on `ifdef UNIT_TEMPLATE` means make
# never sees two recipes for the same target, so there is no "overriding
# recipe" warning.
ifdef UNIT_TEMPLATE
systemd-render:
	@USER_LINE="User=$(USER)"; \
	if ! sudo -n true 2>/dev/null; then USER_LINE=""; fi; \
	sed -e "s|{{USER_LINE}}|$$USER_LINE|g" \
	    -e "s|{{CURR_DIR}}|$(CURR_DIR)|g" \
	    -e "s|{{PATH_VAL}}|$(PATH_VAL)|g" \
	    -e "s|{{HOME_DIR}}|$(HOME_DIR)|g" \
	    -e "s|{{USER}}|$(USER)|g" \
	    $(UNIT_SED) \
	    $(CURR_DIR)/$(UNIT_TEMPLATE) > $(CURR_DIR)/$(SERVICE_NAME).service
endif

# Depends on env-setup (defined by the service Makefile) and systemd-render
# (above, or the service's own). Installs, then daemon-reload/enable/restart
# - restart, not start, so a unit file change takes effect on a running
# service. Refuses outright if the unit is already installed in the other
# scope, so a flipped `sudo -n` never creates a second copy fighting for the
# same port.
systemd-setup: env-setup systemd-render
	@if sudo -n true 2>/dev/null; then \
		if [ -f $(USER_UNIT_DIR)/$(SERVICE_NAME).service ]; then \
			echo "[ERROR] $(SERVICE_NAME) is already installed as a user unit ($(USER_UNIT_DIR)/$(SERVICE_NAME).service). Run 'make stop' there first."; \
			exit 1; \
		fi; \
		echo "Installing as system service via sudo..."; \
		sudo mv $(CURR_DIR)/$(SERVICE_NAME).service $(SYSTEM_UNIT_DIR)/; \
		sudo systemctl daemon-reload; \
		sudo systemctl enable $(SERVICE_NAME); \
		sudo systemctl restart $(SERVICE_NAME); \
		echo "[OK] Service $(SERVICE_NAME) started (system scope)."; \
	else \
		if [ -f $(SYSTEM_UNIT_DIR)/$(SERVICE_NAME).service ]; then \
			echo "[ERROR] $(SERVICE_NAME) is already installed as a system unit ($(SYSTEM_UNIT_DIR)/$(SERVICE_NAME).service). Remove it there first (needs sudo)."; \
			exit 1; \
		fi; \
		echo "Installing as user systemd service ($(USER_UNIT_DIR))..."; \
		mkdir -p $(USER_UNIT_DIR); \
		mv $(CURR_DIR)/$(SERVICE_NAME).service $(USER_UNIT_DIR)/; \
		systemctl --user daemon-reload; \
		systemctl --user enable $(SERVICE_NAME); \
		systemctl --user restart $(SERVICE_NAME); \
		loginctl enable-linger $(USER) >/dev/null 2>&1 || true; \
		echo "[OK] Service $(SERVICE_NAME) started (user scope)."; \
	fi

systemd-stop:
	@echo "Stopping service..."
	-@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null || systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user stop $(SERVICE_NAME); \
		systemctl --user disable $(SERVICE_NAME); \
		rm -f $(USER_UNIT_DIR)/$(SERVICE_NAME).service; \
		systemctl --user daemon-reload; \
	fi
	-@if sudo -n true 2>/dev/null; then \
		sudo systemctl stop $(SERVICE_NAME) 2>/dev/null; \
		sudo systemctl disable $(SERVICE_NAME) 2>/dev/null; \
		sudo rm -f $(SYSTEM_UNIT_DIR)/$(SERVICE_NAME).service; \
		sudo systemctl daemon-reload; \
	fi
	@echo "[OK] Service stopped and unit file removed."

systemd-status:
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null || systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user status $(SERVICE_NAME) --no-pager; \
	elif sudo -n true 2>/dev/null; then \
		sudo systemctl status $(SERVICE_NAME) --no-pager; \
	else \
		systemctl --user status $(SERVICE_NAME) --no-pager 2>/dev/null || echo "[INFO] Service '$(SERVICE_NAME)' is not running. Run 'make start' to launch it."; \
	fi

# A crashed user unit is "failed", not "active", but still enabled - test
# is-enabled, and never let the system-scope fallback wait on a password (the
# weekly cron has no tty).
systemd-restart:
	@if systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user restart $(SERVICE_NAME); \
	else \
		sudo -n systemctl restart $(SERVICE_NAME); \
	fi

systemd-logs:
	@if systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		journalctl --user -u $(SERVICE_NAME) -n 30 -f; \
	else \
		sudo -n journalctl -u $(SERVICE_NAME) -n 30 -f; \
	fi

# For `upgrade` recipes: restart the unit if it is enabled in either scope,
# do nothing (exit 0) if it is not installed at all. Reading system-scope
# is-enabled needs no sudo (unit files under /etc/systemd/system are world
# readable); only the restart itself is sudo -n.
systemd-restart-if-installed:
	@if systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user restart $(SERVICE_NAME); \
	elif systemctl is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		sudo -n systemctl restart $(SERVICE_NAME); \
	fi
