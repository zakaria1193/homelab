# OpenHands AI Service Automation Makefile
SERVICE_NAME = openhands-ai
USER = $(shell whoami)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(shell pwd)
OPENHANDS_HOST ?= 0.0.0.0
OPENHANDS_PORT ?= 3030
UV_BIN ?= $(shell which uv 2>/dev/null || echo /home/zfadli/.local/bin/uv)

.PHONY: help install upgrade setup env-setup start stop restart status logs clean systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

help:
	@echo "OpenHands AI Service Automation"
	@echo "==============================="
	@echo "  make install   - Install openhands-ai in virtual environment via uv/pip"
	@echo "  make start     - Start OpenHands daemon & server on http://0.0.0.0:$(OPENHANDS_PORT)"
	@echo "  make status    - Check systemd service status"
	@echo "  make logs      - View live systemd logs"
	@echo "  make upgrade   - Upgrade openhands-ai package to latest"
	@echo "  make stop      - Stop the background service daemon and clean up"

# Streamlined user aliases
start: env-setup systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@echo "Creating virtual environment and installing openhands-ai..."
	@if [ ! -d venv ]; then \
		if [ -f "$(UV_BIN)" ]; then \
			$(UV_BIN) venv venv; \
		else \
			python3 -m venv venv; \
		fi \
	fi
	@if [ -f "$(UV_BIN)" ]; then \
		$(UV_BIN) pip install --python venv/bin/python openhands-ai; \
	else \
		venv/bin/pip install openhands-ai; \
	fi
	@echo "[OK] Installation complete."

upgrade:
	@echo "Upgrading openhands-ai..."
	@if [ -f "$(UV_BIN)" ]; then \
		$(UV_BIN) pip install --python venv/bin/python -U openhands-ai; \
	else \
		venv/bin/pip install -U openhands-ai; \
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

setup: env-setup install
	@echo "OpenHands AI environment setup completed."

systemd-setup: env-setup
	@echo "Creating systemd service file for $(SERVICE_NAME)..."
	@mkdir -p ~/.config/systemd/user
	@echo "[Unit]" > $(SERVICE_NAME).service
	@echo "Description=OpenHands AI Agent Server" >> $(SERVICE_NAME).service
	@echo "After=network.target network-online.target" >> $(SERVICE_NAME).service
	@echo "Wants=network-online.target" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Service]" >> $(SERVICE_NAME).service
	@echo "Type=simple" >> $(SERVICE_NAME).service
	@echo "WorkingDirectory=$(CURR_DIR)" >> $(SERVICE_NAME).service
	@echo "Environment=\"PATH=$(PATH_VAL):$(CURR_DIR)/venv/bin\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"OPENHANDS_HOST=$(OPENHANDS_HOST)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"OPENHANDS_PORT=$(OPENHANDS_PORT)\"" >> $(SERVICE_NAME).service
	@echo "EnvironmentFile=-$(CURR_DIR)/.env" >> $(SERVICE_NAME).service
	@echo "ExecStart=$(CURR_DIR)/venv/bin/agent-server --host $(OPENHANDS_HOST) --port $(OPENHANDS_PORT)" >> $(SERVICE_NAME).service
	@echo "Restart=on-failure" >> $(SERVICE_NAME).service
	@echo "RestartSec=10" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Install]" >> $(SERVICE_NAME).service
	@echo "WantedBy=default.target multi-user.target" >> $(SERVICE_NAME).service
	@if sudo -n true 2>/dev/null; then \
		echo "Installing as system service via sudo..."; \
		sudo mv $(SERVICE_NAME).service /etc/systemd/system/; \
		sudo systemctl daemon-reload; \
		sudo systemctl enable $(SERVICE_NAME); \
		sudo systemctl start $(SERVICE_NAME); \
	else \
		echo "Installing as user systemd service (~/.config/systemd/user)..."; \
		mv $(SERVICE_NAME).service ~/.config/systemd/user/; \
		systemctl --user daemon-reload; \
		systemctl --user enable $(SERVICE_NAME); \
		systemctl --user start $(SERVICE_NAME); \
	fi
	@echo "[OK] OpenHands AI service started on http://0.0.0.0:$(OPENHANDS_PORT)"

systemd-stop:
	@echo "Stopping service..."
	-@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user stop $(SERVICE_NAME); \
		systemctl --user disable $(SERVICE_NAME); \
		rm -f ~/.config/systemd/user/$(SERVICE_NAME).service; \
		systemctl --user daemon-reload; \
	fi
	-@if sudo -n true 2>/dev/null && sudo systemctl is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		sudo systemctl stop $(SERVICE_NAME); \
		sudo systemctl disable $(SERVICE_NAME); \
		sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service; \
		sudo systemctl daemon-reload; \
	fi

systemd-status:
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null || systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user status $(SERVICE_NAME); \
	elif sudo -n true 2>/dev/null; then \
		sudo systemctl status $(SERVICE_NAME); \
	else \
		systemctl --user status $(SERVICE_NAME) 2>/dev/null || echo "[INFO] Service '$(SERVICE_NAME)' is not running. Run 'make start' to launch it."; \
	fi

systemd-restart:
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user restart $(SERVICE_NAME); \
	else \
		sudo systemctl restart $(SERVICE_NAME); \
	fi

systemd-logs:
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		journalctl --user -u $(SERVICE_NAME) -n 30 -f; \
	else \
		sudo journalctl -u $(SERVICE_NAME) -n 30 -f; \
	fi


