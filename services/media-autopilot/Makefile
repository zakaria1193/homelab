# Media autopilot — monitor the next episodes you will watch, delete the ones you have.
SERVICE_NAME = media-autopilot
TIMER_NAME   = $(SERVICE_NAME).timer
USER         = $(shell whoami)
PATH_VAL     = $(shell echo $$PATH)
CURR_DIR     = $(shell pwd)
PYTHON_BIN  ?= $(shell which python3 2>/dev/null || echo /usr/bin/python3)
ROOT        := $(abspath $(CURR_DIR)/../..)

.PHONY: help install upgrade setup env-setup start stop restart status logs clean test test-tokens \
        run dry-run systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

help:
	@echo "Media autopilot — keeps 'what you watch + the next 2 episodes' on disk"
	@echo "======================================================================"
	@echo "  make install   - Check prerequisites (stdlib Python only)"
	@echo "  make start     - Install and enable the 5-minute timer"
	@echo "  make status    - Timer schedule and the last log lines"
	@echo "  make logs      - Recent runs from the journal"
	@echo "  make upgrade   - Reinstall the units from the templates"
	@echo "  make stop      - Stop, disable and remove the timer and its unit"
	@echo ""
	@echo "  make dry-run   - Show what a run would grab and delete, change nothing"
	@echo "  make run       - One real run now"
	@echo "  make test      - Run the test suite (no network)"

start: env-setup systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop
setup: install
upgrade: systemd-setup

install:
	@$(PYTHON_BIN) --version >/dev/null 2>&1 || { echo "[ERR] python3 not found"; exit 1; }
	@echo "[OK] $(shell $(PYTHON_BIN) --version) — no third-party packages needed."
	@$(MAKE) --no-print-directory env-setup

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example — put the Jellyfin API key in it."; \
	fi

run:
	@set -a; . ./.env; set +a; $(PYTHON_BIN) autopilot.py

dry-run:
	@set -a; . ./.env; set +a; $(PYTHON_BIN) autopilot.py --dry-run

test:
	@$(PYTHON_BIN) $(CURR_DIR)/tests/test_autopilot.py

test-tokens: env-setup
	@$(PYTHON_BIN) $(ROOT)/services/status/test_tokens.py --env $(ROOT)/services/media-autopilot/.env --strict

systemd-setup:
	@for unit in $(SERVICE_NAME).service $(SERVICE_NAME).timer; do \
		sed -e "s|{{USER}}|$(USER)|g" -e "s|{{CURR_DIR}}|$(CURR_DIR)|g" \
		    -e "s|{{PATH_VAL}}|$(PATH_VAL)|g" -e "s|{{PYTHON_BIN}}|$(PYTHON_BIN)|g" \
		    $$unit.template > $$unit; \
	done
	@if command sudo -n true 2>/dev/null; then \
		echo "Installing as system units via sudo..."; \
		command sudo mv $(SERVICE_NAME).service $(SERVICE_NAME).timer /etc/systemd/system/; \
		command sudo systemctl daemon-reload; \
		command sudo systemctl enable --now $(TIMER_NAME); \
	else \
		echo "Installing as user units (~/.config/systemd/user)..."; \
		mkdir -p ~/.config/systemd/user; \
		mv $(SERVICE_NAME).service $(SERVICE_NAME).timer ~/.config/systemd/user/; \
		systemctl --user daemon-reload; \
		systemctl --user enable --now $(TIMER_NAME); \
		loginctl enable-linger $(USER) >/dev/null 2>&1 || \
			echo "[WARN] could not enable lingering; the timer only runs while you are logged in."; \
	fi
	@echo "[OK] Autopilot timer installed."

systemd-stop:
	-@systemctl --user disable --now $(TIMER_NAME) 2>/dev/null; \
		rm -f ~/.config/systemd/user/$(SERVICE_NAME).service ~/.config/systemd/user/$(TIMER_NAME); \
		systemctl --user daemon-reload 2>/dev/null; true
	-@if command sudo -n true 2>/dev/null; then \
		command sudo systemctl disable --now $(TIMER_NAME) 2>/dev/null; \
		command sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service /etc/systemd/system/$(TIMER_NAME); \
		command sudo systemctl daemon-reload; \
	fi
	@echo "[OK] Timer stopped and unit files removed."

systemd-restart:
	@systemctl --user restart $(TIMER_NAME) 2>/dev/null || command sudo systemctl restart $(TIMER_NAME)

systemd-status:
	@systemctl list-timers $(TIMER_NAME) --no-pager; \
		systemctl --user list-timers $(TIMER_NAME) --no-pager 2>/dev/null | grep -i autopilot || true
	@tail -n 8 autopilot.log 2>/dev/null || echo "(no log yet)"

systemd-logs:
	@journalctl -u $(SERVICE_NAME) -n 50 --no-pager 2>/dev/null || journalctl --user -u $(SERVICE_NAME) -n 50 --no-pager
