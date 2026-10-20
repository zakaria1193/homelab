# Homelab AI Services Master Makefile
# Coordinates status and upgrading for all AI services

.PHONY: help status summary verify print-units test upgrade upgrade-hermes upgrade-openhands upgrade-ai-job-search upgrade-arrmcp upgrade-playwright-mcp upgrade-claude-rc upgrade-antigravity-rc upgrade-aicli upgrade-media upgrade-karakeep upgrade-docker install-skills test-tokens test-tokens-notify

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../..)
MEDIA_DIR := $(ROOT)/services/media
KARAKEEP_DIR := $(ROOT)/services/karakeep
# Overridable so a test can point the weekly token alert at a stub.
SLACK_NOTIFY ?= $(ROOT)/tools/slackbot-notify.sh

# Same channel the cockpit's own health alerts use (the # must be escaped in make).
SLACK_CHANNEL ?= \#homelab-alerts

help:
	@echo "Homelab AI Services Orchestrator"
	@echo "================================"
	@echo "  make status          - Check status of all AI services"
	@echo "  make summary         - One-line status summary of all AI services (no pager)"
	@echo "  make verify          - Assert every installed AI unit is actually running"
	@echo "  make print-units     - List the dir:unit registry (debugging)"
	@echo "  make upgrade         - Upgrade all AI services (hermes, openhands, ai-job-search, arrmcp, playwright-mcp, claude-rc, antigravity-rc, aicli), then the Docker stacks (media, karakeep)."
	@echo "                          Prints a pass/fail summary and warns #homelab-alerts if any sub-upgrade failed; exits non-zero on any failure (sub-upgrade or verify)."
	@echo "  make test-tokens     - Verify all homelab API tokens and credentials"
	@echo "  make test            - Run this directory's own test suite (no network, no real units)"
	@echo "  make install-skills  - Link shared AI skills to installed agents (~/.claude, ~/.gemini, etc.)"

install-skills:
	@./link-skills.sh


# The registry: every directory that owns one or more AI systemd units. Each
# gets a `print-units` target (see each service's Makefile) that prints its
# bare unit name(s), one per line - named Remote Control / Playwright MCP
# instances included, pjm (code lives in ../../../pjm) included. A new AI
# service joins this list and adds its own `print-units` target; nothing else
# here needs to change.
AI_SERVICE_DIRS = hermesAI openhandsAI ai-job-search/daemon arrMcpAI playwrightMcpAI claudeRcAI antigravityRcAI aicliAI pjmAI
# `dir:unit` pairs, one per line, flattened to a space-separated list by
# `$(shell ...)`. A directory with no Makefile (e.g. a submodule that is not
# checked out) and a Makefile whose `print-units` prints nothing both come out
# as `dir:` with an empty unit; summary/verify tell those two apart by
# checking for the Makefile themselves, since that is a filesystem fact, not
# something worth encoding here. Lazy (`=`), so `make help` does not shell out
# for it.
AI_SERVICE_UNITS = $(shell for d in $(AI_SERVICE_DIRS); do \
	units="$$($(MAKE) -s --no-print-directory -C $$d print-units 2>/dev/null)"; \
	if [ -z "$$units" ]; then echo "$$d:"; \
	else printf '%s\n' "$$units" | while IFS= read -r u; do echo "$$d:$$u"; done; fi; \
done)

# For debugging and for services/AI/tests: the same `dir:unit` pairs `summary`
# and `verify` walk, one per line.
print-units:
	@for entry in $(AI_SERVICE_UNITS); do echo "$$entry"; done

SUMMARY_FMT = '%-22s %-20s %-7s %-18s %-9s %s\n'

summary:
	@printf $(SUMMARY_FMT) SERVICE UNIT SCOPE ACTIVE ENABLED UPTIME
	@export XDG_RUNTIME_DIR="$${XDG_RUNTIME_DIR:-/run/user/$$(id -u)}"; \
	for entry in $(AI_SERVICE_UNITS); do \
		dir=$${entry%%:*}; unit=$${entry#*:}; \
		if [ -z "$$unit" ]; then \
			if [ -f "$$dir/Makefile" ]; then \
				printf $(SUMMARY_FMT) "$$dir" "-" "-" "no-units" "-" "-"; \
			else \
				printf $(SUMMARY_FMT) "$$dir" "-" "-" "not-present" "-" "-"; \
			fi; \
			continue; \
		fi; \
		if systemctl --user cat "$$unit" >/dev/null 2>&1; then scope=user; sc=--user; \
		elif systemctl cat "$$unit" >/dev/null 2>&1; then scope=system; sc=; \
		else printf $(SUMMARY_FMT) "$$dir" "$$unit" "-" "not-installed" "-" "-"; continue; fi; \
		state="$$(systemctl $$sc show -p ActiveState --value "$$unit" 2>/dev/null)"; \
		sub="$$(systemctl $$sc show -p SubState --value "$$unit" 2>/dev/null)"; \
		enabled="$$(systemctl $$sc show -p UnitFileState --value "$$unit" 2>/dev/null)"; \
		mono="$$(systemctl $$sc show -p ActiveEnterTimestampMonotonic --value "$$unit" 2>/dev/null)"; \
		up="$$(cut -d' ' -f1 /proc/uptime)"; \
		uptime="$$(awk -v m="$$mono" -v u="$$up" 'BEGIN { if (m + 0 <= 0) { print "-"; exit } s = u - m / 1000000; if (s < 0) s = 0; d = int(s / 86400); h = int(s % 86400 / 3600); mi = int(s % 3600 / 60); if (d > 0) printf "%dd%dh", d, h; else if (h > 0) printf "%dh%dm", h, mi; else printf "%dm", mi }')"; \
		printf $(SUMMARY_FMT) "$$dir" "$$unit" "$$scope" "$${state:-unknown}($${sub:-?})" "$${enabled:--}" "$$uptime"; \
	done

status:
	@for d in $(AI_SERVICE_DIRS); do \
		echo "=== $$d ==="; \
		if [ -f "$$d/Makefile" ]; then $(MAKE) -C "$$d" status; else echo "(not present)"; fi; \
	done

# Post-upgrade gate. `upgrade` used to print "[OK] All AI services upgraded
# successfully." unconditionally: every sub-target is `-@$(MAKE) -C ...`, so
# make ignores their exit status, and nothing ever looked at the units. On
# 2026-09-06 a new paperclipai release raised its Node floor above the host's,
# so the service upgraded cleanly, then refused to boot and sat in a restart
# loop for seventeen hours behind an "[OK]".
#
# So check the only thing that actually answers "did the upgrade work": is the
# unit running now. A unit that is absent, or installed but deliberately
# disabled, is reported and skipped - anything enabled and not running is a
# hard failure that exits non-zero, which is what makes the weekly cron and its
# logfile tell the truth.
VERIFY_FMT = '  %-22s %-20s %s\n'
# Restarted units need a moment; poll rather than judging them mid-restart.
VERIFY_SETTLE_SECS ?= 30
# A plain `make verify` only looks: no agy healing, no Slack, no image prune.
# `make upgrade` turns both on for its closing verify.
AUTO_HEAL ?= 0
PRUNE ?= 0

verify:
	@export XDG_RUNTIME_DIR="$${XDG_RUNTIME_DIR:-/run/user/$$(id -u)}"; \
	echo "=========================================="; \
	echo "Verifying every installed AI unit is running"; \
	echo "=========================================="; \
	fail=0; ok=0; skipped=0; failed_units=""; \
	for entry in $(AI_SERVICE_UNITS); do \
		dir=$${entry%%:*}; unit=$${entry#*:}; \
		if [ -z "$$unit" ]; then \
			if [ -f "$$dir/Makefile" ]; then \
				printf $(VERIFY_FMT) "$$dir" "-" "FAIL  (no units listed)"; \
				fail=$$((fail+1)); failed_units="$$failed_units $$dir:no-units"; \
			else \
				printf $(VERIFY_FMT) "$$dir" "-" "SKIP  (not present)"; \
				skipped=$$((skipped+1)); \
			fi; \
			continue; \
		fi; \
		if systemctl --user cat "$$unit" >/dev/null 2>&1; then sc=--user; \
		elif systemctl cat "$$unit" >/dev/null 2>&1; then sc=; \
		else \
			printf $(VERIFY_FMT) "$$dir" "$$unit" "SKIP  (not installed)"; \
			skipped=$$((skipped+1)); continue; \
		fi; \
		deadline=$$(( $$(date +%s) + $(VERIFY_SETTLE_SECS) )); \
		while :; do \
			state="$$(systemctl $$sc show -p ActiveState --value "$$unit" 2>/dev/null)"; \
			sub="$$(systemctl $$sc show -p SubState --value "$$unit" 2>/dev/null)"; \
			[ "$$state" = "active" ] && break; \
			[ "$$(date +%s)" -ge "$$deadline" ] && break; \
			sleep 2; \
		done; \
		enabled="$$(systemctl $$sc show -p UnitFileState --value "$$unit" 2>/dev/null)"; \
		if [ "$$state" = "active" ]; then \
			printf $(VERIFY_FMT) "$$dir" "$$unit" "OK    ($$sub)"; ok=$$((ok+1)); \
		elif [ "$$enabled" = "disabled" ] || [ "$$enabled" = "masked" ]; then \
			printf $(VERIFY_FMT) "$$dir" "$$unit" "SKIP  ($$enabled, $$state)"; \
			skipped=$$((skipped+1)); \
		else \
			printf $(VERIFY_FMT) "$$dir" "$$unit" "FAIL  ($$state/$$sub)"; \
			fail=$$((fail+1)); failed_units="$$failed_units $$unit"; \
		fi; \
	done; \
	echo "=========================================="; \
	units_ok=0; \
	if [ "$$fail" -gt 0 ]; then \
		units_ok=1; \
		echo "[FAIL] $$fail AI service(s) NOT running - $$ok ok, $$skipped skipped."; \
		echo "       Not running:$$failed_units"; \
		echo "       Diagnose:    journalctl -u <unit> -n 50 --no-pager"; \
	else \
		echo "[OK] All AI services upgraded and running - $$ok ok, $$skipped skipped."; \
	fi; \
	echo "=========================================="; \
	echo "Verifying Docker stacks (media, karakeep)"; \
	echo "=========================================="; \
	docker_out="$$(PRUNE=$(PRUNE) $(ROOT)/tools/docker-stacks-prune-gate.sh "$$units_ok" $(MEDIA_DIR) $(KARAKEEP_DIR) 2>&1)"; \
	docker_ok=$$?; \
	echo "$$docker_out"; \
	failed_containers="$$(echo "$$docker_out" | sed -n 's/^\[FAIL\] failed containers:[[:space:]]*//p')"; \
	echo "=========================================="; \
	if [ "$$units_ok" -ne 0 ] || [ "$$docker_ok" -ne 0 ]; then \
		if [ -z "$$failed_units$$failed_containers" ]; then \
			echo "[FAIL] AI services and/or Docker stacks not all running after upgrade"; \
			echo "       The Docker check failed without naming a container (docker missing, broken compose file?)."; \
			[ "$(AUTO_HEAL)" = "1" ] && $(ROOT)/tools/slackbot-notify.sh --title "AI Services Upgrade Failure" --status error \
				"The Docker stacks could not be verified after the upgrade, and no container was named, so nothing was healed. See services/AI/upgrade.log."; \
			exit 1; \
		elif [ -x "$(ROOT)/tools/auto-heal-and-notify.sh" ] && [ "$(AUTO_HEAL)" = "1" ]; then \
			$(ROOT)/tools/auto-heal-and-notify.sh "$$failed_units" "$$failed_containers"; \
		else \
			echo "[FAIL] AI services and/or Docker stacks not all running after upgrade"; \
			exit 1; \
		fi; \
	else \
		echo "[OK] AI services and Docker stacks upgraded and running"; \
	fi

# Run every sub-upgrade in order, recording each one's exit status instead of
# swallowing it (that `-@$(MAKE) ...` silence is the bug: a failed npm/uv
# upgrade or `compose pull` went unreported and the old version kept running
# with nobody told). A failed sub-upgrade does not stop the ones after it.
# The closing verify and the token check always run; verify's exit status is
# recorded too, so `upgrade` fails if either a sub-upgrade or verify failed -
# a stack skipped because it was stopped on purpose counts as success. A failed
# token check only alerts Slack (test-tokens-notify); it never sets the exit code.
# pjm is checked by summary, verify, status and print-units, but left out of
# UPGRADE_TARGETS on purpose: pjm runs the agents, so it is upgraded on its own
# (`make -C pjmAI upgrade`).
UPGRADE_TARGETS = upgrade-hermes upgrade-openhands upgrade-ai-job-search upgrade-arrmcp upgrade-playwright-mcp upgrade-claude-rc upgrade-antigravity-rc upgrade-aicli upgrade-media upgrade-karakeep

upgrade:
	@fail=0; failed_list=""; summary=""; \
	for t in $(UPGRADE_TARGETS); do \
		$(MAKE) --no-print-directory $$t; rc=$$?; \
		if [ $$rc -eq 0 ]; then \
			summary="$$summary  $$t  OK\n"; \
		else \
			summary="$$summary  $$t  FAIL (exit $$rc)\n"; \
			fail=$$((fail+1)); \
			if [ -z "$$failed_list" ]; then failed_list="$$t"; else failed_list="$$failed_list $$t"; fi; \
		fi; \
	done; \
	$(MAKE) --no-print-directory verify AUTO_HEAL=1 PRUNE=1; verify_rc=$$?; \
	$(MAKE) --no-print-directory test-tokens-notify || true; \
	echo "=========================================="; \
	echo "Upgrade summary"; \
	echo "=========================================="; \
	printf "$$summary"; \
	if [ $$fail -eq 0 ]; then \
		echo "[OK] All sub-upgrades succeeded"; \
	else \
		echo "[FAIL] $$fail sub-upgrade(s) failed: $$failed_list"; \
		if [ -x "$(ROOT)/tools/slackbot-notify.sh" ]; then \
			"$(ROOT)/tools/slackbot-notify.sh" --channel "$(SLACK_CHANNEL)" --status warn \
				--title "Weekly upgrade: sub-upgrade failed" \
				"$$failed_list - old version may still be running, see services/AI/upgrade.log" \
				|| echo "[WARN] could not send the Slack alert"; \
		else \
			echo "[WARN] tools/slackbot-notify.sh not found - no Slack alert sent"; \
		fi; \
	fi; \
	[ $$fail -eq 0 ] && [ $$verify_rc -eq 0 ]

test-tokens:
	@$(MAKE) -C $(ROOT)/services/status test-tokens

# The weekly run's exit code is never this one's: `upgrade` records the
# sub-upgrades' and verify's statuses itself and ignores this target's result,
# whatever the token check says. VERIFY_STATUS only drives this target's own
# exit so a test can check it ("the step's exit code follows verify") without
# running the real upgrade or verify.
VERIFY_STATUS ?= 0

test-tokens-notify:
	@output="$$($(MAKE) --no-print-directory test-tokens 2>&1)"; status=$$?; \
	echo "$$output"; \
	if [ $$status -ne 0 ]; then \
		fail_lines="$$(printf '%s\n' "$$output" | grep '\[FAIL\]')"; \
		$(SLACK_NOTIFY) --channel "$(SLACK_CHANNEL)" --title "Token check failed" --status error "$$fail_lines" || \
			echo "[WARN] slackbot-notify.sh failed to send the token-check alert"; \
	fi; \
	exit $(VERIFY_STATUS)

test:
	@bash tests/run.sh
	@for t in $(ROOT)/services/AI/tests/test_*.py; do python3 "$$t" || exit 1; done

upgrade-hermes:
	@echo "------------------------------------------"
	@echo "=== Upgrading Hermes AI ==="
	@echo "------------------------------------------"
	@$(MAKE) -C hermesAI upgrade

upgrade-openhands:
	@echo "------------------------------------------"
	@echo "=== Upgrading OpenHands AI ==="
	@echo "------------------------------------------"
	@$(MAKE) -C openhandsAI upgrade

upgrade-ai-job-search:
	@echo "------------------------------------------"
	@echo "=== Upgrading AI Job Search ==="
	@echo "------------------------------------------"
	@$(MAKE) -C ai-job-search/daemon upgrade

upgrade-arrmcp:
	@echo "------------------------------------------"
	@echo "=== Upgrading arr-mcp AI ==="
	@echo "------------------------------------------"
	@$(MAKE) -C arrMcpAI upgrade

upgrade-playwright-mcp:
	@echo "------------------------------------------"
	@echo "=== Upgrading Playwright MCP AI ==="
	@echo "------------------------------------------"
	@$(MAKE) -C playwrightMcpAI upgrade

upgrade-claude-rc:
	@echo "------------------------------------------"
	@echo "=== Upgrading Claude Remote Control AI ==="
	@echo "------------------------------------------"
	@$(MAKE) -C claudeRcAI upgrade

upgrade-antigravity-rc:
	@echo "------------------------------------------"
	@echo "=== Upgrading Antigravity Remote Control AI ==="
	@echo "------------------------------------------"
	@$(MAKE) -C antigravityRcAI upgrade

upgrade-aicli:
	@echo "------------------------------------------"
	@echo "=== Upgrading aicli AI ==="
	@echo "------------------------------------------"
	@$(MAKE) -C aicliAI upgrade

upgrade-media:
	@echo "------------------------------------------"
	@echo "=== Upgrading media (Docker) ==="
	@echo "------------------------------------------"
	@$(MAKE) -C $(MEDIA_DIR) upgrade

upgrade-karakeep:
	@echo "------------------------------------------"
	@echo "=== Upgrading karakeep (Docker) ==="
	@echo "------------------------------------------"
	@$(MAKE) -C $(KARAKEEP_DIR) upgrade

# Kept for anyone calling it by hand; `upgrade` itself calls upgrade-media and
# upgrade-karakeep directly so each stack gets its own recorded result.
upgrade-docker: upgrade-media upgrade-karakeep
