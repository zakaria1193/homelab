# OpenHands AI Service Automation Makefile
SERVICE_NAME = openhands-ai
UNIT_TEMPLATE = openhands-ai.service.template
OPENHANDS_HOST ?= 0.0.0.0
OPENHANDS_PORT ?= 3030
UV_BIN ?= $(shell which uv 2>/dev/null || echo /home/zfadli/.local/bin/uv)
UNIT_SED = -e "s|{{OPENHANDS_HOST}}|$(OPENHANDS_HOST)|g" \
	   -e "s|{{OPENHANDS_PORT}}|$(OPENHANDS_PORT)|g"
include $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../../common.mk

.PHONY: help install upgrade setup env-setup start stop restart status logs clean print-units

print-units:
	@echo $(SERVICE_NAME)

help:
	@echo "OpenHands AI Service Automation"
	@echo "==============================="
	@echo "  make install   - Install @openhands/agent-canvas and openhands-ai dependencies"
	@echo "  make start     - Start OpenHands Agent Canvas Web UI on http://0.0.0.0:$(OPENHANDS_PORT)"
	@echo "  make status    - Check systemd service status"
	@echo "  make logs      - View live systemd logs"
	@echo "  make upgrade   - Upgrade @openhands/agent-canvas and openhands-ai packages"
	@echo "  make stop      - Stop the background service daemon and clean up"

# Streamlined user aliases
start: env-setup systemd-setup
	@echo "[OK] OpenHands AI Web UI started on http://$(OPENHANDS_HOST):$(OPENHANDS_PORT)"
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@echo "Installing @openhands/agent-canvas globally..."
	npm install -g @openhands/agent-canvas@latest
	@echo "Creating virtual environment and installing openhands-ai..."
	@if [ ! -d venv ]; then \
		if [ -f "$(UV_BIN)" ]; then \
			$(UV_BIN) venv venv; \
		else \
			python3 -m venv venv; \
		fi \
	fi
	@if [ -f "$(UV_BIN)" ]; then \
		$(UV_BIN) pip install --python venv/bin/python openhands-ai; \
	else \
		venv/bin/pip install openhands-ai; \
	fi
	@echo "[OK] Installation complete."

upgrade:
	@echo "Upgrading @openhands/agent-canvas..."
	npm install -g @openhands/agent-canvas@latest
	@echo "Upgrading openhands-ai..."
	@if [ -f "$(UV_BIN)" ]; then \
		$(UV_BIN) pip install --python venv/bin/python -U openhands-ai; \
	else \
		venv/bin/pip install -U openhands-ai; \
	fi
	@$(MAKE) --no-print-directory systemd-restart-if-installed
	@echo "[OK] Upgrade complete."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi

setup: env-setup install
	@echo "OpenHands AI environment setup completed."
