# OpenHands AI Service Automation Makefile
SERVICE_NAME = openhands-ai
USER = $(shell whoami)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(shell pwd)
OPENHANDS_HOST ?= 0.0.0.0
OPENHANDS_PORT ?= 3030
NPX_BIN ?= $(shell which npx 2>/dev/null || echo /usr/bin/npx)

.PHONY: help install upgrade setup env-setup start stop restart status logs clean systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

help:
	@echo "OpenHands AI Service Automation"
	@echo "==============================="
	@echo "  make install   - Install @openhands/agent-canvas globally via npm"
	@echo "  make start     - Start OpenHands daemon & web dashboard on http://0.0.0.0:$(OPENHANDS_PORT)"
	@echo "  make status    - Check systemd service status"
	@echo "  make logs      - View live systemd logs"
	@echo "  make upgrade   - Upgrade @openhands/agent-canvas package to latest"
	@echo "  make stop      - Stop the background service daemon and clean up"

# Streamlined user aliases
start: env-setup systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@echo "Installing @openhands/agent-canvas globally..."
	npm install -g @openhands/agent-canvas@latest
	@echo "[OK] Installation complete."

upgrade:
	@echo "Upgrading @openhands/agent-canvas..."
	npm install -g @openhands/agent-canvas@latest
	@if sudo systemctl is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		sudo systemctl restart $(SERVICE_NAME); \
	fi
	@echo "[OK] Upgrade complete."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi

setup: env-setup install
	@echo "OpenHands AI environment setup completed."

systemd-setup: env-setup
	@echo "Creating systemd service file for $(SERVICE_NAME)..."
	@echo "[Unit]" > $(SERVICE_NAME).service
	@echo "Description=OpenHands AI Agent Service & Web Dashboard" >> $(SERVICE_NAME).service
	@echo "After=network.target network-online.target" >> $(SERVICE_NAME).service
	@echo "Wants=network-online.target" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Service]" >> $(SERVICE_NAME).service
	@echo "Type=simple" >> $(SERVICE_NAME).service
	@echo "User=$(USER)" >> $(SERVICE_NAME).service
	@echo "WorkingDirectory=$(CURR_DIR)" >> $(SERVICE_NAME).service
	@echo "Environment=\"PATH=$(PATH_VAL)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"OPENHANDS_HOST=$(OPENHANDS_HOST)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"OPENHANDS_PORT=$(OPENHANDS_PORT)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"PORT=$(OPENHANDS_PORT)\"" >> $(SERVICE_NAME).service
	@echo "EnvironmentFile=-$(CURR_DIR)/.env" >> $(SERVICE_NAME).service
	@echo "ExecStart=$(NPX_BIN) @openhands/agent-canvas --port $(OPENHANDS_PORT)" >> $(SERVICE_NAME).service
	@echo "Restart=on-failure" >> $(SERVICE_NAME).service
	@echo "RestartSec=10" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Install]" >> $(SERVICE_NAME).service
	@echo "WantedBy=multi-user.target" >> $(SERVICE_NAME).service
	sudo mv $(SERVICE_NAME).service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE_NAME)
	sudo systemctl start $(SERVICE_NAME)
	@echo "[OK] OpenHands AI service started on http://0.0.0.0:$(OPENHANDS_PORT)"

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
