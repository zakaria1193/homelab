# Supabase keepalive — ping twice a week so free projects are not paused.
SERVICE_NAME = supabase-keepalive
TIMER_UNIT   = $(SERVICE_NAME)
PYTHON_BIN  ?= $(shell which python3 2>/dev/null || echo /usr/bin/python3)
TIMER_SED    = -e "s|{{PYTHON_BIN}}|$(PYTHON_BIN)|g"
include $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../common.mk
ROOT        := $(abspath $(CURR_DIR)/../..)

# `make start` promises a ping inside this many days, however long the timer
# has been installed and whatever the machine was doing on Sunday morning.
MAX_AGE_DAYS ?= 7

.PHONY: help install upgrade setup env-setup start stop restart status logs clean test test-tokens \
        ping ping-if-stale list check

help:
	@echo "Supabase keepalive — twice-weekly ping for free-tier projects"
	@echo "======================================================="
	@echo "  make install   - Check prerequisites (stdlib Python only)"
	@echo "  make start     - Install and enable the timer, then ping if overdue"
	@echo "  make status    - Timer schedule, last run, and every project's last success"
	@echo "  make logs      - Recent runs from the journal"
	@echo "  make upgrade   - Reinstall the units from the templates and restart the timer"
	@echo "  make stop      - Stop, disable and remove the timer and its unit"
	@echo ""
	@echo "  make ping          - Ping every project right now"
	@echo "  make ping-if-stale - Ping only if the last success is over $(MAX_AGE_DAYS) days old"
	@echo "  make list          - Show which projects would be pinged"
	@echo "  make check         - Exit non-zero if no ping succeeded in the last week"
	@echo ""
	@echo "  make pause PROJECT=<name|ref>  - Skip a project from now on (also on /supabase)"
	@echo "  make resume PROJECT=<name|ref> - Put it back in the weekly ping"
	@echo "  make test          - Run the test suite (no network, no real project)"

# Installing the timer must not hinge on the ping: a project list that is not
# filled in yet is a configuration message, not a failed installation.
start: env-setup timer-setup
	@$(MAKE) --no-print-directory ping-if-stale || \
		echo "[WARN] Timer installed, but no ping was made — see the message above (usually .env)."
stop: timer-stop
restart: timer-restart
status: timer-status
	@echo ""
	@echo "=== Last run ==="
	@$(PYTHON_BIN) keepalive.py status || true
logs: timer-logs
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

test:
	@python3 $(CURR_DIR)/tests/test_keepalive.py

test-tokens: env-setup
	@$(PYTHON_BIN) $(ROOT)/services/status/test_tokens.py --env $(ROOT)/services/supabase-keepalive/.env --strict

pause:
	@test -n "$(PROJECT)" || { echo "usage: make pause PROJECT=<name|ref>"; exit 2; }
	@python3 $(CURR_DIR)/keepalive.py pause "$(PROJECT)"

resume:
	@test -n "$(PROJECT)" || { echo "usage: make resume PROJECT=<name|ref>"; exit 2; }
	@python3 $(CURR_DIR)/keepalive.py resume "$(PROJECT)"

list:
	@$(PYTHON_BIN) keepalive.py list

check:
	@$(PYTHON_BIN) keepalive.py status

upgrade: timer-setup
	@echo "[OK] Units regenerated from the templates."
	@$(MAKE) --no-print-directory ping-if-stale
