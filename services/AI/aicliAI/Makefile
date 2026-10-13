# aicli - one place every homelab caller reaches `claude` and `agy`.
#
# `aicli.py` is the command (no unit needed - callers exec it directly). This
# Makefile's systemd half ships `server.py`, the localhost-only HTTP service
# that fronts both CLIs with an OpenAI-compatible chat-completions endpoint
# for text callers like ai-job-search. See ticket homelab-0013.
SERVICE_NAME = aicli-ai
HOME_DIR = $(HOME)
LINK := $(HOME_DIR)/.local/bin/aicli
USER = $(shell whoami)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(shell pwd)
PYTHON_BIN ?= $(shell which python3)

.PHONY: help install test upgrade env-setup start stop restart status logs clean systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

help:
	@echo "aicli"
	@echo "====="
	@echo "  make install  - Link $(LINK) -> aicli.py"
	@echo "  make test     - Run aicli's unit tests (fake CLI only, no real quota)"
	@echo "  make start    - Start the aicli-ai HTTP service via systemd"
	@echo "  make status   - Check status of the aicli-ai service"
	@echo "  make logs     - View live logs of the aicli-ai service"
	@echo "  make upgrade  - Pull latest changes and restart the service"
	@echo "  make stop     - Stop the aicli-ai service and clean up systemd files"

install:
	@mkdir -p $(HOME_DIR)/.local/bin
	@chmod +x aicli.py
	@ln -sf $(CURDIR)/aicli.py $(LINK)
	@echo "[OK] $(LINK) -> $(CURDIR)/aicli.py"

test:
	@python3 -m unittest discover -s tests -v

upgrade:
	@git -C $(CURR_DIR)/../../.. pull
	@$(MAKE) --no-print-directory restart
	@echo "[OK] Upgrade complete."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi

# Streamlined user aliases
start: install env-setup systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

systemd-setup: env-setup
	@if [ -z "$(PYTHON_BIN)" ]; then echo "Error: python3 not found on PATH."; exit 1; fi
	@echo "Generating systemd unit file..."
	@USER_LINE="User=$(USER)"; \
	if ! sudo -n true 2>/dev/null; then USER_LINE=""; fi; \
	sed -e "s|{{USER_LINE}}|$$USER_LINE|g" \
	    -e "s|{{CURR_DIR}}|$(CURR_DIR)|g" \
	    -e "s|{{PATH_VAL}}|$(PATH_VAL)|g" \
	    -e "s|{{PYTHON_BIN}}|$(PYTHON_BIN)|g" \
	    aicli.service.template > $(SERVICE_NAME).service
	@if sudo -n true 2>/dev/null; then \
		echo "Installing as system service via sudo..."; \
		sudo mv $(SERVICE_NAME).service /etc/systemd/system/; \
		sudo systemctl daemon-reload; \
		sudo systemctl enable $(SERVICE_NAME); \
		sudo systemctl restart $(SERVICE_NAME); \
	else \
		echo "Installing as user systemd service (~/.config/systemd/user)..."; \
		mkdir -p ~/.config/systemd/user; \
		mv $(SERVICE_NAME).service ~/.config/systemd/user/; \
		systemctl --user daemon-reload; \
		systemctl --user enable $(SERVICE_NAME); \
		systemctl --user restart $(SERVICE_NAME); \
	fi
	@echo "[OK] Service $(SERVICE_NAME) started successfully."
	@grep -h '^AICLI_\(HOST\|PORT\)=' .env | sed 's/^/    /'

systemd-stop:
	@echo "Stopping service..."
	-@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null || systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user stop $(SERVICE_NAME); \
		systemctl --user disable $(SERVICE_NAME); \
		rm -f ~/.config/systemd/user/$(SERVICE_NAME).service; \
		systemctl --user daemon-reload; \
	fi
	-@if sudo -n true 2>/dev/null; then \
		sudo systemctl stop $(SERVICE_NAME) 2>/dev/null; \
		sudo systemctl disable $(SERVICE_NAME) 2>/dev/null; \
		sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service; \
		sudo systemctl daemon-reload; \
	fi
	@echo "[OK] Service stopped and unit file removed."

systemd-status:
	@echo "=== aicli-ai Status ==="
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null || systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user status $(SERVICE_NAME) --no-pager; \
	elif sudo -n true 2>/dev/null; then \
		sudo systemctl status $(SERVICE_NAME) --no-pager; \
	else \
		systemctl --user status $(SERVICE_NAME) --no-pager 2>/dev/null || echo "[INFO] Service '$(SERVICE_NAME)' is not running."; \
	fi

systemd-restart:
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user restart $(SERVICE_NAME); \
	else \
		sudo systemctl restart $(SERVICE_NAME); \
	fi

systemd-logs:
	@echo "Streaming logs (press Ctrl+C to stop)..."
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		journalctl --user -u $(SERVICE_NAME) -n 30 -f; \
	else \
		sudo journalctl -u $(SERVICE_NAME) -n 30 -f; \
	fi
