# Media stack (docker compose): Jellyfin, Sonarr, Radarr, Chaptarr,
# Prowlarr, FlareSolverr, Transmission. Wraps `docker compose` following the
# AGENTS.md §2 interface as far as it fits a compose stack. See README.md.

SHELL := /bin/bash
HERE := $(shell cd "$(dir $(lastword $(MAKEFILE_LIST)))" && pwd)
ROOT := $(shell cd "$(HERE)/../.." && pwd)
PROJECT := media

# Transmission is paused when free space on the downloads disk drops under this
# (see disk_guard.py); override per host in .env as DISK_GUARD_MIN_FREE_GB.
MIN_FREE_GB ?= 100
PYTHON_BIN ?= $(shell command -v python3 2>/dev/null || echo /usr/bin/python3)
TIMER_UNIT = media-disk-guard
TIMER_SED  = -e "s|{{PYTHON_BIN}}|$(PYTHON_BIN)|g"
include $(HERE)/../common.mk

# Docker on this host is the snap, at /snap/bin/docker; cron's default PATH
# may not include it.
DOCKER := $(shell command -v docker 2>/dev/null || { [ -x /snap/bin/docker ] && echo /snap/bin/docker; })
COMPOSE = $(DOCKER) compose --project-directory $(HERE) -f $(HERE)/docker-compose.yml -p $(PROJECT)

.PHONY: help install start status logs upgrade stop clean verify guard-start guard-stop guard-status test

help:
	@echo "Media stack (docker compose) - $(PROJECT)"
	@echo "========================================="
	@echo "  make install  - check docker/compose/python3, validate the file, pull images"
	@echo "  make start    - docker compose up -d"
	@echo "  make status   - docker compose ps"
	@echo "  make logs     - docker compose logs -f"
	@echo "  make upgrade  - pull images, recreate changed containers, then verify"
	@echo "                  (skips a stack stopped on purpose - no containers)"
	@echo "  make stop     - docker compose down"
	@echo "  make clean    - alias of stop"
	@echo "  make verify   - assert every service has a running, healthy container"
	@echo "  make guard-status - disk guard timer + last log lines (floor: $(MIN_FREE_GB) GB free)"
	@echo "  make test     - disk guard tests"

install:
	@if [ -z "$(DOCKER)" ]; then echo "Error: docker not found on PATH."; exit 1; fi
	@$(DOCKER) compose version >/dev/null || { echo "Error: 'docker compose' plugin not available."; exit 1; }
	@command -v python3 >/dev/null || { echo "Error: python3 not found on PATH (needed by the disk guard)."; exit 1; }
	@$(COMPOSE) config -q
	@$(COMPOSE) pull
	@echo "[OK] Install complete (no containers started)."

start:
	@$(COMPOSE) up -d
	@$(MAKE) --no-print-directory guard-start

status:
	@$(COMPOSE) ps

logs:
	@$(COMPOSE) logs -f

upgrade:
	@DOCKER_BIN="$(DOCKER)" $(ROOT)/tools/compose-upgrade.sh $(HERE) $(PROJECT)

stop:
	@$(COMPOSE) down
	@$(MAKE) --no-print-directory guard-stop

clean: stop

verify:
	@DOCKER_BIN="$(DOCKER)" $(ROOT)/tools/compose-verify.sh $(HERE) $(PROJECT)

# ------------------------------------------------------------- disk guard

env-setup:
	@:

guard-start: timer-setup
	@echo "(floor $(MIN_FREE_GB) GB free)"
guard-stop: timer-stop
guard-status: timer-status
	@tail -n 5 $(HERE)/disk_guard.log 2>/dev/null || echo "(no log yet)"

test:
	@python3 $(HERE)/tests/test_disk_guard.py
