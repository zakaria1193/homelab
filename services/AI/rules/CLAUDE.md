Read [AGENTS.md](AGENTS.md). It holds the rules; this file only points at it.

## Browser automation

Always use the `playwright` (headless) or `playwright-headful` MCP for browser automation, UI checks, and screenshots. For local services, hit `http://localhost:<port>` rather than Cloudflare Access tunnel URLs.

Do **not** use `claude-in-chrome` unless you specifically need the user's already logged-in browser session (e.g., an external auth/Cloudflare Access wall with no local equivalent). Using `claude-in-chrome` requires a manual validation gate (explicit user approval first).

