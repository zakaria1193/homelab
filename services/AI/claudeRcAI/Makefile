# Claude Remote Control (`claude rc`) Service Automation Makefile
#
# One `claude remote-control` process serves exactly one directory, so a second
# always-on workspace means a second instance. Pass INSTANCE=<name> to every
# target to act on it:
#
#   make start                     -> claude-rc-ai            reading .env
#   make start INSTANCE=paperclip  -> claude-rc-ai-paperclip  reading .env.paperclip
#
# Instances are otherwise identical - same targets, same unit layout - so
# adding a workspace is a new .env.<name>, never a new Makefile.
INSTANCE ?=
SUFFIX := $(if $(INSTANCE),-$(INSTANCE),)
SERVICE_NAME = claude-rc-ai$(SUFFIX)
ENV_FILE := .env$(if $(INSTANCE),.$(INSTANCE),)
USER = $(shell whoami)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(shell pwd)

# Local overrides live in $(ENV_FILE) (RC_* keys only - no secrets here, Remote
# Control authenticates with the credentials already stored in ~/.claude).
#
# Seed it here rather than from the env-setup recipe: make expands `include` at
# parse time, so a file created by a recipe would arrive one run too late and
# the unit would be generated from the defaults instead.
$(shell test -f $(ENV_FILE) || cp $(ENV_FILE).example $(ENV_FILE) 2>/dev/null)
-include $(ENV_FILE)

# Repository the Remote Control server runs in (defaults to this repo's root).
RC_WORKDIR ?= $(abspath $(CURR_DIR)/../../..)
RC_SPAWN_MODE ?= worktree
RC_CAPACITY ?= 32
RC_PERMISSION_MODE ?= auto
RC_SESSION_PREFIX ?= homelab
RC_SESSION_NAME ?= homelab
# Optional: path for verbose Remote Control debug logs (stdout is discarded, see below).
RC_DEBUG_FILE ?=
CLAUDE_BIN ?= $(shell which claude 2>/dev/null || echo $(HOME_DIR)/.local/bin/claude)
SHELL_BIN ?= $(shell getent passwd $(USER) | cut -d: -f7)

RC_DEBUG_ARG = $(if $(strip $(RC_DEBUG_FILE)),--debug-file $(strip $(RC_DEBUG_FILE)),)
RC_ARGS = remote-control --spawn $(RC_SPAWN_MODE) --capacity $(RC_CAPACITY) \
	--permission-mode $(RC_PERMISSION_MODE) --name $(RC_SESSION_NAME) \
	--remote-control-session-name-prefix $(RC_SESSION_PREFIX) --create-session-in-dir $(RC_DEBUG_ARG)

.PHONY: help install upgrade setup env-setup start stop restart status logs clean \
	systemd-setup systemd-stop systemd-status systemd-restart systemd-logs doctor

help:
	@echo "Claude Remote Control AI Service Automation"
	@echo "==========================================="
	@echo "  make install   - Install / repair the Claude Code native CLI"
	@echo "  make start     - Run 'claude remote-control' continuously in $(RC_WORKDIR)"
	@echo "  make status    - Check systemd service status"
	@echo "  make logs      - View live systemd logs"
	@echo "  make upgrade   - Upgrade the Claude Code CLI and restart the daemon"
	@echo "  make stop      - Stop the daemon and remove the systemd unit"
	@echo ""
	@echo "  Instance:   $(SERVICE_NAME)  (INSTANCE=$(INSTANCE), env $(ENV_FILE))"
	@echo "  Workspace:  $(RC_WORKDIR)"
	@echo "  Spawn mode: $(RC_SPAWN_MODE)  |  Capacity: $(RC_CAPACITY)  |  Permissions: $(RC_PERMISSION_MODE)"
	@echo ""
	@echo "  Instances here:  (default) $(patsubst .env.%,%,$(filter-out %.example,$(wildcard .env.*)))"
	@echo "  Connect from https://claude.ai/code or the Claude mobile app."

# Streamlined user aliases
start: env-setup systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@echo "Installing / verifying the Claude Code native CLI..."
	@if command -v claude >/dev/null 2>&1; then \
		claude install stable; \
	else \
		curl -fsSL https://claude.ai/install.sh | bash; \
	fi
	@echo "[OK] Installation complete: $$($(CLAUDE_BIN) --version 2>/dev/null || echo 'claude not on PATH')"

upgrade:
	@echo "Upgrading the Claude Code CLI..."
	-@$(CLAUDE_BIN) update
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user restart $(SERVICE_NAME); \
	elif sudo -n true 2>/dev/null && sudo systemctl is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		sudo systemctl restart $(SERVICE_NAME); \
	fi
	@echo "[OK] Upgrade complete."

# The file itself is seeded at parse time (see above); this target only reports
# and fails loudly when there is no template to seed it from.
env-setup:
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "[ERROR] no $(ENV_FILE) and no $(ENV_FILE).example to create it from."; \
		echo "        For a new instance, write .env.<name>.example first."; \
		exit 1; \
	fi
	@echo "Using $(ENV_FILE) (workspace $(RC_WORKDIR), spawn $(RC_SPAWN_MODE))"

setup: env-setup install

doctor:
	@echo "Workspace: $(RC_WORKDIR)"
	@$(CLAUDE_BIN) doctor || true

systemd-setup: env-setup
	@echo "Creating systemd service file for $(SERVICE_NAME)..."
	@if [ "$(RC_SPAWN_MODE)" = "worktree" ] && [ ! -d "$(RC_WORKDIR)/.git" ]; then \
		echo "[ERROR] $(RC_WORKDIR) is not a git repository; '--spawn worktree' requires one."; \
		echo "        Use RC_SPAWN_MODE=same-dir for a workspace that is not its own repo."; \
		exit 1; \
	fi
	@mkdir -p ~/.config/systemd/user
	@echo "[Unit]" > $(SERVICE_NAME).service
	@echo "Description=Claude Code Remote Control server for $(RC_WORKDIR)" >> $(SERVICE_NAME).service
	@echo "After=network.target network-online.target" >> $(SERVICE_NAME).service
	@echo "Wants=network-online.target" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Service]" >> $(SERVICE_NAME).service
	@echo "Type=simple" >> $(SERVICE_NAME).service
	@echo "WorkingDirectory=$(RC_WORKDIR)" >> $(SERVICE_NAME).service
	@echo "Environment=\"HOME=$(HOME_DIR)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"SHELL=$(SHELL_BIN)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"PATH=$(PATH_VAL)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"CLAUDE_REMOTE_CONTROL_SESSION_NAME_PREFIX=$(RC_SESSION_PREFIX)\"" >> $(SERVICE_NAME).service
	@echo "EnvironmentFile=-$(CURR_DIR)/$(ENV_FILE)" >> $(SERVICE_NAME).service
	@echo "ExecStart=$(CLAUDE_BIN) $(RC_ARGS)" >> $(SERVICE_NAME).service
	@echo "StandardOutput=null" >> $(SERVICE_NAME).service
	@echo "StandardError=journal" >> $(SERVICE_NAME).service
	@echo "Restart=always" >> $(SERVICE_NAME).service
	@echo "RestartSec=15" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Install]" >> $(SERVICE_NAME).service
	@echo "WantedBy=default.target multi-user.target" >> $(SERVICE_NAME).service
	@if sudo -n true 2>/dev/null; then \
		echo "Installing as system service via sudo..."; \
		sudo sed -i '/^\[Service\]/a User=$(USER)' $(SERVICE_NAME).service; \
		sudo mv $(SERVICE_NAME).service /etc/systemd/system/; \
		sudo systemctl daemon-reload; \
		sudo systemctl enable $(SERVICE_NAME); \
		sudo systemctl restart $(SERVICE_NAME); \
	else \
		echo "Installing as user systemd service (~/.config/systemd/user)..."; \
		mv $(SERVICE_NAME).service ~/.config/systemd/user/; \
		systemctl --user daemon-reload; \
		systemctl --user enable $(SERVICE_NAME); \
		systemctl --user restart $(SERVICE_NAME); \
		loginctl enable-linger $(USER) 2>/dev/null || true; \
	fi
	@echo "[OK] Remote Control running in $(RC_WORKDIR) (spawn=$(RC_SPAWN_MODE))."
	@echo "     Connect from https://claude.ai/code or the Claude mobile app."

systemd-stop:
	@echo "Stopping service..."
	-@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null || systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user stop $(SERVICE_NAME); \
		systemctl --user disable $(SERVICE_NAME); \
		rm -f ~/.config/systemd/user/$(SERVICE_NAME).service; \
		systemctl --user daemon-reload; \
	fi
	-@if sudo -n true 2>/dev/null; then \
		sudo systemctl stop $(SERVICE_NAME) 2>/dev/null; \
		sudo systemctl disable $(SERVICE_NAME) 2>/dev/null; \
		sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service; \
		sudo systemctl daemon-reload; \
	fi

systemd-status:
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null || systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user status $(SERVICE_NAME) --no-pager; \
	elif sudo -n true 2>/dev/null; then \
		sudo systemctl status $(SERVICE_NAME) --no-pager; \
	else \
		systemctl --user status $(SERVICE_NAME) --no-pager 2>/dev/null || echo "[INFO] Service '$(SERVICE_NAME)' is not running. Run 'make start' to launch it."; \
	fi

systemd-restart:
	@if systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user restart $(SERVICE_NAME); \
	else \
		sudo systemctl restart $(SERVICE_NAME); \
	fi

systemd-logs:
	@if systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		journalctl --user -u $(SERVICE_NAME) -n 30 -f; \
	else \
		sudo journalctl -u $(SERVICE_NAME) -n 30 -f; \
	fi
