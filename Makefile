# Homelab root Makefile - runs every offline test in the repo from one
# target, so nothing but the weekly cron (services/AI/Makefile `upgrade`)
# tests whether a change broke something.
.PHONY: help test

HERE := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

help:
	@echo "Homelab repo"
	@echo "============"
	@echo "  make test  - Run every service's 'test' target, every tools/tests/test_*.sh,"
	@echo "               and tools/cron-manager/test_cron_manager.py. Offline; never"
	@echo "               restarts a live service. Keeps going after a failure, prints a"
	@echo "               pass/fail summary, exits non-zero if any suite failed."

# A service directory is picked up here only if its own Makefile has a
# `test:` rule - discovered with `find`, not a hardcoded list, so a new
# service's tests run without editing this file. `-not -path '*/node_modules/*'`
# keeps vendored trees (e.g. a Node service's dependencies) out of the search.
test:
	@fail=0; failed_list=""; summary=""; \
	for mk in $$(find $(HERE)/services -name Makefile -not -path '*/node_modules/*' | sort); do \
		dir=$$(dirname "$$mk"); \
		rel=$${dir#$(HERE)/}; \
		if ! grep -q '^test:' "$$mk"; then continue; fi; \
		echo "------------------------------------------"; \
		echo "=== make -C $$rel test ==="; \
		echo "------------------------------------------"; \
		if $(MAKE) -C "$$dir" --no-print-directory test; then \
			summary="$$summary  $$rel  PASS\n"; \
		else \
			summary="$$summary  $$rel  FAIL\n"; \
			fail=$$((fail+1)); failed_list="$$failed_list $$rel"; \
		fi; \
	done; \
	for t in $(HERE)/tools/tests/test_*.sh; do \
		rel=$${t#$(HERE)/}; \
		echo "------------------------------------------"; \
		echo "=== $$rel ==="; \
		echo "------------------------------------------"; \
		if "$$t"; then \
			summary="$$summary  $$rel  PASS\n"; \
		else \
			summary="$$summary  $$rel  FAIL\n"; \
			fail=$$((fail+1)); failed_list="$$failed_list $$rel"; \
		fi; \
	done; \
	echo "------------------------------------------"; \
	echo "=== tools/cron-manager/test_cron_manager.py ==="; \
	echo "------------------------------------------"; \
	if python3 $(HERE)/tools/cron-manager/test_cron_manager.py; then \
		summary="$$summary  tools/cron-manager/test_cron_manager.py  PASS\n"; \
	else \
		summary="$$summary  tools/cron-manager/test_cron_manager.py  FAIL\n"; \
		fail=$$((fail+1)); failed_list="$$failed_list tools/cron-manager/test_cron_manager.py"; \
	fi; \
	echo "=========================================="; \
	echo "Test summary"; \
	echo "=========================================="; \
	printf "$$summary"; \
	if [ $$fail -eq 0 ]; then \
		echo "[OK] All test suites passed"; \
	else \
		echo "[FAIL] $$fail suite(s) failed:$$failed_list"; \
	fi; \
	exit $$fail
