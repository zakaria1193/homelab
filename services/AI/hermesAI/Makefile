# Hermes AI Service Automation Makefile
SERVICE_NAME = hermes-ai
UNIT_TEMPLATE = hermes-ai.service.template
HERMES_HOME ?= $(HOME)/.hermes
DASHBOARD_HOST ?= 0.0.0.0
DASHBOARD_PORT ?= 8100
HERMES_PORT ?= 8101
HERMES_BIN ?= $(shell which hermes 2>/dev/null || echo $(HOME)/.local/bin/hermes)
HERMES_CMD ?= dashboard --no-open --host $(DASHBOARD_HOST) --port $(DASHBOARD_PORT) --skip-build
UNIT_SED = -e "s|{{HERMES_HOME}}|$(HERMES_HOME)|g" \
	   -e "s|{{DASHBOARD_PORT}}|$(DASHBOARD_PORT)|g" \
	   -e "s|{{HERMES_PORT}}|$(HERMES_PORT)|g" \
	   -e "s|{{HERMES_BIN}}|$(HERMES_BIN)|g" \
	   -e "s|{{HERMES_CMD}}|$(HERMES_CMD)|g"
include $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../../common.mk

.PHONY: help install upgrade setup env-setup start stop restart status logs clean print-units

# Bare unit name(s) this service owns, one per line. Read by services/AI's
# top-level Makefile to build its registry; must stay free of banners/echoes.
print-units:
	@echo $(SERVICE_NAME)

help:
	@echo "Hermes AI Service Automation"
	@echo "============================"
	@echo "  make install   - Install hermes-agent CLI"
	@echo "  make start     - Start Hermes daemon & web dashboard on http://localhost:$(DASHBOARD_PORT)"
	@echo "  make status    - Check daemon status"
	@echo "  make logs      - View live daemon logs"
	@echo "  make upgrade   - Upgrade hermes-agent CLI to latest version"
	@echo "  make stop      - Stop the background daemon and clean up"

# Streamlined user aliases
start: env-setup systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@echo "Installing Hermes Agent..."
	@if command -v curl >/dev/null 2>&1; then \
		curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash; \
	elif command -v uv >/dev/null 2>&1; then \
		uv tool install hermes-agent; \
	elif command -v pip3 >/dev/null 2>&1; then \
		pip3 install hermes-agent; \
	else \
		echo "Error: Neither curl, uv, nor pip3 found."; exit 1; \
	fi
	@echo "[OK] Installation complete."

upgrade:
	@echo "Upgrading Hermes Agent..."
	@if command -v curl >/dev/null 2>&1; then \
		curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash; \
	elif command -v uv >/dev/null 2>&1; then \
		uv tool install hermes-agent --force; \
	elif command -v pip3 >/dev/null 2>&1; then \
		pip3 install --upgrade hermes-agent; \
	else \
		echo "Error: Neither curl, uv, nor pip3 found."; exit 1; \
	fi
	@$(MAKE) --no-print-directory systemd-restart-if-installed
	@echo "[OK] Upgrade complete."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi

setup: env-setup
	@echo "Running interactive Hermes setup..."
	@if [ -f "$(HERMES_BIN)" ]; then \
		$(HERMES_BIN) setup; \
	elif command -v hermes >/dev/null 2>&1; then \
		hermes setup; \
	else \
		echo "Hermes binary not found. Run 'make install' first."; exit 1; \
	fi
