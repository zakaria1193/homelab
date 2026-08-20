# Paperclip AI Orchestration Workspace

You are operating inside the dedicated **Paperclip AI** workspace in the homelab repository.

## System & Architecture
- **Paperclip Daemon:** Running locally on port `3100` via systemd (`paperclip-ai.service`).
- **Global npm Binary:** `~/.npm-global/bin/paperclipai`
- **Data & Workspaces Directory:** `~/.paperclip/instances/default/`
  - Agent Workspaces: `~/.paperclip/instances/default/workspaces/`
  - Project Directories: `~/.paperclip/instances/default/projects/`
  - Embedded PostgreSQL: `~/.paperclip/instances/default/db/` (Port `54329`)
  - Server Logs: `~/.paperclip/instances/default/logs/`
  - Configuration: `~/.paperclip/instances/default/config.json`
- **Web UI & Domain:**
  - Local: `http://localhost:3100`
  - Domain: `https://paperclip.zakariafadli.com`

## Management Commands (Makefile)
- `make start`     - Start paperclip daemon via systemd
- `make stop`      - Stop daemon and disable systemd service
- `make restart`   - Restart paperclip daemon
- `make status`    - Check paperclip daemon status
- `make logs`      - View live daemon logs
- `make upgrade`   - Upgrade paperclipai & paperclip-mcp to latest release
- `make mcp-get-api-key` - Generate new board authorization key

## MCP Integration
- Tool provider: `paperclip-mcp` (stdio transport)
- Key Tools: `list_issues`, `get_issue`, `create_issue`, `update_issue`, `checkout_issue`, `comment_on_issue`, `list_agents`, `get_agent`, `invoke_agent_heartbeat`, `list_goals`, `create_goal`, `list_approvals`, `approve`, `reject`, `get_dashboard`, `get_cost_summary`.
