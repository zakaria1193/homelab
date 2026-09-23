# Playwright MCP AI Service Automation Makefile
#
# One instance per browser mode. The default instance is headless and is what
# MCP clients point at for testing; a headful instance runs alongside it on its
# own port so a visible window never surprises a test run. Pass INSTANCE=<name>
# to every target, exactly like services/AI/claudeRcAI:
#
#   make start                    -> playwright-mcp          reading .env
#   make start INSTANCE=headful   -> playwright-mcp-headful  reading .env.headful
INSTANCE ?=
SUFFIX := $(if $(INSTANCE),-$(INSTANCE),)
SERVICE_NAME = playwright-mcp$(SUFFIX)
ENV_FILE := .env$(if $(INSTANCE),.$(INSTANCE),)
CONFIG_FILE := playwright-mcp$(SUFFIX).config.json
USER = $(shell whoami)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(shell pwd)
NPX_BIN ?= $(shell which npx)

.PHONY: help install upgrade setup env-setup stealth start stop restart status logs clean systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

help:
	@echo "Playwright MCP AI Service Automation"
	@echo "====================================="
	@echo "  make install   - Download the Playwright browser (chromium)"
	@echo "  make stealth   - Regenerate the anti-detection bundle from the plugin"
	@echo "  make start     - Start the MCP server (HTTP/SSE) via systemd"
	@echo "  make status    - Check status of the MCP server service"
	@echo "  make logs      - View live logs of the MCP server service"
	@echo "  make upgrade   - Refresh the browser build and restart the service"
	@echo "  make stop      - Stop the MCP server service and clean up systemd files"
	@echo ""
	@echo "  Add INSTANCE=<name> to any target to act on that instance"
	@echo "  (unit $(SERVICE_NAME), env $(ENV_FILE))."

# Streamlined user aliases
start: env-setup install stealth systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@if [ -z "$(NPX_BIN)" ]; then echo "Error: npx not found on PATH."; exit 1; fi
	@echo "Installing Playwright browser (chromium & chrome-for-testing)..."
	@# Pin to @latest so the build this downloads matches the @latest the unit
	@# runs. Without the pin npx may reuse an older cached @playwright/mcp and
	@# fetch a chromium revision the running server does not expect, which shows
	@# up only at the first tool call as "Browser is not installed".
	@# No `|| true` here: a missing browser is a broken service, not a warning.
	@$(NPX_BIN) -y @playwright/mcp@latest install-browser chrome-for-testing
	@$(NPX_BIN) -y @playwright/mcp@latest install-browser chromium
	@if sudo -n true 2>/dev/null; then \
		$(NPX_BIN) -y playwright install --with-deps chromium; \
	else \
		$(NPX_BIN) -y playwright install chromium; \
		echo "[INFO] No passwordless sudo - skipped OS-level dependencies (--with-deps)."; \
		echo "       If the browser fails to launch, ask an admin to run:"; \
		echo "         sudo npx playwright install-deps chromium"; \
	fi
	@$(MAKE) --no-print-directory stealth
	@echo "[OK] Installation complete."

upgrade:
	@echo "Refreshing the Playwright browser build..."
	@$(MAKE) install
	@echo "Restarting service to pick up @playwright/mcp@latest..."
	-@$(MAKE) restart
	@echo "[OK] Upgrade complete."

stealth:
	@echo "Generating anti-detection bundle from puppeteer-extra-plugin-stealth..."
	@cd stealth && npm install --silent --no-audit --no-fund && node generate.js
	@echo "[OK] stealth/stealth-init.js and stealth/stealth-launch.json regenerated."

env-setup:
	@if [ ! -f $(ENV_FILE) ]; then \
		if [ ! -f $(ENV_FILE).example ]; then \
			echo "[ERROR] no $(ENV_FILE) and no $(ENV_FILE).example to create it from."; \
			exit 1; \
		fi; \
		cp $(ENV_FILE).example $(ENV_FILE); \
		echo "Created $(ENV_FILE) from $(ENV_FILE).example"; \
	fi

setup: env-setup install
	@echo "Playwright MCP setup completed."

systemd-setup: env-setup
	@if [ -z "$(NPX_BIN)" ]; then echo "Error: npx not found on PATH."; exit 1; fi
	@echo "Rendering playwright-mcp.config.json..."
	@set -a; . ./$(ENV_FILE); set +a; PLAYWRIGHT_MCP_CONFIG_OUT=$(CURR_DIR)/$(CONFIG_FILE) node stealth/render-config.js
	@echo "Generating systemd unit file..."
	@set -a; . ./$(ENV_FILE); set +a; \
	HEADLESS_FLAG=""; [ "$${PLAYWRIGHT_MCP_HEADLESS:-true}" = "true" ] && HEADLESS_FLAG="--headless"; \
	ISOLATED_FLAG=""; [ "$${PLAYWRIGHT_MCP_ISOLATED:-true}" = "true" ] && ISOLATED_FLAG="--isolated"; \
	ALLOWED_HOSTS_FLAG=""; [ -n "$${PLAYWRIGHT_MCP_ALLOWED_HOSTS}" ] && ALLOWED_HOSTS_FLAG="--allowed-hosts $${PLAYWRIGHT_MCP_ALLOWED_HOSTS}"; \
	USER_DATA_DIR_FLAG=""; [ -n "$${PLAYWRIGHT_MCP_USER_DATA_DIR}" ] && USER_DATA_DIR_FLAG="--user-data-dir $${PLAYWRIGHT_MCP_USER_DATA_DIR}"; \
	CONFIG_FLAG="--config $(CURR_DIR)/$(CONFIG_FILE)"; \
	INIT_SCRIPT_FLAG=""; [ "$${PLAYWRIGHT_MCP_STEALTH:-true}" = "true" ] && INIT_SCRIPT_FLAG="--init-script $(CURR_DIR)/stealth/stealth-init.js"; \
	DISPLAY_ENV=""; USER_LINE="User=$(USER)"; \
	if [ "$${PLAYWRIGHT_MCP_HEADLESS:-true}" != "true" ]; then \
	  DISPLAY_ENV="Environment=\"DISPLAY=$${DISPLAY:-:0}\"\nEnvironment=\"XAUTHORITY=$${XAUTHORITY:-$(HOME_DIR)/.Xauthority}\""; \
	fi; \
	if ! sudo -n true 2>/dev/null; then USER_LINE=""; fi; \
	sed -e "s|{{USER_LINE}}|$$USER_LINE|g" \
	    -e "s|{{DISPLAY_ENV}}|$$DISPLAY_ENV|g" \
	    -e "s|{{USER_DATA_DIR_FLAG}}|$$USER_DATA_DIR_FLAG|g" \
	    -e "s|{{CONFIG_FLAG}}|$$CONFIG_FLAG|g" \
	    -e "s|{{INIT_SCRIPT_FLAG}}|$$INIT_SCRIPT_FLAG|g" \
	    -e "s|{{CURR_DIR}}|$(CURR_DIR)|g" \
	    -e "s|{{PATH_VAL}}|$(PATH_VAL)|g" \
	    -e "s|{{NPX_BIN}}|$(NPX_BIN)|g" \
	    -e "s|{{HOST}}|$${PLAYWRIGHT_MCP_HOST:-0.0.0.0}|g" \
	    -e "s|{{PORT}}|$${PLAYWRIGHT_MCP_PORT:-9012}|g" \
	    -e "s|{{BROWSER}}|$${PLAYWRIGHT_MCP_BROWSER:-chromium}|g" \
	    -e "s|{{HEADLESS_FLAG}}|$$HEADLESS_FLAG|g" \
	    -e "s|{{ISOLATED_FLAG}}|$$ISOLATED_FLAG|g" \
	    -e "s|{{ALLOWED_HOSTS_FLAG}}|$$ALLOWED_HOSTS_FLAG|g" \
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
	@echo "[OK] Service $(SERVICE_NAME) started successfully."
	@grep -h '^PLAYWRIGHT_MCP_\(HOST\|PORT\|HEADLESS\|STEALTH\)=' $(ENV_FILE) | sed 's/^/    /'

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
