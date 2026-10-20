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
GUARD := media-disk-guard
PYTHON_BIN ?= $(shell command -v python3 2>/dev/null || echo /usr/bin/python3)

# Docker on this host is the snap, at /snap/bin/docker; cron's default PATH
# may not include it.
DOCKER := $(shell command -v docker 2>/dev/null || { [ -x /snap/bin/docker ] && echo /snap/bin/docker; })
COMPOSE = $(DOCKER) compose --project-directory $(HERE) -f $(HERE)/docker-compose.yml -p $(PROJECT)

.PHONY: help start status logs upgrade stop clean verify guard-start guard-stop guard-status test

help:
	@echo "Media stack (docker compose) - $(PROJECT)"
	@echo "========================================="
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

guard-start:
	@for u in $(GUARD).service $(GUARD).timer; do \
		sed -e "s|{{USER}}|$$(whoami)|g" -e "s|{{CURR_DIR}}|$(HERE)|g" \
		    -e "s|{{PYTHON_BIN}}|$(PYTHON_BIN)|g" $(HERE)/$$u.template > $(HERE)/$$u; \
	done
	@if command sudo -n true 2>/dev/null; then \
		command sudo mv $(HERE)/$(GUARD).service $(HERE)/$(GUARD).timer /etc/systemd/system/; \
		command sudo systemctl daemon-reload; \
		command sudo systemctl enable --now $(GUARD).timer; \
	else \
		mkdir -p ~/.config/systemd/user; \
		mv $(HERE)/$(GUARD).service $(HERE)/$(GUARD).timer ~/.config/systemd/user/; \
		systemctl --user daemon-reload; \
		systemctl --user enable --now $(GUARD).timer; \
		loginctl enable-linger $$(whoami) >/dev/null 2>&1 || true; \
	fi
	@echo "[OK] Disk guard timer installed (floor $(MIN_FREE_GB) GB)."

guard-stop:
	-@systemctl --user disable --now $(GUARD).timer 2>/dev/null; \
		rm -f ~/.config/systemd/user/$(GUARD).service ~/.config/systemd/user/$(GUARD).timer; \
		systemctl --user daemon-reload 2>/dev/null; true
	-@if command sudo -n true 2>/dev/null; then \
		command sudo systemctl disable --now $(GUARD).timer 2>/dev/null; \
		command sudo rm -f /etc/systemd/system/$(GUARD).service /etc/systemd/system/$(GUARD).timer; \
		command sudo systemctl daemon-reload; \
	fi

guard-status:
	@systemctl list-timers $(GUARD).timer --no-pager; systemctl --user list-timers $(GUARD).timer --no-pager 2>/dev/null | grep -i guard || true
	@tail -n 5 $(HERE)/disk_guard.log 2>/dev/null || echo "(no log yet)"

test:
	@python3 $(HERE)/tests/test_disk_guard.py
