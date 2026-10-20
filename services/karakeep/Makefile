# Karakeep stack (docker compose): karakeep web, meilisearch, chrome.
# Wraps `docker compose` following the AGENTS.md §2 interface as far as it
# fits a compose stack. See README.md.

SHELL := /bin/bash
HERE := $(shell cd "$(dir $(lastword $(MAKEFILE_LIST)))" && pwd)
ROOT := $(shell cd "$(HERE)/../.." && pwd)
PROJECT := karakeep

# Docker on this host is the snap, at /snap/bin/docker; cron's default PATH
# may not include it.
DOCKER := $(shell command -v docker 2>/dev/null || { [ -x /snap/bin/docker ] && echo /snap/bin/docker; })
COMPOSE = $(DOCKER) compose --project-directory $(HERE) -f $(HERE)/docker-compose.yml -p $(PROJECT)

.PHONY: help start status logs upgrade stop clean verify test test-tokens

help:
	@echo "Karakeep stack (docker compose) - $(PROJECT)"
	@echo "============================================"
	@echo "  make start    - docker compose up -d"
	@echo "  make status   - docker compose ps"
	@echo "  make logs     - docker compose logs -f"
	@echo "  make upgrade  - pull images, recreate changed containers, then verify"
	@echo "                  (skips a stack stopped on purpose - no containers)"
	@echo "  make stop     - docker compose down"
	@echo "  make clean    - alias of stop"
	@echo "  make verify   - assert every service has a running, healthy container"

start:
	@$(COMPOSE) up -d

status:
	@$(COMPOSE) ps

logs:
	@$(COMPOSE) logs -f

upgrade:
	@DOCKER_BIN="$(DOCKER)" $(ROOT)/tools/compose-upgrade.sh $(HERE) $(PROJECT)

stop:
	@$(COMPOSE) down

clean: stop

verify:
	@DOCKER_BIN="$(DOCKER)" $(ROOT)/tools/compose-verify.sh $(HERE) $(PROJECT)

# `make test` stays offline: agents run it unattended, and these tokens are
# home-IP restricted or rate limited. The live check is `make test-tokens`.
test:
	@echo "No offline tests here; the live credential check is 'make test-tokens'."

test-tokens:
	@python3 $(ROOT)/services/status/test_tokens.py --env $(HERE)/.env --strict
