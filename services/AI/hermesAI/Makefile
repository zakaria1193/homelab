# Hermes AI Service Automation Makefile (Systemd Only)
SERVICE_NAME = hermes-ai
USER = $(shell whoami)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(shell pwd)
HERMES_HOME ?= $(HOME_DIR)/.hermes
DASHBOARD_HOST ?= 0.0.0.0
DASHBOARD_PORT ?= 8100
HERMES_PORT ?= 8101
HERMES_BIN ?= $(shell which hermes 2>/dev/null || echo $(HOME_DIR)/.local/bin/hermes)
HERMES_CMD ?= dashboard --no-open --host $(DASHBOARD_HOST) --port $(DASHBOARD_PORT) --skip-build

.PHONY: help install setup env-setup systemd-setup systemd-stop systemd-status systemd-restart systemd-logs restart logs clean

help:
	@echo "Hermes AI Service Automation (Systemd Only)"
	@echo "==========================================="
	@echo "Daemon / Dashboard management via systemd:"
	@echo "  make install           - Install hermes-agent CLI"
	@echo "  make env-setup         - Create local .env from .env.example"
	@echo "  make setup             - Run interactive 'hermes setup' configuration wizard"
	@echo "  make systemd-setup     - Setup and start hermes-ai systemd service (Dashboard Port $(DASHBOARD_PORT))"
	@echo "  make systemd-status    - Show hermes-ai systemd service status"
	@echo "  make systemd-restart   - Restart hermes-ai systemd service"
	@echo "  make systemd-stop      - Stop and remove hermes-ai systemd service"
	@echo "  make systemd-logs      - Follow hermes-ai systemd service logs"
	@echo "  make restart           - Alias for systemd-restart"
	@echo "  make logs              - Alias for systemd-logs (last 20 lines)"
	@echo "  make clean             - Stop and remove hermes-ai systemd service"
	@echo ""
	@echo "Options (override on make invocation):"
	@echo "  DASHBOARD_PORT=8100    - Web Dashboard port (default: 8100)"
	@echo "  HERMES_PORT=8101       - Headless gateway port (default: 8101)"
	@echo "  HERMES_CMD=\"...\"      - ExecStart command (default: dashboard --no-open --port 8100 --skip-build)"
	@echo "                           To run gateway daemon instead: HERMES_CMD=\"gateway run\""
	@echo "  HERMES_HOME=\"...\"     - Custom config directory (default: $(HERMES_HOME))"

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
	@echo "Installation complete. Ensure $(HOME_DIR)/.local/bin is in your PATH."

env-setup:
	@if [ -f .env ]; then \
		echo ".env already exists, keeping current file."; \
	else \
		cp .env.example .env; \
		echo "Created .env from .env.example. Update your API keys and tokens in .env."; \
	fi

setup:
	@echo "Running interactive Hermes setup..."
	@if [ -f "$(HERMES_BIN)" ]; then \
		$(HERMES_BIN) setup; \
	elif command -v hermes >/dev/null 2>&1; then \
		hermes setup; \
	else \
		echo "Hermes binary not found. Run 'make install' first."; exit 1; \
	fi

systemd-setup: env-setup
	@echo "Creating systemd service file for $(SERVICE_NAME)..."
	@echo "[Unit]" > $(SERVICE_NAME).service
	@echo "Description=Hermes AI Agent Daemon & Dashboard" >> $(SERVICE_NAME).service
	@echo "After=network.target network-online.target" >> $(SERVICE_NAME).service
	@echo "Wants=network-online.target" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Service]" >> $(SERVICE_NAME).service
	@echo "Type=simple" >> $(SERVICE_NAME).service
	@echo "User=$(USER)" >> $(SERVICE_NAME).service
	@echo "WorkingDirectory=$(CURR_DIR)" >> $(SERVICE_NAME).service
	@echo "Environment=\"PATH=$(PATH_VAL)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"HERMES_HOME=$(HERMES_HOME)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"DASHBOARD_PORT=$(DASHBOARD_PORT)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"HERMES_PORT=$(HERMES_PORT)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"PORT=$(DASHBOARD_PORT)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"API_SERVER_PORT=$(DASHBOARD_PORT)\"" >> $(SERVICE_NAME).service
	@echo "EnvironmentFile=-$(CURR_DIR)/.env" >> $(SERVICE_NAME).service
	@echo "ExecStart=$(HERMES_BIN) $(HERMES_CMD)" >> $(SERVICE_NAME).service
	@echo "Restart=on-failure" >> $(SERVICE_NAME).service
	@echo "RestartSec=10" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Install]" >> $(SERVICE_NAME).service
	@echo "WantedBy=multi-user.target" >> $(SERVICE_NAME).service
	@echo "Installing systemd unit to /etc/systemd/system/ (requires sudo)..."
	sudo mv $(SERVICE_NAME).service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE_NAME)
	sudo systemctl start $(SERVICE_NAME)
	@echo "Hermes AI systemd service successfully setup and started on http://localhost:$(DASHBOARD_PORT)."

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

restart: systemd-restart

logs:
	@echo "Showing recent systemd logs..."
	sudo journalctl -u $(SERVICE_NAME) -n 20 --no-pager

clean: systemd-stop



