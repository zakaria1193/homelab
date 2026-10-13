# aicli - one place every homelab caller reaches `claude` and `agy`.
#
# No systemd unit yet: that lands with the HTTP service (server.py), later in
# ticket homelab-0013. For now this just links the `aicli` command and runs
# its tests, same `make install`/`make test` interface every service has.
HOME_DIR = $(HOME)
LINK := $(HOME_DIR)/.local/bin/aicli

.PHONY: help install test

help:
	@echo "aicli"
	@echo "====="
	@echo "  make install  - Link $(LINK) -> aicli.py"
	@echo "  make test     - Run aicli's unit tests (fake CLI only, no real quota)"

install:
	@mkdir -p $(HOME_DIR)/.local/bin
	@chmod +x aicli.py
	@ln -sf $(CURDIR)/aicli.py $(LINK)
	@echo "[OK] $(LINK) -> $(CURDIR)/aicli.py"

test:
	@python3 -m unittest discover -s tests -v
