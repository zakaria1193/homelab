# Home Assistant SSHFS Terminal AI Workspace Makefile
USER = $(shell whoami)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
WORKSPACE_SYMLINK = $(HOME_DIR)/hass_sshfs_workspace
ENV_FILE ?= .env

$(shell test -f $(ENV_FILE) || cp $(ENV_FILE).example $(ENV_FILE) 2>/dev/null)
-include $(ENV_FILE)

HASS_SSH_HOST ?= 192.168.1.11
HASS_SSH_PORT ?= 22
HASS_SSH_USER ?= zfadli
HASS_REMOTE_DIR ?= /config
HASS_MOUNT_DIR ?= $(CURR_DIR)/config
SSHFS_OPTIONS ?= reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,follow_symlinks,auto_unmount

.PHONY: help install setup env-setup setup-symlink mount unmount status clean agy claude

help:
	@echo "Home Assistant SSHFS Terminal AI Workspace (hass-sshfs-bots)"
	@echo "============================================================"
	@echo "  make agy       - Mount SSHFS, launch Antigravity (agy), auto-unmount on exit"
	@echo "  make claude    - Mount SSHFS, launch Claude Code CLI, auto-unmount on exit"
	@echo "  make mount     - Mount Home Assistant configs from $(HASS_SSH_HOST) via sshfs"
	@echo "  make unmount   - Safely unmount Home Assistant configs from $(HASS_MOUNT_DIR)"
	@echo "  make status    - Check SSHFS mount status"
	@echo "  make setup     - Prepare .env, symlinks, and verify sshfs"
	@echo "  make clean     - Unmount SSHFS"

agy:
	@./hass-agy.sh

claude:
	@./hass-claude.sh

env-setup:
	@test -f $(ENV_FILE) || cp $(ENV_FILE).example $(ENV_FILE)
	@echo "Using $(ENV_FILE)"

setup-symlink:
	@echo "Ensuring $(WORKSPACE_SYMLINK) symlink..."
	@ln -sfn $(CURR_DIR) $(WORKSPACE_SYMLINK)
	@echo "[OK] Symlink: $(WORKSPACE_SYMLINK) -> $(CURR_DIR)"

install: setup-symlink
	@echo "Verifying sshfs installation..."
	@if command -v sshfs >/dev/null 2>&1; then \
		echo "[OK] sshfs is installed: $$(sshfs --version 2>&1 | head -1)"; \
	else \
		echo "[WARN] sshfs not found. Installing via apt if sudo available..."; \
		sudo -n apt-get update && sudo -n apt-get install -y sshfs || echo "[ERROR] please install sshfs manually"; \
	fi

setup: env-setup setup-symlink install
	@echo "[OK] Full Home Assistant SSHFS Workspace setup complete."

mount:
	@mkdir -p $(HASS_MOUNT_DIR)
	@if mountpoint -q $(HASS_MOUNT_DIR); then \
		echo "[OK] $(HASS_MOUNT_DIR) is already mounted."; \
	else \
		echo "Mounting $(HASS_SSH_USER)@$(HASS_SSH_HOST):$(HASS_REMOTE_DIR) to $(HASS_MOUNT_DIR)..."; \
		sshfs -p $(HASS_SSH_PORT) -o $(SSHFS_OPTIONS) $(HASS_SSH_USER)@$(HASS_SSH_HOST):$(HASS_REMOTE_DIR) $(HASS_MOUNT_DIR) || \
			echo "[WARN] SSHFS mount failed (check SSH keys / connectivity to $(HASS_SSH_HOST))"; \
	fi

unmount:
	@if mountpoint -q $(HASS_MOUNT_DIR); then \
		echo "Unmounting $(HASS_MOUNT_DIR)..."; \
		fusermount -uz $(HASS_MOUNT_DIR) 2>/dev/null || fusermount -u $(HASS_MOUNT_DIR) 2>/dev/null || sudo umount -l $(HASS_MOUNT_DIR) 2>/dev/null || true; \
		echo "[OK] Unmounted $(HASS_MOUNT_DIR)"; \
	else \
		echo "[INFO] $(HASS_MOUNT_DIR) is not mounted."; \
	fi

status:
	@echo "=== SSHFS Mount Status ==="
	@if mountpoint -q $(HASS_MOUNT_DIR); then \
		echo "[UP] $(HASS_MOUNT_DIR) is mounted from $(HASS_SSH_USER)@$(HASS_SSH_HOST):$(HASS_REMOTE_DIR)"; \
	else \
		echo "[DOWN] $(HASS_MOUNT_DIR) is not mounted"; \
	fi

clean: unmount
