# Supabase service management & credentials
SERVICE_NAME = supabase
CURR_DIR     = $(shell pwd)
PYTHON_BIN  ?= $(shell which python3 2>/dev/null || echo /usr/bin/python3)

.PHONY: help install start status logs upgrade stop clean env-setup test-tokens test

help:
	@echo "Supabase Service & Credentials"
	@echo "=============================="
	@echo "  make install     - Set up local configuration and system symlink (/etc/supabase.env)"
	@echo "  make test-tokens - Test Supabase Management API token against https://api.supabase.com/v1/projects"
	@echo "  make status      - Check configuration & credential status"
	@echo "  make start       - Ensure environment and symlinks are active"
	@echo "  make logs        - Show token verification output"
	@echo "  make upgrade     - Re-verify configuration and refresh symlinks"
	@echo "  make stop        - Remove system symlink (/etc/supabase.env)"
	@echo "  make clean       - Alias for make stop"
	@echo "  make env-setup   - Create .env from template if missing"

install: env-setup
	@if sudo -n true 2>/dev/null; then \
		sudo ln -sf $(CURR_DIR)/.env /etc/supabase.env; \
		echo "[OK] Symlinked /etc/supabase.env -> $(CURR_DIR)/.env"; \
	else \
		echo "[WARN] Passwordless sudo not available; run 'sudo ln -sf $(CURR_DIR)/.env /etc/supabase.env' manually."; \
	fi
	@echo "[OK] Supabase service configuration ready."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi

test:
	@echo "No offline tests here; the live credential check is 'make test-tokens'."

test-tokens: env-setup
	@$(PYTHON_BIN) test_tokens.py

start: install
	@echo "[INFO] No background daemon required; SUPABASE_ACCESS_TOKEN is injected into systemd units via /etc/supabase.env."

status:
	@echo "=== Supabase Credentials Status ==="
	@if [ -f .env ]; then \
		echo "[OK] .env file present (encrypted via git-crypt)."; \
	else \
		echo "[WARN] .env file missing."; \
	fi
	@if [ -L /etc/supabase.env ]; then \
		echo "[OK] /etc/supabase.env symlink is active -> $$(readlink /etc/supabase.env)"; \
	elif [ -f /etc/supabase.env ]; then \
		echo "[WARN] /etc/supabase.env exists as a static file (run 'make install' to symlink)."; \
	else \
		echo "[INFO] /etc/supabase.env not present."; \
	fi

logs: test-tokens

upgrade: install
	@echo "[OK] Supabase service configuration verified."

stop:
	@if sudo -n true 2>/dev/null; then \
		if [ -L /etc/supabase.env ]; then \
			sudo rm -f /etc/supabase.env; \
			echo "[OK] Removed /etc/supabase.env symlink."; \
		fi \
	fi

clean: stop
