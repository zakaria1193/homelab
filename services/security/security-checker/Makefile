SERVICE_NAME := security-checker
SERVICE_FILE := $(SERVICE_NAME).service
TIMER_FILE := $(SERVICE_NAME).timer
SERVICE_TEMPLATE := $(SERVICE_NAME).service.template
TIMER_TEMPLATE := $(SERVICE_NAME).timer.template
SYSTEMD_DIR := /etc/systemd/system
USER_SYSTEMD_DIR := $(HOME)/.config/systemd/user
SERVICE_DIR := $(shell pwd)
REPO_ROOT := $(shell cd ../../.. && pwd)
USER_NAME := $(shell whoami)

HAS_SUDO := $(shell sudo -n true 2>/dev/null && echo "yes" || echo "no")

.PHONY: default help install env-setup start status logs run upgrade stop systemd-setup systemd-stop clean

default: help

help:
	@echo "Homelab Weekly Security Checker Service Management"
	@echo "==================================================="
	@echo "  make install         Verify python3 and prerequisites"
	@echo "  make start           Generate systemd unit/timer and start weekly security checker"
	@echo "  make status          Display systemd service and timer status"
	@echo "  make logs            Follow live service logs via journalctl"
	@echo "  make run             Run security checker manually once"
	@echo "  make upgrade         Upgrade service dependencies and restart timer"
	@echo "  make stop            Stop and disable systemd service & timer"
	@echo "  make clean           Alias for make stop"

install:
	@echo "Checking prerequisites..."
	@python3 --version >/dev/null 2>&1 || (echo "Error: python3 is required." && exit 1)
	@echo "[OK] Prerequisites satisfied."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "[OK] Created .env from .env.example"; \
	fi

start: env-setup install
	@echo "Setting up $(SERVICE_NAME) systemd service & timer..."
	@if [ "$(HAS_SUDO)" = "yes" ]; then \
		sed -e "s|%USER%|$(USER_NAME)|g" \
		    -e "s|%REPO_ROOT%|$(REPO_ROOT)|g" \
		    -e "s|%SERVICE_DIR%|$(SERVICE_DIR)|g" \
		    $(SERVICE_TEMPLATE) | sudo tee $(SYSTEMD_DIR)/$(SERVICE_FILE) > /dev/null; \
		sudo cp $(TIMER_TEMPLATE) $(SYSTEMD_DIR)/$(TIMER_FILE); \
		sudo systemctl daemon-reload; \
		sudo systemctl enable --now $(TIMER_FILE); \
		echo "[OK] Systemd system-level timer enabled & started."; \
	else \
		mkdir -p $(USER_SYSTEMD_DIR); \
		sed -e "s|%USER%|$(USER_NAME)|g" \
		    -e "s|%REPO_ROOT%|$(REPO_ROOT)|g" \
		    -e "s|%SERVICE_DIR%|$(SERVICE_DIR)|g" \
		    $(SERVICE_TEMPLATE) > $(USER_SYSTEMD_DIR)/$(SERVICE_FILE); \
		cp $(TIMER_TEMPLATE) $(USER_SYSTEMD_DIR)/$(TIMER_FILE); \
		systemctl --user daemon-reload; \
		systemctl --user enable --now $(TIMER_FILE); \
		echo "[OK] Systemd user-level timer enabled & started."; \
	fi
	@echo "Running initial security check..."
	@$(MAKE) run

status:
	@if [ "$(HAS_SUDO)" = "yes" ]; then \
		systemctl status $(TIMER_FILE) --no-pager || true; \
		systemctl status $(SERVICE_FILE) --no-pager || true; \
	else \
		systemctl --user status $(TIMER_FILE) --no-pager || true; \
		systemctl --user status $(SERVICE_FILE) --no-pager || true; \
	fi

logs:
	@if [ "$(HAS_SUDO)" = "yes" ]; then \
		journalctl -u $(SERVICE_FILE) -f; \
	else \
		journalctl --user -u $(SERVICE_FILE) -f; \
	fi

run:
	@python3 $(SERVICE_DIR)/security_checker.py

upgrade: install
	@echo "Upgrading $(SERVICE_NAME)..."
	@$(MAKE) start

stop:
	@echo "Stopping $(SERVICE_NAME)..."
	@if [ "$(HAS_SUDO)" = "yes" ]; then \
		sudo systemctl stop $(TIMER_FILE) 2>/dev/null || true; \
		sudo systemctl disable $(TIMER_FILE) 2>/dev/null || true; \
		sudo systemctl stop $(SERVICE_FILE) 2>/dev/null || true; \
		sudo systemctl disable $(SERVICE_FILE) 2>/dev/null || true; \
		sudo rm -f $(SYSTEMD_DIR)/$(TIMER_FILE) $(SYSTEMD_DIR)/$(SERVICE_FILE); \
		sudo systemctl daemon-reload; \
	else \
		systemctl --user stop $(TIMER_FILE) 2>/dev/null || true; \
		systemctl --user disable $(TIMER_FILE) 2>/dev/null || true; \
		systemctl --user stop $(SERVICE_FILE) 2>/dev/null || true; \
		systemctl --user disable $(SERVICE_FILE) 2>/dev/null || true; \
		rm -f $(USER_SYSTEMD_DIR)/$(TIMER_FILE) $(USER_SYSTEMD_DIR)/$(SERVICE_FILE); \
		systemctl --user daemon-reload; \
	fi
	@echo "[OK] $(SERVICE_NAME) stopped and uninstalled."

systemd-setup: start
systemd-stop: stop
clean: stop
