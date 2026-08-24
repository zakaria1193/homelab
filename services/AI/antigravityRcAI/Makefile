# Antigravity Remote Control (`agy --remote-control`) Service Automation Makefile
#
# The Claude counterpart in ../claudeRcAI runs one process per workspace, because
# one `claude remote-control` serves exactly one directory. Antigravity is not
# built that way: a single daemon exposes THIS MACHINE, and you pick the project
# from the web dashboard. So there is one instance here and no INSTANCE= knob.
#
# Upstream ships its own installer, which writes the systemd user unit, a
# port-probing wrapper and an auto-update timer. Rather than reimplement that
# (and drift from it), every target below drives the official script.
#
#   dashboard: https://antigravity.google.com
#   docs:      https://antigravity.google/docs/remote-control/
SERVICE_NAME = agy-remote-control
TIMER_NAME = agy-remote-control-update.timer
DAEMON_URL = https://antigravity.google/cli/agy-daemon.sh
DAEMON_SH = agy-daemon.sh
CURR_DIR = $(shell pwd)

# `systemctl --user` talks to the per-user bus over $XDG_RUNTIME_DIR. A recipe
# invoked from cron, from a parent Makefile or over a non-login SSH session
# inherits a bare environment and the call fails - which `doctor` would then
# report as "inactive" for a unit that is in fact running. Pin it the same way
# services/AI/Makefile does for `make summary`.
XDG_RUNTIME_DIR ?= /run/user/$(shell id -u)
export XDG_RUNTIME_DIR

# Seed .env at parse time, not from a recipe: make expands `include` before any
# recipe runs, so a file created by a recipe would arrive one run too late.
$(shell test -f .env || cp .env.example .env 2>/dev/null)
-include .env

AGY_RC_NAME ?= homelab
AGY_UPDATE_INTERVAL ?= daily
AGY_AUTO_UPDATE ?= 1
AGY_BIN ?= $(shell which agy 2>/dev/null || echo $(HOME)/.local/bin/agy)

INSTALL_ARGS = --name "$(AGY_RC_NAME)" --interval $(AGY_UPDATE_INTERVAL) \
	$(if $(filter 0,$(AGY_AUTO_UPDATE)),--no-auto-update,)

.PHONY: help install fetch start stop restart status logs upgrade doctor clean login

help:
	@echo "Antigravity Remote Control AI Service Automation"
	@echo "==============================================="
	@echo "  make install   - Fetch the official daemon installer and run it"
	@echo "                   (ONE-TIME interactive Google sign-in - needs a TTY)"
	@echo "  make start     - Start the always-on daemon"
	@echo "  make status    - Check systemd service status"
	@echo "  make logs      - View live systemd logs"
	@echo "  make upgrade   - Update the agy CLI and restart the daemon"
	@echo "  make stop      - Stop the daemon and remove the systemd unit"
	@echo "  make doctor    - Report what is and is not wired up"
	@echo ""
	@echo "  Unit:       $(SERVICE_NAME).service (systemd --user)"
	@echo "  Instance:   $(AGY_RC_NAME)"
	@echo "  Dashboard:  https://antigravity.google.com"

# Always re-fetch: upstream updates this script alongside the CLI, so a pinned
# copy would quietly rot. It is gitignored for the same reason.
fetch:
	@echo "==> Fetching $(DAEMON_URL)"
	@curl -fsSL $(DAEMON_URL) -o $(DAEMON_SH)
	@chmod +x $(DAEMON_SH)

install: fetch
	@# The sign-in prompt reads from the terminal; a piped or CI run would abort
	@# halfway and leave a crash-looping unit behind. Fail early and say so.
	@test -t 0 || { \
		echo "ERROR: 'make install' needs an interactive terminal."; \
		echo "       The daemon's one-time Google sign-in prints a URL and"; \
		echo "       waits for you to paste a code back."; \
		echo "       Run it from a real shell:  make -C $(CURR_DIR) install"; \
		exit 1; }
	@echo "==> Installing $(SERVICE_NAME) (instance: $(AGY_RC_NAME))"
	bash $(DAEMON_SH) install $(INSTALL_ARGS)
	@echo "==> Done. Machine should now appear at https://antigravity.google.com"

start:
	@systemctl --user start $(SERVICE_NAME) 2>/dev/null \
		|| { echo "Unit not installed yet - run 'make install' first."; exit 1; }
	@systemctl --user is-active $(SERVICE_NAME) >/dev/null \
		&& echo "$(SERVICE_NAME) is active" || echo "$(SERVICE_NAME) failed to start"

restart:
	systemctl --user restart $(SERVICE_NAME)

stop: fetch
	@echo "==> Stopping and removing $(SERVICE_NAME)"
	bash $(DAEMON_SH) uninstall

status:
	@systemctl --user --no-pager status $(SERVICE_NAME) || true
	@echo "--- auto-update timer ---"
	@systemctl --user --no-pager list-timers $(TIMER_NAME) 2>/dev/null || true

logs:
	journalctl --user -u $(SERVICE_NAME) -f

upgrade:
	@echo "==> Updating the agy CLI"
	$(AGY_BIN) update || echo "agy update failed; continuing with the current build"
	@systemctl --user restart $(SERVICE_NAME) 2>/dev/null \
		&& echo "restarted $(SERVICE_NAME)" || echo "unit not installed; nothing to restart"

# Re-run the interactive sign-in without touching the unit (token expired, or
# you switched Google accounts).
login: fetch
	bash $(DAEMON_SH) logout
	$(MAKE) install

doctor:
	@echo "agy binary      : $(AGY_BIN) $$($(AGY_BIN) --version 2>/dev/null || echo '(missing)')"
	@echo -n "unit installed  : "; test -f $(HOME)/.config/systemd/user/$(SERVICE_NAME).service \
		&& echo yes || echo "no  (run 'make install')"
	@echo    "unit active     : $$(systemctl --user is-active $(SERVICE_NAME) 2>/dev/null || echo inactive)"
	@echo    "instance name   : $$(sed -n 's/.*"cliRemoteControlHostname"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
		$(HOME)/.gemini/config/config.json 2>/dev/null | head -1 || true)"
	@echo    "hub port        : $$(ss -ltn 2>/dev/null | grep -oE '127.0.0.1:44[0-9][0-9]' | head -1 || true)"

clean:
	rm -f $(DAEMON_SH)
