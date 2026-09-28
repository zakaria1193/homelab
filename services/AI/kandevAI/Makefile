# Kandev Service Automation Makefile
SERVICE_NAME = kandev
USER = $(shell whoami)
HOME_DIR = $(HOME)
PATH_VAL = $(shell echo $$PATH)
CURR_DIR = $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
# We run our fork (FORK.md in it explains why and how it stays rebase-able).
KANDEV_REPO ?= https://github.com/zakaria1193/kandev.git
KANDEV_BRANCH ?= main
KANDEV_SRC ?= $(HOME_DIR)/my_repos/kandev
BUNDLE_DIR ?= $(HOME_DIR)/.local/share/kandev-fork
KANDEV_BIN = $(BUNDLE_DIR)/bin/kandev
# Toolchain pinned by the fork's mise.toml, installed under ~/.local (no sudo).
GO_VERSION = 1.26.0
GO_DIR = $(HOME_DIR)/.local/go-$(GO_VERSION)
TOOLS_BIN = $(HOME_DIR)/.local/share/kandev-tools/bin
BUILD_PATH = $(GO_DIR)/bin:$(TOOLS_BIN):$(PATH_VAL)
PORT = $(shell sed -n 's/^KANDEV_SERVER_PORT=//p' $(CURR_DIR)/.env 2>/dev/null || echo 3040)

.PHONY: help install toolchain bundle upgrade env-setup start stop restart status logs clean \
	systemd-setup systemd-stop systemd-status systemd-restart systemd-logs

help:
	@echo "Kandev Service Automation"
	@echo "========================="
	@echo "  make install   - Build the kandev fork from source into $(BUNDLE_DIR)"
	@echo "  make start     - Start Kandev's web UI on http://<host>:$(PORT) via systemd"
	@echo "  make status    - Check daemon status"
	@echo "  make logs      - View live daemon logs"
	@echo "  make upgrade   - Pull the fork's $(KANDEV_BRANCH), rebuild and restart"
	@echo "  make stop      - Stop the daemon and remove the systemd unit"

start: env-setup systemd-setup
stop: systemd-stop
restart: systemd-restart
status: systemd-status
logs: systemd-logs
clean: stop

install: toolchain
	@if [ ! -d $(KANDEV_SRC)/.git ]; then git clone -b $(KANDEV_BRANCH) $(KANDEV_REPO) $(KANDEV_SRC); fi
	@$(MAKE) --no-print-directory bundle

# Go and pnpm at the versions the fork pins; Node >= 24 comes from the host.
toolchain:
	@node -e 'process.exit(parseInt(process.versions.node) >= 24 ? 0 : 1)' \
		|| { echo "[ERROR] Node >= 24 required ($$(node --version))"; exit 1; }
	@if [ ! -x $(GO_DIR)/bin/go ]; then \
		echo "Installing Go $(GO_VERSION) into $(GO_DIR)..."; \
		tmp=$$(mktemp -d); \
		curl -fsSL -o $$tmp/go.tgz https://go.dev/dl/go$(GO_VERSION).linux-amd64.tar.gz; \
		sum=$$(curl -fsSL "https://go.dev/dl/?mode=json&include=all" | python3 -c 'import json,sys; print(next(f["sha256"] for r in json.load(sys.stdin) for f in r["files"] if f["filename"]=="go$(GO_VERSION).linux-amd64.tar.gz"))'); \
		echo "$$sum  $$tmp/go.tgz" | sha256sum -c - >/dev/null || { echo "[ERROR] Go checksum mismatch"; rm -rf $$tmp; exit 1; }; \
		mkdir -p $(GO_DIR) && tar -C $(GO_DIR) --strip-components=1 -xzf $$tmp/go.tgz; rm -rf $$tmp; \
	fi
	@mkdir -p $(TOOLS_BIN) && corepack enable pnpm --install-directory $(TOOLS_BIN)
	@echo "  go: $$($(GO_DIR)/bin/go version | cut -d' ' -f3)"

# Build the web app + backend and package them as a runtime bundle. The old
# bundle keeps serving until the new one is complete (package-bundle swaps bin/).
bundle:
	@echo "Building kandev fork $$(git -C $(KANDEV_SRC) rev-parse --short HEAD) into $(BUNDLE_DIR)..."
	@cd $(KANDEV_SRC) && PATH="$(BUILD_PATH)" COREPACK_ENABLE_DOWNLOAD_PROMPT=0 sh -c \
		'cd apps && pnpm install --frozen-lockfile >/dev/null && cd .. && \
		 make runtime-bundle RUNTIME_BUNDLE_DIR=$(BUNDLE_DIR) RUNTIME_VERSION=fork-$$(git rev-parse --short HEAD)' \
		> $(CURR_DIR)/build.log 2>&1 || { tail -30 $(CURR_DIR)/build.log; echo "[ERROR] build failed - see $(CURR_DIR)/build.log"; exit 1; }
	@echo "[OK] $$($(KANDEV_BIN) --version) built"

upgrade:
	@git -C $(KANDEV_SRC) fetch -q origin
	@git -C $(KANDEV_SRC) checkout -q $(KANDEV_BRANCH)
	@git -C $(KANDEV_SRC) merge -q --ff-only origin/$(KANDEV_BRANCH) || { echo "[ERROR] local $(KANDEV_BRANCH) diverged from origin - resolve in $(KANDEV_SRC)"; exit 1; }
	@$(MAKE) --no-print-directory toolchain bundle
	@if systemctl is-active --quiet $(SERVICE_NAME) 2>/dev/null; then sudo systemctl restart $(SERVICE_NAME); \
	elif systemctl --user is-active --quiet $(SERVICE_NAME) 2>/dev/null; then systemctl --user restart $(SERVICE_NAME); fi
	@echo "[OK] Upgrade complete."

env-setup:
	@if [ ! -f $(CURR_DIR)/.env ]; then \
		cp $(CURR_DIR)/.env.example $(CURR_DIR)/.env; \
		echo "Created .env from .env.example"; \
	fi

systemd-setup: env-setup
	@test -x $(KANDEV_BIN) || { echo "[ERROR] no bundle at $(BUNDLE_DIR) - run 'make install'"; exit 1; }
	@echo "Rendering $(SERVICE_NAME).service..."
	@sed -e 's|{{USER}}|$(USER)|g' -e 's|{{DIR}}|$(CURR_DIR)|g' -e 's|{{HOME}}|$(HOME_DIR)|g' \
		-e 's|{{PATH}}|$(PATH_VAL)|g' -e 's|{{KANDEV_BIN}}|$(KANDEV_BIN)|g' -e 's|{{BUNDLE_DIR}}|$(BUNDLE_DIR)|g' \
		$(CURR_DIR)/$(SERVICE_NAME).service.template | grep -v '^# ' > $(SERVICE_NAME).service
	@if sudo -n true 2>/dev/null; then \
		echo "Installing as system service via sudo..."; \
		sudo mv $(SERVICE_NAME).service /etc/systemd/system/; \
		sudo systemctl daemon-reload; \
		sudo systemctl enable $(SERVICE_NAME); \
		sudo systemctl restart $(SERVICE_NAME); \
	else \
		echo "Installing as user systemd service (~/.config/systemd/user)..."; \
		mkdir -p ~/.config/systemd/user; \
		sed '/^User=/d' $(SERVICE_NAME).service > ~/.config/systemd/user/$(SERVICE_NAME).service; \
		rm -f $(SERVICE_NAME).service; \
		systemctl --user daemon-reload; \
		systemctl --user enable $(SERVICE_NAME); \
		systemctl --user restart $(SERVICE_NAME); \
		loginctl enable-linger $(USER) >/dev/null 2>&1 || true; \
	fi
	@echo "[OK] Kandev on http://$$(hostname -I | cut -d' ' -f1):$(PORT)"

systemd-stop:
	-@if [ -f ~/.config/systemd/user/$(SERVICE_NAME).service ]; then \
		systemctl --user disable --now $(SERVICE_NAME); \
		rm -f ~/.config/systemd/user/$(SERVICE_NAME).service; \
		systemctl --user daemon-reload; \
	fi
	-@if [ -f /etc/systemd/system/$(SERVICE_NAME).service ]; then \
		sudo systemctl disable --now $(SERVICE_NAME); \
		sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service; \
		sudo systemctl daemon-reload; \
	fi

systemd-status:
	@if [ -f ~/.config/systemd/user/$(SERVICE_NAME).service ]; then \
		systemctl --user status $(SERVICE_NAME) --no-pager; \
	else \
		systemctl status $(SERVICE_NAME) --no-pager; \
	fi

systemd-restart:
	@if [ -f ~/.config/systemd/user/$(SERVICE_NAME).service ]; then \
		systemctl --user restart $(SERVICE_NAME); \
	else \
		sudo systemctl restart $(SERVICE_NAME); \
	fi

systemd-logs:
	@if [ -f ~/.config/systemd/user/$(SERVICE_NAME).service ]; then \
		journalctl --user -u $(SERVICE_NAME) -n 50 -f; \
	else \
		sudo journalctl -u $(SERVICE_NAME) -n 50 -f; \
	fi
