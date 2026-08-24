# Homelab Cockpit Service Automation Makefile
SERVICE_NAME = homelab-status
USER = $(shell whoami)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
RUNTIME_DIR = /run/user/$(shell id -u)

STATUS_HOST ?= 0.0.0.0
STATUS_PORT ?= 8300
PYTHON_BIN ?= $(shell which python3 2>/dev/null || echo /usr/bin/python3)

.PHONY: help install upgrade setup env-setup check start stop restart status logs clean \
	systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

help:
	@echo "Homelab Cockpit Service Automation"
	@echo "==========================================="
	@echo "  make install   - Verify runtime prerequisites (python3 stdlib only)"
	@echo "  make start     - Serve the cockpit on http://$(STATUS_HOST):$(STATUS_PORT) via systemd"
	@echo "  make status    - Check daemon status"
	@echo "  make logs      - View live daemon logs"
	@echo "  make upgrade   - Reload the cockpit after config or code changes"
	@echo "  make stop      - Stop the daemon and remove the systemd unit"
	@echo "  make check     - Print a one-shot status snapshot to the terminal"

# Streamlined user aliases
start: env-setup systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@echo "Checking prerequisites..."
	@$(PYTHON_BIN) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' \
		|| { echo "[ERROR] python3 >= 3.7 is required ($(PYTHON_BIN))"; exit 1; }
	@echo "  python3: $$($(PYTHON_BIN) --version)"
	@command -v systemctl >/dev/null 2>&1 && echo "  systemctl: found" \
		|| echo "  [WARN] systemctl missing - systemd checks will report 'unknown'"
	@command -v docker >/dev/null 2>&1 && echo "  docker: found" \
		|| echo "  [WARN] docker missing - container checks will report 'unknown'"
	@echo "[OK] No external packages needed; the cockpit uses the Python standard library."

upgrade: install
	@echo "Validating services.conf..."
	@$(PYTHON_BIN) $(CURR_DIR)/status_server.py --once >/dev/null
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user restart $(SERVICE_NAME); \
	elif sudo -n true 2>/dev/null && sudo systemctl is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		sudo systemctl restart $(SERVICE_NAME); \
	fi
	@echo "[OK] Upgrade complete."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi

setup: env-setup install
	@echo "Homelab Cockpit environment setup completed."

check:
	@$(PYTHON_BIN) $(CURR_DIR)/status_server.py --once

systemd-setup: env-setup
	@echo "Creating systemd service file for $(SERVICE_NAME)..."
	@mkdir -p ~/.config/systemd/user
	@echo "[Unit]" > $(SERVICE_NAME).service
	@echo "Description=Homelab Cockpit" >> $(SERVICE_NAME).service
	@echo "After=network.target network-online.target" >> $(SERVICE_NAME).service
	@echo "Wants=network-online.target" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Service]" >> $(SERVICE_NAME).service
	@echo "Type=simple" >> $(SERVICE_NAME).service
	@echo "User=$(USER)" >> $(SERVICE_NAME).service
	@echo "WorkingDirectory=$(CURR_DIR)" >> $(SERVICE_NAME).service
	@echo "Environment=\"PATH=$(PATH_VAL)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"XDG_RUNTIME_DIR=$(RUNTIME_DIR)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"STATUS_HOST=$(STATUS_HOST)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"STATUS_PORT=$(STATUS_PORT)\"" >> $(SERVICE_NAME).service
	@echo "EnvironmentFile=-$(CURR_DIR)/.env" >> $(SERVICE_NAME).service
	@echo "ExecStart=$(PYTHON_BIN) $(CURR_DIR)/status_server.py" >> $(SERVICE_NAME).service
	@echo "Restart=always" >> $(SERVICE_NAME).service
	@echo "RestartSec=5" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Install]" >> $(SERVICE_NAME).service
	@echo "WantedBy=default.target multi-user.target" >> $(SERVICE_NAME).service
	@if sudo -n true 2>/dev/null; then \
		echo "Installing as system service via sudo..."; \
		sudo mv $(SERVICE_NAME).service /etc/systemd/system/; \
		sudo systemctl daemon-reload; \
		sudo systemctl enable $(SERVICE_NAME); \
		sudo systemctl restart $(SERVICE_NAME); \
	else \
		echo "Installing as user systemd service (~/.config/systemd/user)..."; \
		mv $(SERVICE_NAME).service ~/.config/systemd/user/; \
		systemctl --user daemon-reload; \
		systemctl --user enable $(SERVICE_NAME); \
		systemctl --user restart $(SERVICE_NAME); \
		loginctl enable-linger $(USER) >/dev/null 2>&1 || true; \
	fi
	@echo "[OK] Homelab Cockpit served on http://$(STATUS_HOST):$(STATUS_PORT)"

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

systemd-status:
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null || systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user status $(SERVICE_NAME) --no-pager; \
	elif sudo -n true 2>/dev/null; then \
		sudo systemctl status $(SERVICE_NAME) --no-pager; \
	else \
		systemctl --user status $(SERVICE_NAME) --no-pager 2>/dev/null || echo "[INFO] Service '$(SERVICE_NAME)' is not running. Run 'make start' to launch it."; \
	fi

systemd-restart:
	@if systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
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
