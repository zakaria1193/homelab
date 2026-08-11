# Hermes AI Service Automation Makefile
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

.PHONY: help install upgrade setup env-setup start stop restart status logs clean systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

help:
	@echo "Hermes AI Service Automation"
	@echo "============================"
	@echo "  make start     - Start Hermes daemon & web dashboard on http://localhost:$(DASHBOARD_PORT)"
	@echo "  make stop      - Stop the background daemon and clean up"
	@echo "  make status    - Check daemon status"
	@echo "  make logs      - View live daemon logs"
	@echo "  make install   - Install hermes-agent CLI"
	@echo "  make upgrade   - Upgrade hermes-agent CLI to latest version"

# Streamlined user aliases
start: env-setup systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

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
	@echo "[OK] Installation complete."

upgrade:
	@echo "Upgrading Hermes Agent..."
	@if command -v curl >/dev/null 2>&1; then \
		curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash; \
	elif command -v uv >/dev/null 2>&1; then \
		uv tool install hermes-agent --force; \
	elif command -v pip3 >/dev/null 2>&1; then \
		pip3 install --upgrade hermes-agent; \
	else \
		echo "Error: Neither curl, uv, nor pip3 found."; exit 1; \
	fi
	@if sudo systemctl is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		sudo systemctl restart $(SERVICE_NAME); \
	fi
	@echo "[OK] Upgrade complete."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi

setup: env-setup
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
	sudo mv $(SERVICE_NAME).service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE_NAME)
	sudo systemctl start $(SERVICE_NAME)
	@echo "[OK] Hermes AI service started on http://localhost:$(DASHBOARD_PORT)"

systemd-stop:
	@echo "Stopping service..."
	-sudo systemctl stop $(SERVICE_NAME)
	-sudo systemctl disable $(SERVICE_NAME)
	-sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service
	sudo systemctl daemon-reload

systemd-status:
	-sudo systemctl status $(SERVICE_NAME)

systemd-restart:
	sudo systemctl restart $(SERVICE_NAME)

systemd-logs:
	sudo journalctl -u $(SERVICE_NAME) -n 30 -f
