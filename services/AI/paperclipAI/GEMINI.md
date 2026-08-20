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

## Primary / Default Company
- **Name:** `Bootstrap` (When user mentions "bootstrap", always assume this company)
- **Company ID:** `a6608d2b-ea7e-444d-978f-254cee766c24`
- **Issue Prefix:** `BOO`
- **Reporter AI Knowledge Base:** `/home/zfadli/Documents/notes_perso/Projects/paperclip`
  - *Rule:* The Reporter AI writes reports across project subdirectories here (and `OVERVIEW.md`). Since it might not run for every single issue, **ALWAYS check what the Reporter AI wrote and when first** before planning or answering questions about Bootstrap projects and issues.
- **Link Formatting Rule:**
  - When referencing Paperclip issues, agents, or external/remote resources, ALWAYS provide clickable markdown web links with full HTTPS/HTTP URLs (e.g. `[BOO-147](https://paperclip.zakariafadli.com/BOO/issues/BOO-147)`) so clicking them immediately opens and renders the page in your web browser (Chrome). Avoid bare identifiers or non-opening raw paths.
  - *Note on Local Artifacts & Private Notes:* To make local notes, plans, and reports (under `/home/zfadli/Documents/notes_perso/Projects/paperclip`) open directly in Obsidian, ALWAYS format them as Obsidian URI links. 
    Format: `[Link Text](obsidian://open?vault=notes_perso&file=Projects%2Fpaperclip%2Fpath%2Fto%2Ffile.md)` (e.g. `[OVERVIEW.md](obsidian://open?vault=notes_perso&file=Projects%2Fpaperclip%2FOVERVIEW.md)`). This prevents them from opening as plain text in the IDE editor.
    If using general web browser rendering instead, plans can be posted to the Paperclip board UI.
  - *Rule on Plan Locations:* Keep all temporary execution plans and slash command plans within internal directories (`~/.gemini/antigravity-cli/brain/`). Do not write them into your private notes repository (`notes_perso/Projects/paperclip/`) unless the plans are complex, long-term documents that need layout styling or are explicitly requested.

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
