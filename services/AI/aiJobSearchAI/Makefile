# ai-job-search service automation (homelab side).
#
# ai-job-search's code lives in its own repo (AI_JOB_SEARCH_DIR). This folder holds what
# homelab keeps per service: the git-crypt encrypted .env, the standard make targets and
# the docs. The systemd unit is rendered by ai-job-search's own Makefile, pointed at this .env.
# The unit ai-job-search's own Makefile installs; services/AI's summary and verify read it.
SERVICE_NAME = ai-job-search
CURR_DIR = $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
ROOT = $(abspath $(CURR_DIR)/../../..)
AI_JOB_SEARCH_DIR ?= $(HOME)/my_repos/ai-job-search
AI_JOB_SEARCH_REPO ?= git@github.com:zakaria1193/ai-job-search.git
ENV_FILE = $(CURR_DIR)/.env
AI_JOB_SEARCH = $(MAKE) -C $(AI_JOB_SEARCH_DIR) ENV_FILE=$(ENV_FILE)
PORT = $(shell sed -n 's/^PORT=//p' $(ENV_FILE) 2>/dev/null | tail -1 | grep . || echo 8200)

.PHONY: help install upgrade env-setup start stop restart status logs clean check test test-tokens \
        systemd-setup systemd-stop systemd-status systemd-restart systemd-logs print-units

help:
	@echo "AI Job Search Service Automation"
	@echo "================================"
	@echo "  make install   - Clone ai-job-search to $(AI_JOB_SEARCH_DIR) if missing and check dependencies"
	@echo "  make start     - Create .env, install the systemd unit, start ai-job-search on http://<host>:$(PORT)"
	@echo "  make status    - Check daemon status"
	@echo "  make logs      - Follow daemon logs"
	@echo "  make upgrade   - git pull ai-job-search, check dependencies, restart"
	@echo "  make stop      - Stop the daemon and remove the systemd unit"
	@echo "  make check     - Check config and tests"

start: env-setup systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

print-units:
	@echo $(SERVICE_NAME)

install:
	@if [ ! -d $(AI_JOB_SEARCH_DIR)/.git ]; then git clone $(AI_JOB_SEARCH_REPO) $(AI_JOB_SEARCH_DIR); fi
	@$(AI_JOB_SEARCH) install

env-setup:
	@if [ ! -f $(ENV_FILE) ]; then \
		cp $(CURR_DIR)/.env.example $(ENV_FILE); \
		echo "Created .env from .env.example"; \
	fi

systemd-setup: env-setup
	@$(AI_JOB_SEARCH) systemd-setup

systemd-stop:
	@$(AI_JOB_SEARCH) systemd-stop

systemd-restart:
	@$(AI_JOB_SEARCH) systemd-restart

systemd-status:
	@$(AI_JOB_SEARCH) systemd-status

systemd-logs:
	@$(AI_JOB_SEARCH) systemd-logs

upgrade:
	@$(AI_JOB_SEARCH) upgrade

check:
	@$(AI_JOB_SEARCH) check

test:
	@$(AI_JOB_SEARCH) test

test-tokens: env-setup
	@python3 $(ROOT)/services/status/test_tokens.py --env $(ENV_FILE) --strict
