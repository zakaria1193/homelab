# Homelab AI Services Master Makefile
# Coordinates status and upgrading for all AI services

.PHONY: help status summary upgrade upgrade-paperclip upgrade-hermes upgrade-openhands upgrade-ai-job-search upgrade-arrmcp upgrade-playwright-mcp upgrade-claude-rc upgrade-antigravity-rc

help:
	@echo "Homelab AI Services Orchestrator"
	@echo "================================"
	@echo "  make status    - Check status of all AI services"
	@echo "  make summary   - One-line status summary of all AI services (no pager)"
	@echo "  make upgrade   - Upgrade all AI services (paperclip, hermes, openhands, ai-job-search, arrmcp, playwright-mcp, claude-rc, antigravity-rc)"

# One-line-per-service summary. Uses `systemctl show`, which never pages and
# never needs sudo, so it is safe to run non-interactively.
AI_SERVICE_DIRS = paperclipAI hermesAI openhandsAI ai-job-search/daemon arrMcpAI playwrightMcpAI claudeRcAI antigravityRcAI
# The trailing `cut` drops make-variable references such as the `$(SUFFIX)` in
# claudeRcAI's `SERVICE_NAME = claude-rc-ai$(SUFFIX)`. `$(shell ...)` output is
# not re-expanded by make, so that text reached /bin/sh verbatim and was read as
# command substitution - printing "SUFFIX: not found" and only landing on the
# right unit by accident. A systemd unit name is a literal, and the default
# instance - no INSTANCE= - is exactly the base name, which is what summary wants.
# Deliberately `cut` and not `sed`: make counts parentheses while matching
# `$(shell ...)`, so a bracket expression containing one would close it early.
unit_of = $(shell sed -n 's/^SERVICE_NAME[[:space:]]*[?:]*=[[:space:]]*//p' $(1)/Makefile 2>/dev/null | head -1 | cut -d'$$' -f1)
AI_SERVICE_UNITS = $(foreach d,$(AI_SERVICE_DIRS),$(d):$(call unit_of,$(d)))

SUMMARY_FMT = '%-22s %-20s %-7s %-18s %-9s %s\n'

summary:
	@printf $(SUMMARY_FMT) SERVICE UNIT SCOPE ACTIVE ENABLED UPTIME
	@export XDG_RUNTIME_DIR="$${XDG_RUNTIME_DIR:-/run/user/$$(id -u)}"; \
	for entry in $(AI_SERVICE_UNITS); do \
		dir=$${entry%%:*}; unit=$${entry##*:}; \
		if [ -z "$$unit" ]; then \
			printf $(SUMMARY_FMT) "$$dir" "-" "-" "no-makefile" "-" "-"; continue; \
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
	@echo "=== Paperclip AI ==="
	-@$(MAKE) -C paperclipAI status
	@echo "=== Hermes AI ==="
	-@$(MAKE) -C hermesAI status
	@echo "=== OpenHands AI ==="
	-@$(MAKE) -C openhandsAI status
	@echo "=== AI Job Search ==="
	-@$(MAKE) -C ai-job-search/daemon status
	@echo "=== arr-mcp AI ==="
	-@$(MAKE) -C arrMcpAI status
	@echo "=== Playwright MCP AI ==="
	-@$(MAKE) -C playwrightMcpAI status
	@echo "=== Claude Remote Control AI ==="
	-@$(MAKE) -C claudeRcAI status
	@echo "=== Antigravity Remote Control AI ==="
	-@$(MAKE) -C antigravityRcAI status

upgrade: upgrade-paperclip upgrade-hermes upgrade-openhands upgrade-ai-job-search upgrade-arrmcp upgrade-playwright-mcp upgrade-claude-rc upgrade-antigravity-rc
	@echo "=========================================="
	@echo "[OK] All AI services upgraded successfully."
	@echo "=========================================="

upgrade-paperclip:
	@echo "------------------------------------------"
	@echo "=== Upgrading Paperclip AI ==="
	@echo "------------------------------------------"
	-@$(MAKE) -C paperclipAI upgrade

upgrade-hermes:
	@echo "------------------------------------------"
	@echo "=== Upgrading Hermes AI ==="
	@echo "------------------------------------------"
	-@$(MAKE) -C hermesAI upgrade

upgrade-openhands:
	@echo "------------------------------------------"
	@echo "=== Upgrading OpenHands AI ==="
	@echo "------------------------------------------"
	-@$(MAKE) -C openhandsAI upgrade

upgrade-ai-job-search:
	@echo "------------------------------------------"
	@echo "=== Upgrading AI Job Search ==="
	@echo "------------------------------------------"
	-@$(MAKE) -C ai-job-search/daemon upgrade

upgrade-arrmcp:
	@echo "------------------------------------------"
	@echo "=== Upgrading arr-mcp AI ==="
	@echo "------------------------------------------"
	-@$(MAKE) -C arrMcpAI upgrade

upgrade-playwright-mcp:
	@echo "------------------------------------------"
	@echo "=== Upgrading Playwright MCP AI ==="
	@echo "------------------------------------------"
	-@$(MAKE) -C playwrightMcpAI upgrade

upgrade-claude-rc:
	@echo "------------------------------------------"
	@echo "=== Upgrading Claude Remote Control AI ==="
	@echo "------------------------------------------"
	-@$(MAKE) -C claudeRcAI upgrade

upgrade-antigravity-rc:
	@echo "------------------------------------------"
	@echo "=== Upgrading Antigravity Remote Control AI ==="
	@echo "------------------------------------------"
	-@$(MAKE) -C antigravityRcAI upgrade

