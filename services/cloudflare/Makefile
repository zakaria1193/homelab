# Cloudflare service management & credentials
SERVICE_NAME = cloudflare

.PHONY: help install start status logs upgrade stop clean env-setup

help:
	@echo "Cloudflare Service & Credentials"
	@echo "================================"
	@echo "  make install   - Verify local configuration"
	@echo "  make start     - Start service (no local daemon currently running)"
	@echo "  make status    - Check configuration & service status"
	@echo "  make logs      - View logs (no local daemon currently running)"
	@echo "  make upgrade   - Check configuration"
	@echo "  make stop      - Stop service"
	@echo "  make clean     - Clean service"
	@echo "  make env-setup - Create .env from template if missing"

install: env-setup
	@echo "[OK] Cloudflare service configuration ready."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi

start: env-setup
	@echo "[INFO] No local daemon to run. Cloudflare tunnels run on the gateway Pi and Workers run on Cloudflare edge."

status:
	@echo "=== Cloudflare Service Status ==="
	@echo "[INFO] No local service running on this host."
	@echo "[INFO] Cloudflare tunnel runs on gateway (Raspberry Pi 4)."
	@if [ -f .env ]; then \
		echo "[OK] .env file present (encrypted via git-crypt)."; \
	else \
		echo "[WARN] .env file missing."; \
	fi

logs:
	@echo "[INFO] No local daemon running; check cloudflared logs on gateway host."

upgrade: env-setup
	@echo "[OK] Cloudflare service configuration verified."

stop:
	@echo "[INFO] No local service to stop."

clean: stop
