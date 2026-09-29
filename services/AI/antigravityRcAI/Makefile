# Antigravity Remote Control (`agy --remote-control`) Service Automation Makefile
#
# Supports multiple always-on instances across workspaces:
#   make start                     -> agy-remote-control            reading .env
#   make start INSTANCE=myrepos    -> agy-remote-control-myrepos    reading .env.myrepos

INSTANCE ?=
SUFFIX := $(if $(INSTANCE),-$(INSTANCE),)
SERVICE_NAME = $(if $(INSTANCE),agy-remote-control$(SUFFIX),antigravity-cli-daemon)
ENV_FILE := .env$(if $(INSTANCE),.$(INSTANCE),)
USER = $(shell whoami)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(shell pwd)

XDG_RUNTIME_DIR ?= /run/user/$(shell id -u)
export XDG_RUNTIME_DIR

$(shell test -f $(ENV_FILE) || cp $(ENV_FILE).example $(ENV_FILE) 2>/dev/null)
-include $(ENV_FILE)

AGY_RC_WORKDIR ?= $(abspath $(CURR_DIR)/../../..)
AGY_RC_NAME ?= $(if $(INSTANCE),$(INSTANCE),homelab)
AGY_RC_PORT ?= $(if $(INSTANCE),,4400)
AGY_LOG_FILE ?= $(HOME_DIR)/.antigravity/agy_daemon$(if $(INSTANCE),_$(INSTANCE),).log
AGY_BIN ?= $(shell which agy 2>/dev/null || echo $(HOME_DIR)/.local/bin/agy)

PORT_ARG = $(if $(strip $(AGY_RC_PORT)),--hub-port $(strip $(AGY_RC_PORT)),)
RC_ARGS = --remote-control $(PORT_ARG) --remote-control-name "$(AGY_RC_NAME)"

.PHONY: help install start stop restart status logs upgrade doctor clean systemd-setup systemd-stop env-setup

help:
	@echo "Antigravity Remote Control AI Service Automation"
	@echo "==============================================="
	@echo "  make install   - Verify/install agy CLI dependency"
	@echo "  make start     - Start daemon in $(AGY_RC_WORKDIR)"
	@echo "  make status    - Check systemd service status"
	@echo "  make logs      - View live daemon logs"
	@echo "  make upgrade   - Update agy CLI and restart daemon"
	@echo "  make stop      - Stop and remove systemd unit"
	@echo "  make doctor    - Diagnostics report"
	@echo ""
	@echo "  Instance:   $(SERVICE_NAME) (INSTANCE=$(INSTANCE), env $(ENV_FILE))"
	@echo "  Workspace:  $(AGY_RC_WORKDIR)"

env-setup:
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "[ERROR] no $(ENV_FILE) and no $(ENV_FILE).example to create it from."; \
		exit 1; \
	fi

install: env-setup
	@which $(AGY_BIN) >/dev/null 2>&1 || (echo "Installing agy CLI..." && curl -fsSL https://antigravity.google/cli/install.sh | bash)
	@echo "[OK] agy CLI is installed: $$($(AGY_BIN) --version)"

start: systemd-setup

systemd-setup: env-setup
ifeq ($(strip $(INSTANCE)),)
	@echo "Starting Antigravity Remote Control daemon ($(SERVICE_NAME))..."
	@$(AGY_BIN) remote-control start --name "$(AGY_RC_NAME)"
	@loginctl enable-linger $(USER) 2>/dev/null || true
	@echo "[OK] $(SERVICE_NAME) running."
else
	@echo "Creating systemd user unit for $(SERVICE_NAME)..."
	@mkdir -p ~/.config/systemd/user
	@mkdir -p $(HOME_DIR)/.antigravity
	@echo "[Unit]" > ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "Description=Antigravity CLI (agy) Remote Control Daemon ($(INSTANCE))" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "After=network.target network-online.target" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "Wants=network-online.target" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "[Service]" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "Type=simple" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "WorkingDirectory=$(AGY_RC_WORKDIR)" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "Environment=\"HOME=$(HOME_DIR)\"" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "Environment=\"PATH=$(PATH_VAL)\"" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "EnvironmentFile=-$(CURR_DIR)/$(ENV_FILE)" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "ExecStart=$(AGY_BIN) $(RC_ARGS)" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "StandardOutput=journal" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "StandardError=journal" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "Restart=always" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "RestartSec=5" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "[Install]" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@echo "WantedBy=default.target" >> ~/.config/systemd/user/$(SERVICE_NAME).service
	@systemctl --user daemon-reload
	@systemctl --user enable $(SERVICE_NAME)
	@systemctl --user restart $(SERVICE_NAME)
	@loginctl enable-linger $(USER) 2>/dev/null || true
	@echo "[OK] $(SERVICE_NAME) running in $(AGY_RC_WORKDIR)."
endif

systemd-stop:
ifeq ($(strip $(INSTANCE)),)
	@echo "Stopping $(SERVICE_NAME)..."
	-@$(AGY_BIN) remote-control stop 2>/dev/null || true
	-@systemctl --user stop $(SERVICE_NAME) 2>/dev/null || true
	-@systemctl --user disable $(SERVICE_NAME) 2>/dev/null || true
	@rm -f ~/.config/systemd/user/$(SERVICE_NAME).service
	@systemctl --user daemon-reload
else
	@echo "Stopping $(SERVICE_NAME)..."
	-@systemctl --user stop $(SERVICE_NAME) 2>/dev/null || true
	-@systemctl --user disable $(SERVICE_NAME) 2>/dev/null || true
	@rm -f ~/.config/systemd/user/$(SERVICE_NAME).service
	@systemctl --user daemon-reload
endif

stop: systemd-stop

restart:
	systemctl --user restart $(SERVICE_NAME)

status:
ifeq ($(strip $(INSTANCE)),)
	-@$(AGY_BIN) remote-control status 2>/dev/null || true
endif
	@systemctl --user --no-pager status $(SERVICE_NAME) || true

logs:
	@journalctl --user -u $(SERVICE_NAME) -f

upgrade:
	@echo "==> Updating the agy CLI"
	-@$(AGY_BIN) update
	@systemctl --user restart $(SERVICE_NAME) 2>/dev/null \
		&& echo "restarted $(SERVICE_NAME)" || echo "unit not running"

doctor:
	@echo "agy binary      : $(AGY_BIN) $$($(AGY_BIN) --version 2>/dev/null || echo '(missing)')"
	@echo -n "unit installed  : "; test -f $(HOME_DIR)/.config/systemd/user/$(SERVICE_NAME).service \
		&& echo yes || echo "no (run 'make start')"
	@echo    "unit active     : $$(systemctl --user is-active $(SERVICE_NAME) 2>/dev/null || echo inactive)"
	@echo    "instance name   : $(AGY_RC_NAME)"
	@echo    "workspace       : $(AGY_RC_WORKDIR)"

clean: stop
	@rm -f *.log
