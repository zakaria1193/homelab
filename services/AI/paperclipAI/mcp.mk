# mcp.mk — everything for the Paperclip MCP server.
# Included by the main Makefile. Covers: install, the .env credentials workflow,
# running the server (foreground / systemd), and registering with Claude Code.
# Run 'make mcp-help' for a step-by-step setup guide.

# ── Variables ───────────────────────────────────────────────────────────────────
# The only URL you need: base URL of your Paperclip instance (includes /api).
# Used for the API key auth flow and written into .env; paperclip-mcp reads it too.
PAPERCLIP_BASE_URL ?= https://paperclip.zakariafadli.com/api
# Port for the paperclip-mcp HTTP server
MCP_PORT ?= 9011
# Bind address for the HTTP server (use 0.0.0.0 only on trusted LANs)
MCP_HOST ?= 127.0.0.1
# MCP server name reported to the client. Set a distinct value per instance
# when running multiple servers for different companies (e.g. paperclip-acme).
SERVER_NAME ?= paperclip
# Scope for 'claude mcp add' (user = all projects, project/local = this repo)
MCP_SCOPE ?= user
# Absolute path to uv (systemd needs it since PATH is minimal for services)
UV = $(shell command -v uv)
# systemd unit name for the MCP HTTP server
MCP_SERVICE_NAME = paperclip-mcp
# Required env vars that must be set (in .env) before serving/registering.
# PAPERCLIP_BASE_URL is not listed: it has a default and is seeded into .env.
REQUIRED_ENV_VARS = PAPERCLIP_API_KEY PAPERCLIP_COMPANY_ID
# jq filter that normalizes the /companies response into "id<TAB>name" rows.
# Handles an array of objects, a plain name->uuid object map, or a {companies:[...]} wrapper.
COMPANIES_JQ = (if type=="object" and has("companies") then .companies else . end) | (if type=="object" then to_entries[] | "\(.value)\t\(.key)" else .[] | "\(.id // .uuid // ._id)\t\(.name // .companyName // "")" end)
# Shell snippet printed when the companies response can't be parsed into rows.
# Auto-diagnoses: valid-but-unknown JSON shape vs. an auth/not-approved error.
COMPANIES_FAIL = echo "Could not parse any companies from the /companies response."; \
	if printf '%s' "$$resp" | jq -e . > /dev/null 2>&1; then \
		echo "The response is valid JSON but not a shape the built-in filter recognizes."; \
		echo "Fix: adjust COMPANIES_JQ in mcp.mk to match the shape below (share it if unsure)."; \
	else \
		echo "The response is not JSON — likely an auth error or the key isn't approved yet."; \
		echo "Fix: re-run 'make mcp-get-api-key', approve the URL in your browser, then retry."; \
	fi; \
	echo "--- raw response ---"; printf '%s\n' "$$resp"

.PHONY: mcp-help install-mcp mcp-env-setup mcp-get-api-key mcp-list-companies mcp-set-company \
	mcp-register mcp-systemd-setup mcp-systemd-stop mcp-systemd-status \
	mcp-systemd-restart mcp-systemd-logs

# ── Help ────────────────────────────────────────────────────────────────────────
mcp-help:
	@echo "Paperclip MCP — setup guide"
	@echo "==========================="
	@echo ""
	@echo "One-time setup:"
	@echo "  1. make install-mcp        Install paperclip-mcp (editable, via uv)"
	@echo "  2. make mcp-env-setup      Create ./.env (sets PAPERCLIP_BASE_URL)"
	@echo "  3. make mcp-get-api-key    Fetch a board API key -> .env; prints an approval URL"
	@echo "        -> approve that URL in your browser to activate the key"
	@echo "  4. make mcp-set-company    Pick your company (fzf) -> PAPERCLIP_COMPANY_ID in .env"
	@echo ""
	@echo "Run the server (choose one):"
	@echo "  make mcp-systemd-setup     HTTP server as a systemd service on $(MCP_HOST):$(MCP_PORT)"
	@echo "  make mcp-register          Register with Claude Code directly (stdio + uvx)"
	@echo "                             -> then restart Claude Code"
	@echo ""
	@echo "Manage the systemd service:"
	@echo "  make mcp-systemd-status | mcp-systemd-logs | mcp-systemd-restart | mcp-systemd-stop"
	@echo ""
	@echo "Other:"
	@echo "  make mcp-list-companies    List companies (id + name) for your API key"
	@echo ""
	@echo "Multiple companies: repeat steps 4 + register with SERVER_NAME=<distinct-name>,"
	@echo "e.g. make mcp-register SERVER_NAME=paperclip-acme PAPERCLIP_COMPANY_ID=<uuid>"
	@echo ""
	@echo "Options (override on the make command line):"
	@echo "  PAPERCLIP_BASE_URL=$(PAPERCLIP_BASE_URL)"
	@echo "  MCP_HOST=$(MCP_HOST)  MCP_PORT=$(MCP_PORT)  SERVER_NAME=$(SERVER_NAME)  MCP_SCOPE=$(MCP_SCOPE)"

# ── Install ─────────────────────────────────────────────────────────────────────
# Install paperclip-mcp editable for local use. Uses uv if available, else pip.
install-mcp:
	@echo "Installing paperclip-mcp (editable) from paperclip-mcp/..."
	@if command -v uv > /dev/null 2>&1; then \
		echo "Using uv..."; \
		cd paperclip-mcp && uv pip install -e .; \
	else \
		echo "uv not found, using pip..."; \
		cd paperclip-mcp && pip install -e .; \
	fi

# ── Credentials / .env ──────────────────────────────────────────────────────────
# Copy the example env file so values can be filled in.
mcp-env-setup:
	@if [ -f .env ]; then \
		echo ".env already exists, not overwriting."; \
	else \
		cp paperclip-mcp/.env.example .env; \
		grep -v '^PAPERCLIP_BASE_URL=' .env > .env.tmp && mv .env.tmp .env; \
		echo "PAPERCLIP_BASE_URL=$(PAPERCLIP_BASE_URL)" >> .env; \
		echo "Created .env from paperclip-mcp/.env.example (PAPERCLIP_BASE_URL set)."; \
		echo "Still needed: PAPERCLIP_API_KEY, PAPERCLIP_COMPANY_ID."; \
	fi
	@echo "Run 'make mcp-help' for the full setup guide."

# Request a board API key (prefix pcp_board_) via the CLI auth challenge flow
# and write it into ./.env as PAPERCLIP_API_KEY automatically.
# 1. POST a challenge -> returns boardApiToken + approvalUrl
# 2. boardApiToken is written to .env as PAPERCLIP_API_KEY
# 3. Approve approvalUrl in a browser to activate the key
mcp-get-api-key:
	@echo "Requesting a board API key from $(PAPERCLIP_BASE_URL)..."
	@resp=$$(curl -s -X POST $(PAPERCLIP_BASE_URL)/cli-auth/challenges \
		-H "Content-Type: application/json" \
		-d '{"command":"login"}'); \
	if [ -z "$$resp" ]; then \
		echo "Error: no response from $(PAPERCLIP_BASE_URL). Is Paperclip reachable? Set PAPERCLIP_BASE_URL=..."; \
		exit 1; \
	fi; \
	if command -v jq > /dev/null 2>&1; then \
		token=$$(echo "$$resp" | jq -r '.boardApiToken // empty'); \
		url=$$(echo "$$resp" | jq -r '.approvalUrl // empty'); \
		if [ -z "$$token" ] || [ -z "$$url" ]; then \
			echo "Unexpected response:"; echo "$$resp"; exit 1; \
		fi; \
		touch .env; \
		grep -v '^PAPERCLIP_API_KEY=' .env > .env.tmp && mv .env.tmp .env; \
		echo "PAPERCLIP_API_KEY=$$token" >> .env; \
		echo "Wrote PAPERCLIP_API_KEY to .env"; \
		echo ""; \
		echo "Next steps:"; \
		echo "  1. Approve the key in your browser: $$url"; \
		echo "  2. make mcp-set-company  -> pick a company (fzf) and write PAPERCLIP_COMPANY_ID"; \
		echo "  3. make mcp-register     -> register with Claude Code"; \
	else \
		echo "$$resp"; \
		echo "(install jq to auto-extract and write the key; set PAPERCLIP_API_KEY in .env manually)"; \
	fi

# List companies (id + name) available to the board API key in .env.
mcp-list-companies:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Run 'make mcp-get-api-key' first."; exit 1; \
	fi
	@command -v jq > /dev/null 2>&1 || { echo "Error: jq is required. Install it (e.g. apt install jq)."; exit 1; }
	@set -a; . ./.env; set +a; \
	[ -n "$$PAPERCLIP_API_KEY" ] || { echo "Error: PAPERCLIP_API_KEY not set. Run 'make mcp-get-api-key'."; exit 1; }; \
	url="$${PAPERCLIP_BASE_URL:-$(PAPERCLIP_BASE_URL)}"; \
	resp=$$(curl -s $$url/companies -H "Authorization: Bearer $$PAPERCLIP_API_KEY"); \
	rows=$$(printf '%s' "$$resp" | jq -r '$(COMPANIES_JQ)' 2>/dev/null); \
	if [ -z "$$rows" ]; then \
		$(COMPANIES_FAIL); exit 1; \
	fi; \
	printf '%s\n' "$$rows" | while IFS="$$(printf '\t')" read -r id name; do \
		printf '  %-38s %s\n' "$$id" "$$name"; \
	done

# Pick a company with fzf and write its UUID into .env as PAPERCLIP_COMPANY_ID.
# Pass REGISTER=1 to chain straight into 'make mcp-register' afterwards.
mcp-set-company:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Run 'make mcp-get-api-key' first."; exit 1; \
	fi
	@command -v jq > /dev/null 2>&1 || { echo "Error: jq is required. Install it (e.g. apt install jq)."; exit 1; }
	@command -v fzf > /dev/null 2>&1 || { echo "Error: fzf is required. Install it, or use 'make mcp-list-companies' and edit .env manually."; exit 1; }
	@set -a; . ./.env; set +a; \
	[ -n "$$PAPERCLIP_API_KEY" ] || { echo "Error: PAPERCLIP_API_KEY not set. Run 'make mcp-get-api-key'."; exit 1; }; \
	url="$${PAPERCLIP_BASE_URL:-$(PAPERCLIP_BASE_URL)}"; \
	resp=$$(curl -s $$url/companies -H "Authorization: Bearer $$PAPERCLIP_API_KEY"); \
	rows=$$(printf '%s' "$$resp" | jq -r '$(COMPANIES_JQ)' 2>/dev/null); \
	if [ -z "$$rows" ]; then \
		$(COMPANIES_FAIL); exit 1; \
	fi; \
	sel=$$(printf '%s\n' "$$rows" | fzf --delimiter='\t' --with-nth=2 --prompt="Select company: " --height=40% --reverse); \
	[ -n "$$sel" ] || { echo "Cancelled — .env unchanged."; exit 0; }; \
	id=$$(printf '%s' "$$sel" | cut -f1); \
	name=$$(printf '%s' "$$sel" | cut -f2-); \
	grep -v '^PAPERCLIP_COMPANY_ID=' .env > .env.tmp && mv .env.tmp .env; \
	echo "PAPERCLIP_COMPANY_ID=$$id" >> .env; \
	echo "Set PAPERCLIP_COMPANY_ID=$$id ($$name) in .env"
	@if [ "$(REGISTER)" = "1" ]; then \
		echo "REGISTER=1 set — registering with Claude Code..."; \
		$(MAKE) mcp-register; \
	else \
		echo "Next: make mcp-register  (or re-run as 'make mcp-set-company REGISTER=1' to do it now)"; \
	fi

# ── Run the server ──────────────────────────────────────────────────────────────
# Register paperclip-mcp with Claude Code using stdio + uvx (upstream recommended).
# Reads values from .env and passes them per-server, so multiple companies can
# coexist under distinct SERVER_NAME / PAPERCLIP_SERVER_NAME values.
mcp-register:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Run 'make mcp-env-setup' and 'make mcp-get-api-key' first."; \
		exit 1; \
	fi
	@set -a; . ./.env; set +a; \
	base="$${PAPERCLIP_BASE_URL:-$(PAPERCLIP_BASE_URL)}"; \
	for var in $(REQUIRED_ENV_VARS); do \
		eval "val=\$$$$var"; \
		if [ -z "$$val" ]; then \
			echo "Error: $$var is not set in .env. Fill it in before registering."; \
			exit 1; \
		fi; \
	done; \
	name=$${PAPERCLIP_SERVER_NAME:-$(SERVER_NAME)}; \
	echo "Registering '$$name' with Claude Code (stdio, $(MCP_SCOPE) scope, base: $$base)..."; \
	claude mcp add "$$name" -s $(MCP_SCOPE) \
		-e PAPERCLIP_SERVER_NAME="$$name" \
		-e PAPERCLIP_API_KEY="$$PAPERCLIP_API_KEY" \
		-e PAPERCLIP_COMPANY_ID="$$PAPERCLIP_COMPANY_ID" \
		-e PAPERCLIP_BASE_URL="$$base" \
		-- uvx paperclip-mcp --transport stdio

# ── systemd service (background HTTP server) ────────────────────────────────────
# Install a systemd service that serves the MCP HTTP server (uv run paperclip-mcp).
mcp-systemd-setup:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Run 'make mcp-env-setup' and 'make mcp-get-api-key' first."; \
		exit 1; \
	fi
	@if [ -z "$(UV)" ]; then echo "Error: uv not found on PATH."; exit 1; fi
	@echo "Creating systemd service file..."
	@echo "[Unit]" > $(MCP_SERVICE_NAME).service
	@echo "Description=Paperclip MCP HTTP server" >> $(MCP_SERVICE_NAME).service
	@echo "After=network.target" >> $(MCP_SERVICE_NAME).service
	@echo "" >> $(MCP_SERVICE_NAME).service
	@echo "[Service]" >> $(MCP_SERVICE_NAME).service
	@echo "Type=simple" >> $(MCP_SERVICE_NAME).service
	@echo "User=$(USER)" >> $(MCP_SERVICE_NAME).service
	@echo "WorkingDirectory=$(CURDIR)" >> $(MCP_SERVICE_NAME).service
	@echo "Environment=PAPERCLIP_SERVER_NAME=$(SERVER_NAME)" >> $(MCP_SERVICE_NAME).service
	@echo "EnvironmentFile=$(CURDIR)/.env" >> $(MCP_SERVICE_NAME).service
	@echo "ExecStart=$(UV) run paperclip-mcp --host $(MCP_HOST) --port $(MCP_PORT)" >> $(MCP_SERVICE_NAME).service
	@echo "Restart=on-failure" >> $(MCP_SERVICE_NAME).service
	@echo "RestartSec=10" >> $(MCP_SERVICE_NAME).service
	@echo "" >> $(MCP_SERVICE_NAME).service
	@echo "[Install]" >> $(MCP_SERVICE_NAME).service
	@echo "WantedBy=multi-user.target" >> $(MCP_SERVICE_NAME).service
	@echo "Moving service file to /etc/systemd/system/ (requires sudo)..."
	sudo mv $(MCP_SERVICE_NAME).service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable $(MCP_SERVICE_NAME)
	sudo systemctl restart $(MCP_SERVICE_NAME)
	@echo "MCP systemd service running on $(MCP_HOST):$(MCP_PORT)."

mcp-systemd-stop:
	@echo "Stopping and disabling MCP systemd service..."
	-sudo systemctl stop $(MCP_SERVICE_NAME)
	-sudo systemctl disable $(MCP_SERVICE_NAME)
	-sudo rm -f /etc/systemd/system/$(MCP_SERVICE_NAME).service
	sudo systemctl daemon-reload

mcp-systemd-status:
	sudo systemctl status $(MCP_SERVICE_NAME)

mcp-systemd-restart:
	sudo systemctl restart $(MCP_SERVICE_NAME)

mcp-systemd-logs:
	sudo journalctl -u $(MCP_SERVICE_NAME) -f
