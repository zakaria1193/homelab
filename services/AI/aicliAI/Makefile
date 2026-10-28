# aicli - one place every homelab caller reaches `claude` and `agy`.
#
# aicli's code lives in its own repo (AICLI_DIR, github.com/zakaria1193/aicli).
# This folder is the homelab side, the same split as pjmAI: the systemd unit
# for `server.py` (the localhost-only OpenAI-compatible service, unit
# aicli-ai), its git-crypt encrypted .env, and homelab's aicli config
# (aicli.toml - the tracked defaults for every class, client and the OptiPlex
# project list). `make install` links aicli.toml into ~/.config/aicli/, where
# every caller's `aicli` finds it, and creates the untracked route-override
# state file (~/.local/state/aicli/routes.json) the cockpit's AI Routes tab
# and `aicli route` write to live. See tickets homelab-0013, homelab-0019.
SERVICE_NAME = aicli-ai
UNIT_TEMPLATE = aicli.service.template
PYTHON_BIN ?= $(shell which python3)
AICLI_DIR ?= $(HOME)/my_repos/aicli
AICLI_REPO ?= https://github.com/zakaria1193/aicli.git
UNIT_SED = -e "s|{{PYTHON_BIN}}|$(PYTHON_BIN)|g" -e "s|{{AICLI_DIR}}|$(AICLI_DIR)|g"
# common.mk defines targets; keep a bare `make` on help, not systemd-render.
.DEFAULT_GOAL := help
include $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../../common.mk

LINK := $(HOME_DIR)/.local/bin/aicli
USER_CONFIG_DIR := $(HOME_DIR)/.config/aicli
STATE_DIR := $(HOME_DIR)/.local/state/aicli
STATE_ROUTES := $(STATE_DIR)/routes.json

.PHONY: help install test test-tokens upgrade env-setup start stop restart status logs clean print-units

help:
	@echo "aicli (code in $(AICLI_DIR))"
	@echo "====="
	@echo "  make install  - Clone aicli to $(AICLI_DIR) if missing, link $(LINK) and"
	@echo "                  this folder's aicli.toml into $(USER_CONFIG_DIR); create"
	@echo "                  the untracked override state file at $(STATE_ROUTES)"
	@echo "  make test     - Run aicli's unit tests (fake CLI only, no real quota)"
	@echo "  make test-tokens - Verify AICLI_API_KEY against the running service"
	@echo "  make start    - Start the aicli-ai HTTP service via systemd"
	@echo "  make status   - Check status of the aicli-ai service"
	@echo "  make logs     - View live logs of the aicli-ai service"
	@echo "  make upgrade  - Pull homelab and aicli, then restart the service"
	@echo "  make stop     - Stop the aicli-ai service and clean up systemd files"

print-units:
	@echo $(SERVICE_NAME)

install:
	@if [ -z "$(PYTHON_BIN)" ]; then echo "Error: python3 not found on PATH."; exit 1; fi
	@if [ ! -d $(AICLI_DIR)/.git ]; then git clone $(AICLI_REPO) $(AICLI_DIR); fi
	@$(MAKE) --no-print-directory -C $(AICLI_DIR) install LINK=$(LINK) PYTHON=$(PYTHON_BIN)
	@mkdir -p $(USER_CONFIG_DIR)
	@ln -sfn $(CURR_DIR)/aicli.toml $(USER_CONFIG_DIR)/aicli.toml
	@if [ -L $(USER_CONFIG_DIR)/routes.json ]; then rm -f $(USER_CONFIG_DIR)/routes.json; fi
	@mkdir -p $(STATE_DIR)
	@if [ ! -f $(STATE_ROUTES) ]; then echo '{}' > $(STATE_ROUTES); fi
	@echo "[OK] $(USER_CONFIG_DIR)/aicli.toml -> $(CURR_DIR)/aicli.toml; overrides in $(STATE_ROUTES)"

test:
	@$(MAKE) --no-print-directory -C $(AICLI_DIR) test

# `make test` stays offline; this hits the running service, and also checks
# the AICLI_API_KEY / karakeep OPENAI_API_KEY invariant CLAUDE.md §5 requires
# (loopback requests skip the key, so reaching the service proves nothing
# about the key itself - only the equality check does).
test-tokens: env-setup
	@python3 $(CURR_DIR)/../../status/test_tokens.py --env $(CURR_DIR)/.env --strict
	@$(MAKE) --no-print-directory -C $(AICLI_DIR) check-quota
	@aicli_key=$$(grep -h '^AICLI_API_KEY=' $(CURR_DIR)/.env | cut -d= -f2-); \
	karakeep_key=$$(grep -h '^OPENAI_API_KEY=' $(CURR_DIR)/../../karakeep/.env | cut -d= -f2-); \
	if [ -z "$$aicli_key" ]; then \
		echo "[FAIL] AICLI_API_KEY is empty."; exit 1; \
	elif [ "$$aicli_key" != "$$karakeep_key" ]; then \
		echo "[FAIL] AICLI_API_KEY does not match karakeep's OPENAI_API_KEY."; exit 1; \
	else \
		echo "[PASS] AICLI_API_KEY matches karakeep's OPENAI_API_KEY."; \
	fi

# `restart` re-renders the unit and installs first. The first upgrade after
# aicli moved out of homelab runs the old Makefile's `pull` then `$(MAKE)
# restart`, which reads this file: that clones aicli, makes the
# ~/.config/aicli links and points the unit at $(AICLI_DIR)/server.py. Later
# runs find all three in place.
upgrade:
	@git -C $(CURR_DIR)/../../.. pull --autostash
	@$(MAKE) --no-print-directory install
	@git -C $(AICLI_DIR) pull
	@$(MAKE) --no-print-directory restart
	@echo "[OK] Upgrade complete."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi

# Streamlined user aliases
start: install env-setup systemd-setup
	@grep -h '^AICLI_\(HOST\|PORT\)=' .env | sed 's/^/    /'
stop: systemd-stop
restart: install systemd-setup
status: systemd-status
logs: systemd-logs
clean: stop
