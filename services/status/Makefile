# Homelab Cockpit Service Automation Makefile
SERVICE_NAME = homelab-status
# Owns the tmux server holding every cockpit shell, so the cockpit can restart
# without taking the sessions with it. See tmux-server.service.template.
TMUX_SERVICE_NAME = tmux-server
TMUX_BIN ?= $(shell which tmux 2>/dev/null || echo /usr/bin/tmux)
TMUX_START_CMD = if sudo -n true 2>/dev/null; then sudo systemctl restart $(TMUX_SERVICE_NAME); \
	else systemctl --user restart $(TMUX_SERVICE_NAME); fi
USER = $(shell whoami)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
RUNTIME_DIR = /run/user/$(shell id -u)

REPO_ROOT = $(shell dirname $$(dirname $(CURR_DIR)))

STATUS_HOST ?= 0.0.0.0
STATUS_PORT ?= 8300
PYTHON_BIN ?= $(shell which python3 2>/dev/null || echo /usr/bin/python3)

# Slack ideas bot: a companion unit that writes to the same Obsidian board.
SLACK_BOT_SERVICE = slack-ideas-bot
SLACK_ENV = $(HOME)/.config/homelab/slack.env
UV_BIN ?= $(shell which uv 2>/dev/null || echo $(HOME)/.local/bin/uv)

.PHONY: help install upgrade setup env-setup check start stop restart status logs clean test \
	systemd-setup systemd-stop systemd-status systemd-restart systemd-logs \
	tmux-setup tmux-adopt tmux-status tmux-stop tmux-ai-install tmux-ai-uninstall attach \
	slack-bot-start slack-bot-stop slack-bot-status slack-bot-logs

help:
	@echo "Homelab Cockpit Service Automation"
	@echo "==========================================="
	@echo "  make install   - Verify runtime prerequisites (python3 stdlib only)"
	@echo "  make start     - Serve the cockpit on http://$(STATUS_HOST):$(STATUS_PORT) via systemd"
	@echo "  make status    - Check daemon status"
	@echo "  make logs      - View live daemon logs"
	@echo "  make upgrade   - Reload the cockpit after config or code changes"
	@echo "  make stop      - Stop the daemon and remove the systemd unit"
	@echo "  make check     - Print a one-shot status snapshot to the terminal"
	@echo "  make test      - Assert cockpit shells survive a cockpit restart"
	@echo "  make attach    - Attach to a cockpit tmux session from this terminal"
	@echo "  make tmux-status - Show the $(TMUX_SERVICE_NAME) unit and its sessions"
	@echo "  make tmux-stop - Stop that unit (KILLS every shell) and remove it"
	@echo "  make slack-bot-start  - Install & start the Slack ideas bot (/idea -> Obsidian board)"
	@echo "  make slack-bot-status - Show the bot's unit status"
	@echo "  make slack-bot-logs   - Follow the bot's logs"
	@echo "  make slack-bot-stop   - Stop the bot and remove its unit"

# Streamlined user aliases
start: env-setup tmux-setup systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install:
	@echo "Checking prerequisites..."
	@$(PYTHON_BIN) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' \
		|| { echo "[ERROR] python3 >= 3.7 is required ($(PYTHON_BIN))"; exit 1; }
	@echo "  python3: $$($(PYTHON_BIN) --version)"
	@command -v systemctl >/dev/null 2>&1 && echo "  systemctl: found" \
		|| echo "  [WARN] systemctl missing - systemd checks will report 'unknown'"
	@command -v docker >/dev/null 2>&1 && echo "  docker: found" \
		|| echo "  [WARN] docker missing - container checks will report 'unknown'"
	@echo "[OK] No external packages needed; the cockpit uses the Python standard library."

upgrade: install
	@echo "Validating services.conf..."
	@$(PYTHON_BIN) $(CURR_DIR)/status_server.py --once >/dev/null
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user restart $(SERVICE_NAME); \
	elif sudo -n true 2>/dev/null && sudo systemctl is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		sudo systemctl restart $(SERVICE_NAME); \
	fi
	@echo "[OK] Upgrade complete."

env-setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi

setup: env-setup install
	@echo "Homelab Cockpit environment setup completed."

check:
	@$(PYTHON_BIN) $(CURR_DIR)/status_server.py --once

systemd-setup: env-setup
	@echo "Creating systemd service file for $(SERVICE_NAME)..."
	@mkdir -p ~/.config/systemd/user
	@echo "[Unit]" > $(SERVICE_NAME).service
	@echo "Description=Homelab Cockpit" >> $(SERVICE_NAME).service
	@echo "After=network.target network-online.target $(TMUX_SERVICE_NAME).service" >> $(SERVICE_NAME).service
	@echo "Wants=network-online.target $(TMUX_SERVICE_NAME).service" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Service]" >> $(SERVICE_NAME).service
	@echo "Type=simple" >> $(SERVICE_NAME).service
	@echo "User=$(USER)" >> $(SERVICE_NAME).service
	@echo "WorkingDirectory=$(CURR_DIR)" >> $(SERVICE_NAME).service
	@echo "Environment=\"PATH=$(PATH_VAL)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"XDG_RUNTIME_DIR=$(RUNTIME_DIR)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"STATUS_HOST=$(STATUS_HOST)\"" >> $(SERVICE_NAME).service
	@echo "Environment=\"STATUS_PORT=$(STATUS_PORT)\"" >> $(SERVICE_NAME).service
	@echo "EnvironmentFile=-$(CURR_DIR)/.env" >> $(SERVICE_NAME).service
	@echo "ExecStart=$(PYTHON_BIN) $(CURR_DIR)/status_server.py" >> $(SERVICE_NAME).service
	@echo "Restart=always" >> $(SERVICE_NAME).service
	@echo "RestartSec=5" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Install]" >> $(SERVICE_NAME).service
	@echo "WantedBy=default.target multi-user.target" >> $(SERVICE_NAME).service
	@if sudo -n true 2>/dev/null; then \
		echo "Installing as system service via sudo..."; \
		sudo mv $(SERVICE_NAME).service /etc/systemd/system/; \
		sudo systemctl daemon-reload; \
		sudo systemctl enable $(SERVICE_NAME); \
		sudo systemctl restart $(SERVICE_NAME); \
	else \
		echo "Installing as user systemd service (~/.config/systemd/user)..."; \
		mv $(SERVICE_NAME).service ~/.config/systemd/user/; \
		systemctl --user daemon-reload; \
		systemctl --user enable $(SERVICE_NAME); \
		systemctl --user restart $(SERVICE_NAME); \
		loginctl enable-linger $(USER) >/dev/null 2>&1 || true; \
	fi
	@echo "[OK] Homelab Cockpit served on http://$(STATUS_HOST):$(STATUS_PORT)"

# --------------------------------------------------------------- tmux ----- #
# The tmux server holding the cockpit's shells runs under its own unit. Whoever
# starts the server owns it, and systemd kills a unit's whole cgroup on stop -
# so while status_server.py started it, every `make upgrade` killed the shells.

tmux-setup:
	@command -v $(TMUX_BIN) >/dev/null 2>&1 || { echo "[WARN] tmux missing - cockpit shells will not persist"; exit 0; }
	@echo "Creating systemd service file for $(TMUX_SERVICE_NAME)..."
	@mkdir -p ~/.config/systemd/user
	@echo "[Unit]" > $(TMUX_SERVICE_NAME).service
	@echo "Description=tmux server for homelab cockpit shells" >> $(TMUX_SERVICE_NAME).service
	@echo "" >> $(TMUX_SERVICE_NAME).service
	@echo "[Service]" >> $(TMUX_SERVICE_NAME).service
	@echo "Type=exec" >> $(TMUX_SERVICE_NAME).service
	@echo "User=$(USER)" >> $(TMUX_SERVICE_NAME).service
	@echo "WorkingDirectory=$(HOME_DIR)" >> $(TMUX_SERVICE_NAME).service
	@echo "Environment=\"PATH=$(PATH_VAL)\"" >> $(TMUX_SERVICE_NAME).service
	@echo "Environment=\"XDG_RUNTIME_DIR=$(RUNTIME_DIR)\"" >> $(TMUX_SERVICE_NAME).service
	@echo "ExecStart=$(TMUX_BIN) -D" >> $(TMUX_SERVICE_NAME).service
	@echo "ExecStop=$(TMUX_BIN) kill-server" >> $(TMUX_SERVICE_NAME).service
	@echo "Restart=always" >> $(TMUX_SERVICE_NAME).service
	@echo "RestartSec=30" >> $(TMUX_SERVICE_NAME).service
	@echo "" >> $(TMUX_SERVICE_NAME).service
	@echo "[Install]" >> $(TMUX_SERVICE_NAME).service
	@echo "WantedBy=default.target multi-user.target" >> $(TMUX_SERVICE_NAME).service
	@if sudo -n true 2>/dev/null; then \
		sudo mv $(TMUX_SERVICE_NAME).service /etc/systemd/system/; \
		sudo systemctl daemon-reload; \
		sudo systemctl enable $(TMUX_SERVICE_NAME) >/dev/null 2>&1; \
	else \
		mv $(TMUX_SERVICE_NAME).service ~/.config/systemd/user/; \
		systemctl --user daemon-reload; \
		systemctl --user enable $(TMUX_SERVICE_NAME) >/dev/null 2>&1; \
		loginctl enable-linger $(USER) >/dev/null 2>&1 || true; \
	fi
	@if systemctl is-active --quiet $(TMUX_SERVICE_NAME) 2>/dev/null \
		|| systemctl --user is-active --quiet $(TMUX_SERVICE_NAME) 2>/dev/null; then \
		echo "[OK] $(TMUX_SERVICE_NAME) already owns the tmux socket"; \
	elif $(TMUX_BIN) ls >/dev/null 2>&1; then \
		echo "[WARN] another tmux server already holds $${TMUX_TMPDIR:-/tmp}/tmux-$$(id -u)/default:"; \
		$(TMUX_BIN) ls 2>/dev/null | sed "s/^/         /"; \
		echo "       Those sessions stay where they are. Run 'make tmux-adopt' to move"; \
		echo "       ownership to systemd - it KILLS them first, so do it when idle."; \
	else \
		$(TMUX_START_CMD); \
		echo "[OK] $(TMUX_SERVICE_NAME) owns the tmux socket; cockpit shells survive restarts"; \
	fi

# Kill whatever holds the socket, then hand it to systemd. Destroys sessions.
tmux-adopt:
	@echo "Killing the current tmux server (all sessions) and handing the socket to systemd..."
	-@$(TMUX_BIN) kill-server 2>/dev/null
	@$(TMUX_START_CMD)
	@echo "[OK] $(TMUX_SERVICE_NAME) owns the tmux socket"

tmux-status:
	-@systemctl status $(TMUX_SERVICE_NAME) --no-pager 2>/dev/null \
		|| systemctl --user status $(TMUX_SERVICE_NAME) --no-pager
	@echo ""
	-@$(TMUX_BIN) ls 2>/dev/null || echo "(no sessions)"

# Stopping this unit kills every shell it holds - the cockpit's and yours.
tmux-stop:
	@echo "Stopping $(TMUX_SERVICE_NAME) - this kills every tmux session:"
	-@$(TMUX_BIN) ls 2>/dev/null | sed "s/^/  /"
	-@if systemctl --user is-enabled --quiet $(TMUX_SERVICE_NAME) 2>/dev/null; then \
		systemctl --user stop $(TMUX_SERVICE_NAME); \
		systemctl --user disable $(TMUX_SERVICE_NAME); \
		rm -f ~/.config/systemd/user/$(TMUX_SERVICE_NAME).service; \
		systemctl --user daemon-reload; \
	fi
	-@if sudo -n true 2>/dev/null; then \
		sudo systemctl stop $(TMUX_SERVICE_NAME) 2>/dev/null; \
		sudo systemctl disable $(TMUX_SERVICE_NAME) 2>/dev/null; \
		sudo rm -f /etc/systemd/system/$(TMUX_SERVICE_NAME).service; \
		sudo systemctl daemon-reload; \
	fi

tmux-ai-install:
	@echo "Installing AI CLI tmux session wrappers (agy & claude)..."
	@sudo -n ln -sf $(REPO_ROOT)/tools/optiplex-ai-tmux.sh /usr/local/bin/agy 2>/dev/null || ln -sf $(REPO_ROOT)/tools/optiplex-ai-tmux.sh $(HOME)/.local/bin/agy-tmux
	@sudo -n ln -sf $(REPO_ROOT)/tools/optiplex-ai-tmux.sh /usr/local/bin/claude 2>/dev/null || ln -sf $(REPO_ROOT)/tools/optiplex-ai-tmux.sh $(HOME)/.local/bin/claude-tmux
	@echo "[OK] agy and claude now automatically run inside cockpit tmux sessions."

tmux-ai-uninstall:
	@echo "Removing AI CLI tmux session wrappers..."
	-@sudo -n rm -f /usr/local/bin/agy /usr/local/bin/claude
	@echo "[OK] Restored default binary lookup for agy and claude."

# Same sessions the browser terminal shows, from this terminal or over SSH.
attach:
	@if [ -n "$(SESSION)" ]; then \
		$(TMUX_BIN) attach -t "$(SESSION)" 2>/dev/null || $(TMUX_BIN) attach -t "cockpit-$(SESSION)"; \
	else \
		$(TMUX_BIN) ls 2>/dev/null || { echo "No tmux server running."; exit 1; }; \
		echo ""; \
		echo "Attach with: make attach SESSION=<name>   (or: tmux attach -t <name>)"; \
	fi

test:
	@for t in $(CURR_DIR)/tests/test_*.py; do python3 "$$t" || exit 1; done
	@$(CURR_DIR)/tests/test_tmux_persistence.sh

# Only the cockpit: the shells belong to $(TMUX_SERVICE_NAME) and stay up.
systemd-stop:
	@echo "Stopping service (tmux sessions survive; 'make tmux-stop' ends those)..."
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

systemd-status:
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null || systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user status $(SERVICE_NAME) --no-pager; \
	elif sudo -n true 2>/dev/null; then \
		sudo systemctl status $(SERVICE_NAME) --no-pager; \
	else \
		systemctl --user status $(SERVICE_NAME) --no-pager 2>/dev/null || echo "[INFO] Service '$(SERVICE_NAME)' is not running. Run 'make start' to launch it."; \
	fi

systemd-restart:
	@if systemctl --user is-enabled --quiet $(SERVICE_NAME) 2>/dev/null; then \
		systemctl --user restart $(SERVICE_NAME); \
	else \
		sudo systemctl restart $(SERVICE_NAME); \
	fi

systemd-logs:
	@if systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		journalctl --user -u $(SERVICE_NAME) -n 30 -f; \
	else \
		sudo journalctl -u $(SERVICE_NAME) -n 30 -f; \
	fi

# ------------------------------------------------------- Slack ideas bot --- #
# Socket Mode needs no public URL. The Slack app itself (slash command /idea,
# Socket Mode, app_mention + message.im events) is configured on api.slack.com.

slack-bot-start:
	@test -f $(SLACK_ENV) || { echo "[ERROR] $(SLACK_ENV) missing (needs SLACK_BOT_TOKEN, SLACK_APP_TOKEN)"; exit 1; }
	@grep -Eq '^SLACK_APP_TOKEN=["'"'"']?xapp-' $(SLACK_ENV) || { echo "[ERROR] SLACK_APP_TOKEN (xapp-...) missing from $(SLACK_ENV)"; exit 1; }
	@test -x $(UV_BIN) || { echo "[ERROR] uv not found ($(UV_BIN)); it provides slack-bolt"; exit 1; }
	@echo "Rendering $(SLACK_BOT_SERVICE).service..."
	@sed -e 's|{{USER}}|$(USER)|g' -e 's|{{DIR}}|$(CURR_DIR)|g' -e 's|{{HOME}}|$(HOME_DIR)|g' \
		-e 's|{{PATH}}|$(PATH_VAL)|g' -e 's|{{UV_BIN}}|$(UV_BIN)|g' \
		$(CURR_DIR)/$(SLACK_BOT_SERVICE).service.template | grep -v '^# ' > $(SLACK_BOT_SERVICE).service
	@if sudo -n true 2>/dev/null; then \
		echo "Installing as system service via sudo..."; \
		sudo mv $(SLACK_BOT_SERVICE).service /etc/systemd/system/; \
		sudo systemctl daemon-reload; \
		sudo systemctl enable $(SLACK_BOT_SERVICE); \
		sudo systemctl restart $(SLACK_BOT_SERVICE); \
	else \
		echo "Installing as user systemd service (~/.config/systemd/user)..."; \
		mkdir -p ~/.config/systemd/user; \
		sed '/^User=/d' $(SLACK_BOT_SERVICE).service > ~/.config/systemd/user/$(SLACK_BOT_SERVICE).service; \
		rm -f $(SLACK_BOT_SERVICE).service; \
		systemctl --user daemon-reload; \
		systemctl --user enable $(SLACK_BOT_SERVICE); \
		systemctl --user restart $(SLACK_BOT_SERVICE); \
		loginctl enable-linger $(USER) >/dev/null 2>&1 || true; \
	fi
	@echo "[OK] $(SLACK_BOT_SERVICE) started - try /idea in Slack ('make slack-bot-logs' to watch)"

slack-bot-stop:
	-@if systemctl --user is-enabled --quiet $(SLACK_BOT_SERVICE) 2>/dev/null || systemctl --user is-active --quiet $(SLACK_BOT_SERVICE) 2>/dev/null; then \
		systemctl --user disable --now $(SLACK_BOT_SERVICE); \
		rm -f ~/.config/systemd/user/$(SLACK_BOT_SERVICE).service; \
		systemctl --user daemon-reload; \
	fi
	-@if sudo -n true 2>/dev/null && [ -f /etc/systemd/system/$(SLACK_BOT_SERVICE).service ]; then \
		sudo systemctl disable --now $(SLACK_BOT_SERVICE); \
		sudo rm -f /etc/systemd/system/$(SLACK_BOT_SERVICE).service; \
		sudo systemctl daemon-reload; \
	fi
	@echo "[OK] $(SLACK_BOT_SERVICE) stopped and removed"

slack-bot-status:
	@if [ -f ~/.config/systemd/user/$(SLACK_BOT_SERVICE).service ]; then \
		systemctl --user status $(SLACK_BOT_SERVICE) --no-pager; \
	elif [ -f /etc/systemd/system/$(SLACK_BOT_SERVICE).service ]; then \
		systemctl status $(SLACK_BOT_SERVICE) --no-pager; \
	else \
		echo "[INFO] $(SLACK_BOT_SERVICE) is not installed. Run 'make slack-bot-start'."; \
	fi

slack-bot-logs:
	@if [ -f ~/.config/systemd/user/$(SLACK_BOT_SERVICE).service ]; then \
		journalctl --user -u $(SLACK_BOT_SERVICE) -n 50 -f; \
	else \
		sudo journalctl -u $(SLACK_BOT_SERVICE) -n 50 -f; \
	fi
