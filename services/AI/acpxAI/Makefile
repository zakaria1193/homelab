# ACPX AI Service Automation Makefile (Systemd Only)
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

.PHONY: help install setup env-setup systemd-setup systemd-stop systemd-status systemd-restart systemd-logs systemd-log restart logs clean

help:
	@echo "ACPX AI Service Automation (Systemd Only)"
	@echo "========================================="
	@echo "Daemon / Session management via systemd:"
	@echo "  make install           - Install acpx CLI, agy-acp, and claude-agent-acp globally via npm"
	@echo "  make env-setup         - Create local .env from .env.example"
	@echo "  make setup             - Run 'acpx config init' and ensure session for current workspace"
	@echo "  make systemd-setup     - Setup and start acpx-ai systemd service"
	@echo "  make systemd-status    - Show acpx-ai systemd service status"
	@echo "  make systemd-restart   - Restart acpx-ai systemd service"
	@echo "  make systemd-stop      - Stop and remove acpx-ai systemd service"
	@echo "  make systemd-logs      - Follow acpx-ai systemd service logs"
	@echo "  make systemd-log       - Alias for systemd-logs"
	@echo "  make restart           - Alias for systemd-restart"
	@echo "  make logs              - Alias for systemd-logs (last 20 lines)"
	@echo "  make clean             - Stop and remove acpx-ai systemd service"
	@echo ""
	@echo "Options (override on make invocation):"
	@echo "  ACPX_AGENT=claude      - Default ACP agent (e.g., claude, agy, codex, gemini)"
	@echo "  ACPX_TTL=0             - Queue owner idle TTL seconds (default: 0 = keep alive forever)"
	@echo "  ACPX_PERMISSIONS=approve-reads - Default permission policy (approve-reads, approve-all, deny-all)"
	@echo "  ACPX_HOME=\"...\"        - Custom config directory (default: $(ACPX_HOME))"

install:
	@echo "Installing ACPX CLI, agy-acp, and claude-agent-acp adapters..."
	npm install -g acpx@latest agy-acp@latest @agentclientprotocol/claude-agent-acp@latest
	@echo "Installation complete. Ensure $(HOME_DIR)/.npm-global/bin (or npm bin) is in your PATH."

env-setup:
	@if [ -f .env ]; then \
		echo ".env already exists, keeping current file."; \
	else \
		cp .env.example .env; \
		echo "Created .env from .env.example. Update your configuration in .env."; \
	fi

setup:
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
	@echo "Creating systemd service file for $(SERVICE_NAME)..."
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
	@echo "Installing systemd unit to /etc/systemd/system/ (requires sudo)..."
	sudo mv $(SERVICE_NAME).service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE_NAME)
	sudo systemctl start $(SERVICE_NAME)
	@echo "ACPX AI systemd service successfully setup and started."

systemd-stop:
	@echo "Stopping and disabling systemd service..."
	-sudo systemctl stop $(SERVICE_NAME)
	-sudo systemctl disable $(SERVICE_NAME)
	-sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service
	sudo systemctl daemon-reload

systemd-status:
	-sudo systemctl status $(SERVICE_NAME)

systemd-restart:
	sudo systemctl restart $(SERVICE_NAME)

systemd-logs:
	sudo journalctl -u $(SERVICE_NAME) -f

systemd-log: systemd-logs

restart: systemd-restart

logs:
	@echo "Showing recent systemd logs..."
	sudo journalctl -u $(SERVICE_NAME) -n 20 --no-pager

clean: systemd-stop
