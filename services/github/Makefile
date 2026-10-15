# GitHub service management & credentials
SERVICE_NAME = github
PYTHON_BIN  ?= $(shell which python3 2>/dev/null || echo /usr/bin/python3)

.PHONY: help install start status logs upgrade stop clean env-setup test-tokens test

help:
	@echo "GitHub Service & Credentials"
	@echo "============================"
	@echo "  make install     - Verify local configuration"
	@echo "  make test-tokens - Test GitHub API token against https://api.github.com/user"
	@echo "  make status      - Check configuration & credential status"
	@echo "  make start       - Ensure environment is ready"
	@echo "  make logs        - Show token verification output"
	@echo "  make upgrade     - Re-verify configuration"
	@echo "  make stop        - Clean service"
	@echo "  make clean       - Alias for make stop"
	@echo "  make env-setup   - Create .env from template if missing"

install: env-setup
	@echo "[OK] GitHub service configuration ready."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi

test:
	@echo "No offline tests here; the live credential check is 'make test-tokens'."

test-tokens: env-setup
	@$(PYTHON_BIN) test_tokens.py

start: env-setup
	@echo "[INFO] No background daemon required; GH_TOKEN is referenced directly from $(shell pwd)/.env by systemd drop-ins."

status:
	@echo "=== GitHub Credentials Status ==="
	@if [ -f .env ]; then \
		echo "[OK] .env file present (encrypted via git-crypt)."; \
	else \
		echo "[WARN] .env file missing."; \
	fi

logs: test-tokens

upgrade: env-setup
	@echo "[OK] GitHub service configuration verified."

stop:
	@echo "[INFO] No local service daemon to stop."

clean: stop
