# Global Antigravity (`agy`) Rules

## Browser Automation & Playwright Standard

- **Default to Playwright (`playwright` / `playwright-headful` MCP):** Always use `playwright` (headless) or `playwright-headful` MCP for browser automation, UI checks, and screenshots. For local services, hit `http://localhost:<port>` rather than Cloudflare Access tunnel URLs.
- **Manual Validation Gate for `claude-in-chrome`:** Do **not** use `claude-in-chrome` unless you specifically need the user's already logged-in browser session (e.g., an external OAuth/Cloudflare Access wall with no local equivalent).
  - Because `agy` does not have `claude-in-chrome` natively, when `aicli` routes to `agy` and a logged-in session is genuinely required, **ask the user for explicit approval first** (manual validation gate), then launch a scoped `claude` session forwarding that authorization for the approved task. In unattended `pjm` runs, block/escalate for user approval instead of running silently.
