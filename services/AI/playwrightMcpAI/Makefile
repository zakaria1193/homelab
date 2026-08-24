# Playwright MCP AI Service Automation Makefile
SERVICE_NAME = playwright-mcp
USER = $(shell whoami)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(shell pwd)
NPX_BIN ?= $(shell which npx)

.PHONY: help install upgrade setup env-setup start stop restart status logs clean systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

help:
	@echo "Playwright MCP AI Service Automation"
	@echo "====================================="
	@echo "  make install   - Download the Playwright browser (chromium)"
	@echo "  make start     - Start the MCP server (HTTP/SSE) via systemd"
	@echo "  make status    - Check status of the MCP server service"
	@echo "  make logs      - View live logs of the MCP server service"
	@echo "  make upgrade   - Refresh the browser build and restart the service"
	@echo "  make stop      - Stop the MCP server service and clean up systemd files"

# Streamlined user aliases
start: env-setup install systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@if [ -z "$(NPX_BIN)" ]; then echo "Error: npx not found on PATH."; exit 1; fi
	@echo "Installing Playwright browser (chromium)..."
	@if sudo -n true 2>/dev/null; then \
		$(NPX_BIN) -y playwright install --with-deps chromium; \
	else \
		$(NPX_BIN) -y playwright install chromium; \
		echo "[INFO] No passwordless sudo - skipped OS-level dependencies (--with-deps)."; \
		echo "       If the browser fails to launch, ask an admin to run:"; \
		echo "         sudo npx playwright install-deps chromium"; \
	fi
	@echo "[OK] Installation complete."

upgrade:
	@echo "Refreshing the Playwright browser build..."
	@$(MAKE) install
	@echo "Restarting service to pick up @playwright/mcp@latest..."
	-@$(MAKE) restart
	@echo "[OK] Upgrade complete."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi

setup: env-setup install
	@echo "Playwright MCP setup completed."

systemd-setup: env-setup
	@if [ -z "$(NPX_BIN)" ]; then echo "Error: npx not found on PATH."; exit 1; fi
	@echo "Generating systemd unit file..."
	@set -a; . ./.env; set +a; \
	HEADLESS_FLAG=""; [ "$${PLAYWRIGHT_MCP_HEADLESS:-true}" = "true" ] && HEADLESS_FLAG="--headless"; \
	ISOLATED_FLAG=""; [ "$${PLAYWRIGHT_MCP_ISOLATED:-true}" = "true" ] && ISOLATED_FLAG="--isolated"; \
	sed -e "s|{{USER}}|$(USER)|g" \
	    -e "s|{{CURR_DIR}}|$(CURR_DIR)|g" \
	    -e "s|{{PATH_VAL}}|$(PATH_VAL)|g" \
	    -e "s|{{NPX_BIN}}|$(NPX_BIN)|g" \
	    -e "s|{{HOST}}|$${PLAYWRIGHT_MCP_HOST:-127.0.0.1}|g" \
	    -e "s|{{PORT}}|$${PLAYWRIGHT_MCP_PORT:-9012}|g" \
	    -e "s|{{BROWSER}}|$${PLAYWRIGHT_MCP_BROWSER:-chromium}|g" \
	    -e "s|{{HEADLESS_FLAG}}|$$HEADLESS_FLAG|g" \
	    -e "s|{{ISOLATED_FLAG}}|$$ISOLATED_FLAG|g" \
	    playwright-mcp.service.template > $(SERVICE_NAME).service
	@# Install service
	@if sudo -n true 2>/dev/null; then \
		echo "Installing as system service via sudo..."; \
		sudo mv $(SERVICE_NAME).service /etc/systemd/system/; \
		sudo systemctl daemon-reload; \
		sudo systemctl enable $(SERVICE_NAME); \
		sudo systemctl restart $(SERVICE_NAME); \
	else \
		echo "Installing as user systemd service (~/.config/systemd/user)..."; \
		mkdir -p ~/.config/systemd/user; \
		mv $(SERVICE_NAME).service ~/.config/systemd/user/; \
		systemctl --user daemon-reload; \
		systemctl --user enable $(SERVICE_NAME); \
		systemctl --user restart $(SERVICE_NAME); \
	fi
	@echo "[OK] Service started successfully."
	@grep -h '^PLAYWRIGHT_MCP_\(HOST\|PORT\)=' .env | sed 's/^/    /'

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
	@echo "=== Playwright MCP Status ==="
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null || systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user status $(SERVICE_NAME) --no-pager; \
	elif sudo -n true 2>/dev/null; then \
		sudo systemctl status $(SERVICE_NAME) --no-pager; \
	else \
		systemctl --user status $(SERVICE_NAME) --no-pager 2>/dev/null || echo "[INFO] Service '$(SERVICE_NAME)' is not running."; \
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
