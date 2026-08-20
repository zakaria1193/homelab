# Paperclip AI Service Automation Makefile
SERVICE_NAME = paperclip-ai
USER = $(shell whoami)
NPX = $(shell which npx)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
HOSTS ?= 192.168.1.10 paperclip.zakariafadli.com

include mcp.mk

CURR_DIR = $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
WORKSPACE_SYMLINK = $(HOME_DIR)/paperclip_workspace

.PHONY: help install upgrade setup env-setup setup-symlink start stop restart status logs clean systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

help:
	@echo "Paperclip AI Service Automation"
	@echo "==============================="
	@echo "  make setup     - Full setup: .env, symlinks, paperclipai & paperclip-mcp"
	@echo "  make install   - Install paperclipai globally & setup workspace symlink"
	@echo "  make start     - Start paperclipai daemon via systemd"
	@echo "  make status    - Check daemon status"
	@echo "  make logs      - View live daemon logs"
	@echo "  make upgrade   - Upgrade paperclipai and paperclip-mcp to latest"
	@echo "  make stop      - Stop the background daemon and clean up"

# Streamlined user aliases
start: systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

env-setup: mcp-env-setup

setup-symlink:
	@echo "Ensuring ~/paperclip_workspace symlink..."
	@ln -sfn $(CURR_DIR) $(WORKSPACE_SYMLINK)
	@echo "[OK] Symlink: $(WORKSPACE_SYMLINK) -> $(CURR_DIR)"

setup: env-setup setup-symlink install
	@echo "[OK] Full Paperclip AI workspace and service setup complete."

install: setup-symlink
	@echo "Installing paperclipai globally..."
	npm install -g paperclipai@latest
	@echo "Installing paperclip-mcp..."
	@$(MAKE) install-mcp
	@echo "[OK] Installation complete."

upgrade:
	@WAS_ACTIVE_SERVICE=0; \
	WAS_ACTIVE_MCP=0; \
	if systemctl is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		WAS_ACTIVE_SERVICE=1; \
		sudo systemctl stop $(SERVICE_NAME); \
	fi; \
	if systemctl is-active --quiet $(MCP_SERVICE_NAME) 2>/dev/null; then \
		WAS_ACTIVE_MCP=1; \
		sudo systemctl stop $(MCP_SERVICE_NAME); \
	fi; \
	echo "Upgrading paperclipai globally..."; \
	npm install -g paperclipai@latest; \
	echo "Upgrading paperclip-mcp..."; \
	$(MAKE) install-mcp; \
	if [ $$WAS_ACTIVE_SERVICE -eq 1 ]; then \
		sudo systemctl start $(SERVICE_NAME); \
	fi; \
	if [ $$WAS_ACTIVE_MCP -eq 1 ]; then \
		sudo systemctl start $(MCP_SERVICE_NAME); \
	fi; \
	echo "[OK] Upgrade complete."

systemd-setup:
	@echo "Creating and starting systemd service file..."
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
	sudo mv $(SERVICE_NAME).service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE_NAME)
	sudo systemctl start $(SERVICE_NAME)
	@for host in $(HOSTS); do \
		$(NPX) paperclipai allowed-hostname $$host; \
	done
	sudo systemctl restart $(SERVICE_NAME)
	@echo "[OK] Paperclip AI service setup complete."

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
