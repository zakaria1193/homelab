# aicli - one place every homelab caller reaches `claude` and `agy`.
#
# `aicli.py` is the command (no unit needed - callers exec it directly). This
# Makefile's systemd half ships `server.py`, the localhost-only HTTP service
# that fronts both CLIs with an OpenAI-compatible chat-completions endpoint
# for text callers like ai-job-search. See ticket homelab-0013.
SERVICE_NAME = aicli-ai
UNIT_TEMPLATE = aicli.service.template
PYTHON_BIN ?= $(shell which python3)
UNIT_SED = -e "s|{{PYTHON_BIN}}|$(PYTHON_BIN)|g"
include $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../../common.mk

LINK := $(HOME_DIR)/.local/bin/aicli

.PHONY: help install test upgrade env-setup start stop restart status logs clean print-units

help:
	@echo "aicli"
	@echo "====="
	@echo "  make install  - Link $(LINK) -> aicli.py"
	@echo "  make test     - Run aicli's unit tests (fake CLI only, no real quota)"
	@echo "  make start    - Start the aicli-ai HTTP service via systemd"
	@echo "  make status   - Check status of the aicli-ai service"
	@echo "  make logs     - View live logs of the aicli-ai service"
	@echo "  make upgrade  - Pull latest changes and restart the service"
	@echo "  make stop     - Stop the aicli-ai service and clean up systemd files"

print-units:
	@echo $(SERVICE_NAME)

install:
	@if [ -z "$(PYTHON_BIN)" ]; then echo "Error: python3 not found on PATH."; exit 1; fi
	@mkdir -p $(HOME_DIR)/.local/bin
	@chmod +x aicli.py
	@ln -sf $(CURDIR)/aicli.py $(LINK)
	@echo "[OK] $(LINK) -> $(CURDIR)/aicli.py"

test:
	@python3 -m unittest discover -s tests -v

upgrade:
	@git -C $(CURR_DIR)/../../.. pull
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
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop
