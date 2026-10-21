# Media autopilot — monitor the next episodes you will watch, delete the ones you have.
SERVICE_NAME = media-autopilot
TIMER_UNIT   = $(SERVICE_NAME)
PYTHON_BIN  ?= $(shell which python3 2>/dev/null || echo /usr/bin/python3)
TIMER_SED    = -e "s|{{PYTHON_BIN}}|$(PYTHON_BIN)|g"
include $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../common.mk
ROOT        := $(abspath $(CURR_DIR)/../..)

.PHONY: help install upgrade setup env-setup start stop restart status logs clean test test-tokens \
        run dry-run

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

start: env-setup timer-setup
stop: timer-stop
restart: timer-restart
status: timer-status
	@tail -n 8 autopilot.log 2>/dev/null || echo "(no log yet)"
logs: timer-logs
clean: stop
setup: install
upgrade: timer-setup

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

