# pjm service automation (homelab side).
#
# pjm's code lives in its own repo (PJM_DIR). This folder holds what homelab keeps per
# service: the git-crypt encrypted .env, the standard make targets and the docs. The
# systemd unit is rendered by pjm's own Makefile, pointed at this .env.
CURR_DIR = $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
PJM_DIR ?= $(HOME)/my_repos/pjm
PJM_REPO ?= https://github.com/zakaria1193/pjm.git
ENV_FILE = $(CURR_DIR)/.env
PJM = $(MAKE) -C $(PJM_DIR) ENV_FILE=$(ENV_FILE)
PORT = $(shell sed -n 's/^PJM_PORT=//p' $(ENV_FILE) 2>/dev/null | tail -1 | grep . || echo 8400)

.PHONY: help install upgrade env-setup start stop restart status logs clean check test \
        systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

help:
	@echo "pjm Service Automation"
	@echo "======================"
	@echo "  make install   - Clone pjm to $(PJM_DIR) if missing and check the host"
	@echo "  make start     - Create .env, install the systemd unit, start pjm on http://<host>:$(PORT)"
	@echo "  make status    - Check daemon status"
	@echo "  make logs      - Follow daemon logs"
	@echo "  make upgrade   - git pull pjm, run its tests, restart"
	@echo "  make stop      - Stop the daemon and remove the systemd unit"
	@echo "  make check     - Check config, tools and the data folder"

start: env-setup systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@if [ ! -d $(PJM_DIR)/.git ]; then git clone $(PJM_REPO) $(PJM_DIR); fi
	@$(PJM) install

env-setup:
	@if [ ! -f $(ENV_FILE) ]; then \
		cp $(CURR_DIR)/.env.example $(ENV_FILE); \
		echo "Created .env from .env.example"; \
	fi

systemd-setup: env-setup
	@$(PJM) systemd-setup

systemd-stop:
	@$(PJM) systemd-stop

systemd-restart:
	@$(PJM) systemd-restart

systemd-status:
	@$(PJM) systemd-status

systemd-logs:
	@$(PJM) systemd-logs

upgrade:
	@$(PJM) upgrade

check:
	@$(PJM) check

test:
	@$(PJM) test
