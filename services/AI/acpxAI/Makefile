# ACPX AI Service Automation Makefile
SERVICE_NAME = acpx-ai
USER = $(shell whoami)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(shell pwd)
ACPX_HOME ?= $(HOME_DIR)/.acpx
ACPX_BIN ?= $(shell which acpx 2>/dev/null || echo $(HOME_DIR)/.npm-global/bin/acpx)
ACPX_AGENT ?= claude
ACPX_TTL ?= 0
ACPX_PERMISSIONS ?= approve-reads

.PHONY: help install upgrade setup env-setup start stop restart status logs clean systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

help:
	@echo "ACPX AI Service Automation"
	@echo "=========================="
	@echo "  make install   - Install acpx CLI & ACP adapters globally"
	@echo "  make start     - Start background daemon via systemd"
	@echo "  make status    - Check daemon status"
	@echo "  make logs      - View live daemon logs"
	@echo "  make upgrade   - Upgrade acpx CLI & ACP adapters to latest versions"
	@echo "  make stop      - Stop the background daemon and clean up"

# Streamlined user aliases
start: env-setup systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@echo "Installing ACPX CLI, agy-acp, and claude-agent-acp adapters..."
	npm install -g acpx@latest agy-acp@latest @agentclientprotocol/claude-agent-acp@latest
	@echo "[OK] Installation complete."

upgrade:
	@echo "Upgrading ACPX CLI, agy-acp, and claude-agent-acp adapters..."
	npm install -g acpx@latest agy-acp@latest @agentclientprotocol/claude-agent-acp@latest
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
	@echo "Initializing ACPX configuration & ensuring session..."
	@if [ -f "$(ACPX_BIN)" ]; then \
		$(ACPX_BIN) config init; \
		$(ACPX_BIN) $(ACPX_AGENT) sessions ensure; \
	elif command -v acpx >/dev/null 2>&1; then \
		acpx config init; \
		acpx $(ACPX_AGENT) sessions ensure; \
	else \
		echo "ACPX binary not found. Run 'make install' first."; exit 1; \
	fi

systemd-setup: env-setup
	@echo "Creating and starting systemd service for $(SERVICE_NAME)..."
	@echo "[Unit]" > $(SERVICE_NAME).service
	@echo "Description=ACPX AI Agent Client Protocol Daemon" >> $(SERVICE_NAME).service
	@echo "After=network.target network-online.target" >> $(SERVICE_NAME).service
	@echo "Wants=network-online.target" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Service]" >> $(SERVICE_NAME).service
	@echo "Type=simple" >> $(SERVICE_NAME).service
	@echo "User=$(USER)" >> $(SERVICE_NAME).service
	@echo "WorkingDirectory=$(CURR_DIR)" >> $(SERVICE_NAME).service
	@echo "Environment=\"PATH=$(PATH_VAL)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"ACPX_HOME=$(ACPX_HOME)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"ACPX_AGENT=$(ACPX_AGENT)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"ACPX_TTL=$(ACPX_TTL)\"" >> $(SERVICE_NAME).service
	@echo "EnvironmentFile=-$(CURR_DIR)/.env" >> $(SERVICE_NAME).service
	@echo "ExecStart=/bin/sh -c '$(ACPX_BIN) --ttl $(ACPX_TTL) --$(ACPX_PERMISSIONS) $(ACPX_AGENT) sessions ensure --name daemon && while true; do sleep 60; $(ACPX_BIN) --ttl $(ACPX_TTL) $(ACPX_AGENT) status >/dev/null 2>&1 || $(ACPX_BIN) --ttl $(ACPX_TTL) --$(ACPX_PERMISSIONS) $(ACPX_AGENT) sessions ensure --name daemon; done'" >> $(SERVICE_NAME).service
	@echo "Restart=on-failure" >> $(SERVICE_NAME).service
	@echo "RestartSec=10" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Install]" >> $(SERVICE_NAME).service
	@echo "WantedBy=multi-user.target" >> $(SERVICE_NAME).service
	sudo mv $(SERVICE_NAME).service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE_NAME)
	sudo systemctl start $(SERVICE_NAME)
	@echo "[OK] Service started successfully."

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
