# Supabase keepalive — weekly ping so free projects are not paused.
SERVICE_NAME = supabase-keepalive
TIMER_NAME   = $(SERVICE_NAME).timer
USER         = $(shell whoami)
PATH_VAL     = $(shell echo $$PATH)
CURR_DIR     = $(shell pwd)
PYTHON_BIN  ?= $(shell which python3 2>/dev/null || echo /usr/bin/python3)

# `make start` promises a ping inside this many days, however long the timer
# has been installed and whatever the machine was doing on Sunday morning.
MAX_AGE_DAYS ?= 7

.PHONY: help install upgrade setup env-setup start stop restart status logs clean \
        ping ping-if-stale list check \
        systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

help:
	@echo "Supabase keepalive — weekly ping for free-tier projects"
	@echo "======================================================="
	@echo "  make install   - Check prerequisites (stdlib Python only)"
	@echo "  make start     - Install and enable the weekly timer, then ping if overdue"
	@echo "  make status    - Timer schedule, last run, and every project's last success"
	@echo "  make logs      - Recent runs from the journal"
	@echo "  make upgrade   - Reinstall the units from the templates and restart the timer"
	@echo "  make stop      - Stop, disable and remove the timer and its unit"
	@echo ""
	@echo "  make ping          - Ping every project right now"
	@echo "  make ping-if-stale - Ping only if the last success is over $(MAX_AGE_DAYS) days old"
	@echo "  make list          - Show which projects would be pinged"
	@echo "  make check         - Exit non-zero if no ping succeeded in the last week"

# Installing the timer must not hinge on the ping: a project list that is not
# filled in yet is a configuration message, not a failed installation.
start: env-setup systemd-setup
	@$(MAKE) --no-print-directory ping-if-stale || \
		echo "[WARN] Timer installed, but no ping was made — see the message above (usually .env)."
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@echo "Checking prerequisites..."
	@$(PYTHON_BIN) --version >/dev/null 2>&1 || { echo "[ERR] python3 not found"; exit 1; }
	@echo "[OK] $(shell $(PYTHON_BIN) --version) — no third-party packages needed."
	@$(MAKE) --no-print-directory env-setup

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example — put your Supabase access token in it."; \
	fi

setup: install

# ----------------------------------------------------------------- pinging

ping:
	@$(PYTHON_BIN) keepalive.py ping

ping-if-stale:
	@$(PYTHON_BIN) keepalive.py ping --if-stale --max-age-days $(MAX_AGE_DAYS)

list:
	@$(PYTHON_BIN) keepalive.py list

check:
	@$(PYTHON_BIN) keepalive.py status

# ------------------------------------------------------------------ systemd

systemd-setup: env-setup
	@echo "Generating systemd units..."
	@for unit in $(SERVICE_NAME).service $(SERVICE_NAME).timer; do \
		sed -e "s|{{USER}}|$(USER)|g" \
		    -e "s|{{CURR_DIR}}|$(CURR_DIR)|g" \
		    -e "s|{{PATH_VAL}}|$(PATH_VAL)|g" \
		    -e "s|{{PYTHON_BIN}}|$(PYTHON_BIN)|g" \
		    $$unit.template > $$unit; \
	done
	@if sudo -n true 2>/dev/null; then \
		echo "Installing as system units via sudo..."; \
		sudo mv $(SERVICE_NAME).service $(SERVICE_NAME).timer /etc/systemd/system/; \
		sudo systemctl daemon-reload; \
		sudo systemctl enable --now $(TIMER_NAME); \
	else \
		echo "Installing as user units (~/.config/systemd/user)..."; \
		mkdir -p ~/.config/systemd/user; \
		mv $(SERVICE_NAME).service $(SERVICE_NAME).timer ~/.config/systemd/user/; \
		systemctl --user daemon-reload; \
		systemctl --user enable --now $(TIMER_NAME); \
		loginctl enable-linger $(USER) >/dev/null 2>&1 || \
			echo "[WARN] could not enable lingering; the timer only runs while you are logged in."; \
	fi
	@echo "[OK] Weekly timer installed."

systemd-stop:
	@echo "Stopping timer..."
	-@if systemctl --user list-unit-files $(TIMER_NAME) >/dev/null 2>&1; then \
		systemctl --user disable --now $(TIMER_NAME) 2>/dev/null; \
		rm -f ~/.config/systemd/user/$(SERVICE_NAME).service ~/.config/systemd/user/$(TIMER_NAME); \
		systemctl --user daemon-reload; \
	fi
	-@if sudo -n true 2>/dev/null; then \
		sudo systemctl disable --now $(TIMER_NAME) 2>/dev/null; \
		sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service /etc/systemd/system/$(TIMER_NAME); \
		sudo systemctl daemon-reload; \
	fi
	@echo "[OK] Timer stopped and unit files removed."

systemd-restart:
	@if systemctl --user list-unit-files $(TIMER_NAME) >/dev/null 2>&1; then \
		systemctl --user restart $(TIMER_NAME); \
	else \
		sudo systemctl restart $(TIMER_NAME); \
	fi

systemd-status:
	@echo "=== Timer ==="
	@if systemctl --user list-unit-files $(TIMER_NAME) >/dev/null 2>&1; then \
		systemctl --user list-timers $(TIMER_NAME) --all --no-pager; \
		systemctl --user status $(TIMER_NAME) --no-pager | head -12; \
	elif sudo -n true 2>/dev/null; then \
		sudo systemctl list-timers $(TIMER_NAME) --all --no-pager; \
		sudo systemctl status $(TIMER_NAME) --no-pager | head -12; \
	else \
		echo "[INFO] '$(TIMER_NAME)' is not installed."; \
	fi
	@echo ""
	@echo "=== Last run ==="
	@$(PYTHON_BIN) keepalive.py status || true

systemd-logs:
	@if systemctl --user list-unit-files $(TIMER_NAME) >/dev/null 2>&1; then \
		journalctl --user -u $(SERVICE_NAME) -n 50 --no-pager; \
	else \
		sudo journalctl -u $(SERVICE_NAME) -n 50 --no-pager; \
	fi

upgrade: systemd-setup
	@echo "[OK] Units regenerated from the templates."
	@$(MAKE) --no-print-directory ping-if-stale
