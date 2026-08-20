# arr-mcp AI Service Automation Makefile
SERVICE_NAME = arr-mcp-backend
USER = $(shell whoami)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(shell pwd)
UV_BIN ?= $(shell which uv 2>/dev/null || echo /home/zfadli/.local/bin/uv)

.PHONY: help install upgrade setup env-setup start stop restart status logs clean systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

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
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@echo "Installing backend dependencies using uv..."
	@cd arr-mcp && $(UV_BIN) sync
	@echo "[OK] Installation complete."

upgrade:
	@echo "Pulling latest changes for arr-mcp..."
	@cd arr-mcp && git pull
	@echo "Upgrading backend dependencies..."
	@cd arr-mcp && $(UV_BIN) sync
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

systemd-setup: env-setup
	@echo "Generating systemd unit file..."
	@# Generate backend service
	@sed -e "s|{{USER}}|$(USER)|g" \
	     -e "s|{{CURR_DIR}}|$(CURR_DIR)|g" \
	     -e "s|{{PATH_VAL}}|$(PATH_VAL)|g" \
	     -e "s|{{UV_BIN}}|$(UV_BIN)|g" \
	     arr-mcp-backend.service.template > $(SERVICE_NAME).service
	@# Install service
	@if sudo -n true 2>/dev/null; then \
		echo "Installing as system service via sudo..."; \
		sudo mv $(SERVICE_NAME).service /etc/systemd/system/; \
		sudo systemctl daemon-reload; \
		sudo systemctl enable $(SERVICE_NAME); \
		sudo systemctl start $(SERVICE_NAME); \
	else \
		echo "Installing as user systemd service (~/.config/systemd/user)..."; \
		mkdir -p ~/.config/systemd/user; \
		mv $(SERVICE_NAME).service ~/.config/systemd/user/; \
		systemctl --user daemon-reload; \
		systemctl --user enable $(SERVICE_NAME); \
		systemctl --user start $(SERVICE_NAME); \
	fi
	@echo "[OK] Service started successfully."
	@echo "Backend (SSE MCP): Port 10938"

systemd-stop:
	@echo "Stopping service..."
	-@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null || systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user stop $(SERVICE_NAME); \
		systemctl --user disable $(SERVICE_NAME); \
		rm -f ~/.config/systemd/user/$(SERVICE_NAME).service; \
		systemctl --user daemon-reload; \
	fi
	-@if sudo -n true 2>/dev/null; then \
		sudo systemctl stop $(SERVICE_NAME) 2>/dev/null; \
		sudo systemctl disable $(SERVICE_NAME) 2>/dev/null; \
		sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service; \
		sudo systemctl daemon-reload; \
	fi
	@echo "[OK] Service stopped and unit file removed."

systemd-status:
	@echo "=== Backend Status ==="
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null || systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user status $(SERVICE_NAME); \
	elif sudo -n true 2>/dev/null; then \
		sudo systemctl status $(SERVICE_NAME); \
	else \
		systemctl --user status $(SERVICE_NAME) 2>/dev/null || echo "[INFO] Service '$(SERVICE_NAME)' is not running."; \
	fi

systemd-restart:
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user restart $(SERVICE_NAME); \
	else \
		sudo systemctl restart $(SERVICE_NAME); \
	fi

systemd-logs:
	@echo "Streaming logs (press Ctrl+C to stop)..."
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		journalctl --user -u $(SERVICE_NAME) -n 30 -f; \
	else \
		sudo journalctl -u $(SERVICE_NAME) -n 30 -f; \
	fi
