# arr-mcp AI Service Automation Makefile
SERVICE_NAME = arr-mcp-backend
UNIT_TEMPLATE = arr-mcp-backend.service.template
UV_BIN ?= $(shell which uv 2>/dev/null || echo /home/zfadli/.local/bin/uv)
UNIT_SED = -e "s|{{UV_BIN}}|$(UV_BIN)|g"
include $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../../common.mk

ROOT = $(abspath $(CURR_DIR)/../../..)

.PHONY: help install upgrade setup env-setup start stop restart status logs clean test test-tokens print-units

print-units:
	@echo $(SERVICE_NAME)

help:
	@echo "arr-mcp AI Service Automation"
	@echo "==============================="
	@echo "  make install   - Install backend dependencies (uv sync)"
	@echo "  make start     - Start backend (SSE MCP) via systemd"
	@echo "  make status    - Check status of backend service"
	@echo "  make logs      - View live logs of backend service"
	@echo "  make upgrade   - Pull latest changes and update dependencies"
	@echo "  make stop      - Stop backend service and clean up systemd files"

# Streamlined user aliases
start: env-setup systemd-setup
	@echo "Backend (SSE MCP): Port 10938"
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

# `make test` stays offline: agents run it unattended, and these tokens are
# home-IP restricted or rate limited. The live check is `make test-tokens`.
test:
	@echo "No offline tests here; the live credential check is 'make test-tokens'."

test-tokens: env-setup
	@python3 $(ROOT)/services/status/test_tokens.py --env $(CURR_DIR)/.env --strict

install:
	@echo "Installing backend dependencies using uv..."
	@cd arr-mcp && $(UV_BIN) sync --no-dev
	@echo "[OK] Installation complete."

upgrade:
	@echo "Pulling latest changes for arr-mcp..."
	@cd arr-mcp && \
		if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$$(git ls-files --others --exclude-standard)" ]; then \
			echo "[WARN] Local changes in arr-mcp checkout; stashing before pull..."; \
			git stash push -u -m "arr-mcp upgrade auto-stash $$(date -Iseconds)"; \
			stashed=1; \
		else \
			stashed=0; \
		fi; \
		git pull; \
		if [ "$$stashed" = "1" ]; then \
			echo "[INFO] Restoring stashed local changes..."; \
			git stash pop || echo "[WARN] Could not auto-restore stash; run 'git stash list' in arr-mcp/ to recover it."; \
		fi
	@echo "Upgrading backend dependencies..."
	@cd arr-mcp && $(UV_BIN) sync --no-dev
	@echo "Restarting service..."
	@$(MAKE) restart
	@echo "[OK] Upgrade complete."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi

setup: env-setup install
	@echo "arr-mcp setup completed."
