# Variables
SERVICE_NAME = paperclip-ai
USER = $(shell whoami)
NPX = $(shell which npx)
HOME_DIR = $(HOME)
# Inherit current PATH to ensure binaries like 'claude' are found by the service
PATH_VAL = $(shell echo $$PATH)
# Hostnames/IPs to allow during setup (space-separated)
HOSTS ?= 192.168.1.10 paperclip.zakariafadli.com
# Port for the paperclip-mcp HTTP server
MCP_PORT ?= 9011
# Required env vars that must be set (in .env) before serving
REQUIRED_ENV_VARS = PAPERCLIP_BASE_URL PAPERCLIP_API_KEY PAPERCLIP_COMPANY_ID

.PHONY: help install install-mcp env-setup mcp-serve mcp-register systemd-setup systemd-stop systemd-status systemd-restart systemd-logs restart logs clean

help:
	@echo "Paperclip AI Service Automation"
	@echo "==============================="
	@echo "Usage:"
	@echo "  make install         - Install paperclipai globally"
	@echo "  make install-mcp     - Install paperclip-mcp (editable) from paperclip-mcp/"
	@echo "  make env-setup       - Copy paperclip-mcp/.env.example to ./.env"
	@echo "  make mcp-serve       - Start paperclip-mcp HTTP server (port MCP_PORT, default 9011)"
	@echo "  make mcp-register    - Register paperclip-mcp with Claude Code (HTTP transport)"
	@echo "  make systemd-setup   - Setup and start background service using systemd"
	@echo "  make systemd-stop    - Stop and remove systemd service"
	@echo "  make systemd-status  - Show systemd service status"
	@echo "  make restart         - Restart the systemd service"
	@echo "  make logs            - Show systemd service logs"
	@echo "  make clean           - Stop and remove the systemd service"
	@echo ""
	@echo "Options:"
	@echo "  HOSTS=\"h1 h2\"      - Specify hostnames/IPs to allow during setup"
	@echo "  MCP_PORT=9011        - Port for the paperclip-mcp HTTP server"

install:
	@echo "Installing paperclipai globally..."
	npm install -g paperclipai

# Install paperclip-mcp editable for local use.
# Uses uv if available, otherwise falls back to pip.
install-mcp:
	@echo "Installing paperclip-mcp (editable) from paperclip-mcp/..."
	@if command -v uv > /dev/null 2>&1; then \
		echo "Using uv..."; \
		cd paperclip-mcp && uv pip install -e .; \
	else \
		echo "uv not found, using pip..."; \
		cd paperclip-mcp && pip install -e .; \
	fi

# Copy the example env file so values can be filled in.
env-setup:
	@if [ -f .env ]; then \
		echo ".env already exists, not overwriting."; \
	else \
		cp paperclip-mcp/.env.example .env; \
		echo "Created .env from paperclip-mcp/.env.example. Fill in your values:"; \
		echo "  PAPERCLIP_BASE_URL=http://localhost:3100/api"; \
		echo "  PAPERCLIP_API_KEY=your_api_key_here"; \
		echo "  PAPERCLIP_COMPANY_ID=your_company_uuid_here"; \
	fi

# Start the paperclip-mcp HTTP server (Claude Code / mcp-proxy).
# Loads .env and ensures the required vars are set before serving.
mcp-serve:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Run 'make env-setup' and fill in your values."; \
		exit 1; \
	fi
	@set -a; . ./.env; set +a; \
	for var in $(REQUIRED_ENV_VARS); do \
		eval "val=\$$$$var"; \
		if [ -z "$$val" ]; then \
			echo "Error: $$var is not set in .env. Fill it in before serving."; \
			exit 1; \
		fi; \
	done; \
	echo "Starting paperclip-mcp HTTP server on port $(MCP_PORT)..."; \
	paperclip-mcp --port $(MCP_PORT)

# Register paperclip-mcp with Claude Code over HTTP (persistent across restarts).
mcp-register:
	@echo "Registering paperclip with Claude Code (HTTP, port $(MCP_PORT))..."
	claude mcp add paperclip --transport http http://localhost:$(MCP_PORT)/mcp

systemd-setup:
	@echo "Creating systemd service file..."
	@echo "[Unit]" > $(SERVICE_NAME).service
	@echo "Description=Paperclip AI Daemon" >> $(SERVICE_NAME).service
	@echo "After=network.target" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Service]" >> $(SERVICE_NAME).service
	@echo "Type=simple" >> $(SERVICE_NAME).service
	@echo "User=$(USER)" >> $(SERVICE_NAME).service
	@echo "Environment=\"PATH=$(PATH_VAL)\"" >> $(SERVICE_NAME).service
	@echo "Restart=on-failure" >> $(SERVICE_NAME).service
	@echo "RestartSec=10" >> $(SERVICE_NAME).service
	@echo "WorkingDirectory=$(HOME_DIR)" >> $(SERVICE_NAME).service
	@echo "ExecStart=$(NPX) paperclipai onboard --yes --bind lan" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Install]" >> $(SERVICE_NAME).service
	@echo "WantedBy=multi-user.target" >> $(SERVICE_NAME).service
	@echo "Moving service file to /etc/systemd/system/ (requires sudo)..."
	sudo mv $(SERVICE_NAME).service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE_NAME)
	sudo systemctl start $(SERVICE_NAME)
	@echo "Allowing hostnames: $(HOSTS)..."
	@for host in $(HOSTS); do \
		$(NPX) paperclipai allowed-hostname $$host; \
	done
	sudo systemctl restart $(SERVICE_NAME)
	@echo "Systemd service setup complete."

systemd-stop:
	@echo "Stopping and disabling systemd service..."
	-sudo systemctl stop $(SERVICE_NAME)
	-sudo systemctl disable $(SERVICE_NAME)
	-sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service
	sudo systemctl daemon-reload

systemd-status:
	sudo systemctl status $(SERVICE_NAME)

systemd-restart:
	sudo systemctl restart $(SERVICE_NAME)

systemd-logs:
	sudo journalctl -u $(SERVICE_NAME) -f

restart:
	@echo "Restarting systemd service..."
	sudo systemctl restart $(SERVICE_NAME)

logs:
	@echo "Showing systemd logs..."
	sudo journalctl -u $(SERVICE_NAME) -n 20 --no-pager

clean:
	@echo "Cleaning up systemd service..."
	-sudo systemctl stop $(SERVICE_NAME)
	-sudo systemctl disable $(SERVICE_NAME)
	-sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service
	-sudo systemctl daemon-reload
