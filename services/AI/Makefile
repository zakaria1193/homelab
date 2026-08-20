# Homelab AI Services Master Makefile
# Coordinates status and upgrading for all AI services

.PHONY: help status upgrade upgrade-paperclip upgrade-hermes upgrade-acpx upgrade-openhands upgrade-ai-job-search upgrade-arrmcp

help:
	@echo "Homelab AI Services Orchestrator"
	@echo "================================"
	@echo "  make status    - Check status of all AI services"
	@echo "  make upgrade   - Upgrade all AI services (paperclip, hermes, acpx, openhands, ai-job-search, arrmcp)"

status:
	@echo "=== Paperclip AI ==="
	-@$(MAKE) -C paperclipAI status
	@echo "=== Hermes AI ==="
	-@$(MAKE) -C hermesAI status
	@echo "=== ACPX AI ==="
	-@$(MAKE) -C acpxAI status
	@echo "=== OpenHands AI ==="
	-@$(MAKE) -C openhandsAI status
	@echo "=== AI Job Search ==="
	-@$(MAKE) -C ai-job-search/daemon status
	@echo "=== arr-mcp AI ==="
	-@$(MAKE) -C arrMcpAI status

upgrade: upgrade-paperclip upgrade-hermes upgrade-acpx upgrade-openhands upgrade-ai-job-search upgrade-arrmcp
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

upgrade-acpx:
	@echo "------------------------------------------"
	@echo "=== Upgrading ACPX AI ==="
	@echo "------------------------------------------"
	-@$(MAKE) -C acpxAI upgrade

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

