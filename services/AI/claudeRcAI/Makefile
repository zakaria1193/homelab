# Claude Remote Control (`claude rc`) Service Automation Makefile
#
# One `claude remote-control` process serves exactly one directory, so a second
# always-on workspace means a second instance. Pass INSTANCE=<name> to every
# target to act on it:
#
#   make start                     -> claude-rc-ai            reading .env
#   make start INSTANCE=myrepos    -> claude-rc-ai-myrepos    reading .env.myrepos
#
# Instances are otherwise identical - same targets, same unit layout - so
# adding a workspace is a new .env.<name>, never a new Makefile.
INSTANCE ?=
SUFFIX := $(if $(INSTANCE),-$(INSTANCE),)
SERVICE_NAME = claude-rc-ai$(SUFFIX)
UNIT_TEMPLATE = claude-rc-ai.service.template
ENV_FILE := .env$(if $(INSTANCE),.$(INSTANCE),)

# Local overrides live in $(ENV_FILE) (RC_* keys only - no secrets here, Remote
# Control authenticates with the credentials already stored in ~/.claude).
#
# Seed it here rather than from the env-setup recipe: make expands `include` at
# parse time, so a file created by a recipe would arrive one run too late and
# the unit would be generated from the defaults instead.
$(shell test -f $(ENV_FILE) || cp $(ENV_FILE).example $(ENV_FILE) 2>/dev/null)
-include $(ENV_FILE)

# Repository the Remote Control server runs in (defaults to this repo's root).
RC_WORKDIR ?= $(abspath $(CURR_DIR)/../../..)
RC_SPAWN_MODE ?= worktree
RC_CAPACITY ?= 32
RC_PERMISSION_MODE ?= auto
RC_SESSION_PREFIX ?= homelab
RC_SESSION_NAME ?= homelab
# Path for verbose Remote Control debug logs
RC_DEBUG_FILE ?= $(CURR_DIR)/claude-rc$(SUFFIX).log
CLAUDE_BIN ?= $(shell which claude 2>/dev/null || echo $(HOME_DIR)/.local/bin/claude)
SHELL_BIN ?= $(shell getent passwd $(USER) | cut -d: -f7)

RC_DEBUG_ARG = $(if $(strip $(RC_DEBUG_FILE)),--debug-file $(strip $(RC_DEBUG_FILE)),)
RC_ARGS = remote-control --spawn $(RC_SPAWN_MODE) --capacity $(RC_CAPACITY) \
	--permission-mode $(RC_PERMISSION_MODE) --name $(RC_SESSION_NAME) \
	--remote-control-session-name-prefix $(RC_SESSION_PREFIX) --create-session-in-dir $(RC_DEBUG_ARG)

UNIT_SED = -e "s|{{RC_WORKDIR}}|$(RC_WORKDIR)|g" \
	   -e "s|{{SHELL_BIN}}|$(SHELL_BIN)|g" \
	   -e "s|{{RC_SESSION_PREFIX}}|$(RC_SESSION_PREFIX)|g" \
	   -e "s|{{ENV_FILE}}|$(ENV_FILE)|g" \
	   -e "s|{{CLAUDE_BIN}}|$(CLAUDE_BIN)|g" \
	   -e "s|{{RC_ARGS}}|$(RC_ARGS)|g"
include $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../../common.mk

.PHONY: help install upgrade setup env-setup start stop restart status logs clean doctor print-units

# Bare unit names this service owns: the default instance, then one per
# .env.<name> / .env.<name>.example found here (.env and .env.example are the
# default instance, not a named one). Ignores INSTANCE - always the full set.
print-units:
	@echo $(SERVICE_NAME)
	@for f in .env.*; do \
		[ -e "$$f" ] || continue; \
		[ "$$f" = ".env.example" ] && continue; \
		name=$${f#.env.}; \
		case "$$name" in *.example) name=$${name%.example} ;; esac; \
		echo "$$name"; \
	done | sort -u | sed 's/^/claude-rc-ai-/'

help:
	@echo "Claude Remote Control AI Service Automation"
	@echo "==========================================="
	@echo "  make install   - Install / repair the Claude Code native CLI"
	@echo "  make start     - Run 'claude remote-control' continuously in $(RC_WORKDIR)"
	@echo "  make status    - Check systemd service status"
	@echo "  make logs      - View live systemd logs"
	@echo "  make upgrade   - Upgrade the Claude Code CLI and restart the daemon"
	@echo "  make stop      - Stop the daemon and remove the systemd unit"
	@echo ""
	@echo "  Instance:   $(SERVICE_NAME)  (INSTANCE=$(INSTANCE), env $(ENV_FILE))"
	@echo "  Workspace:  $(RC_WORKDIR)"
	@echo "  Spawn mode: $(RC_SPAWN_MODE)  |  Capacity: $(RC_CAPACITY)  |  Permissions: $(RC_PERMISSION_MODE)"
	@echo ""
	@echo "  Instances here:  (default) $(patsubst .env.%,%,$(filter-out %.example,$(wildcard .env.*)))"
	@echo "  Connect from https://claude.ai/code or the Claude mobile app."

# Streamlined user aliases
start: env-setup systemd-setup
	@echo "[OK] Remote Control running in $(RC_WORKDIR) (spawn=$(RC_SPAWN_MODE))."
	@echo "     Connect from https://claude.ai/code or the Claude mobile app."
stop: systemd-stop
# Re-render the unit so .env edits (spawn mode, capacity...) apply; the flags
# are baked into ExecStart, so a bare systemctl restart would keep the old ones.
restart: systemd-setup
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@echo "Installing / verifying the Claude Code native CLI..."
	@if command -v claude >/dev/null 2>&1; then \
		claude install stable; \
	else \
		curl -fsSL https://claude.ai/install.sh | bash; \
	fi
	@echo "[OK] Installation complete: $$($(CLAUDE_BIN) --version 2>/dev/null || echo 'claude not on PATH')"

# Restarts every active unit this service owns (default plus named instances),
# not just $(SERVICE_NAME) - an upgrade must not leave a named instance on the
# old binary until the next reboot. Scope (user vs system) is detected per
# unit, same as summary/verify.
upgrade:
	@echo "Upgrading the Claude Code CLI..."
	-@$(CLAUDE_BIN) update
	@for unit in $$($(MAKE) -s --no-print-directory print-units); do \
		if systemctl --user is-active --quiet "$$unit" 2>/dev/null; then \
			systemctl --user restart "$$unit"; \
		elif sudo -n true 2>/dev/null && sudo systemctl is-active --quiet "$$unit" 2>/dev/null; then \
			sudo systemctl restart "$$unit"; \
		fi; \
	done
	@echo "[OK] Upgrade complete."

# The file itself is seeded at parse time (see above); this target reports
# and fails loudly when there is no template to seed it from, and refuses a
# worktree spawn mode against a workspace that is not a git repo.
env-setup:
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "[ERROR] no $(ENV_FILE) and no $(ENV_FILE).example to create it from."; \
		echo "        For a new instance, write .env.<name>.example first."; \
		exit 1; \
	fi
	@if [ "$(RC_SPAWN_MODE)" = "worktree" ] && [ ! -d "$(RC_WORKDIR)/.git" ]; then \
		echo "[ERROR] $(RC_WORKDIR) is not a git repository; '--spawn worktree' requires one."; \
		echo "        Use RC_SPAWN_MODE=same-dir for a workspace that is not its own repo."; \
		exit 1; \
	fi
	@echo "Using $(ENV_FILE) (workspace $(RC_WORKDIR), spawn $(RC_SPAWN_MODE))"

setup: env-setup install

doctor:
	@echo "Workspace: $(RC_WORKDIR)"
	@$(CLAUDE_BIN) doctor || true
