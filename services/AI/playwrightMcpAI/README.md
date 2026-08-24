# playwrightMcpAI

Runs [`@playwright/mcp`](https://github.com/microsoft/playwright-mcp), Microsoft's
official Playwright MCP server, as a headless-Chromium HTTP/SSE endpoint any
MCP client (Claude Code, Paperclip, etc.) can dial to drive a real browser -
navigate pages, click, fill forms, take snapshots/screenshots, run JS.

## Directory structure
* `Makefile` - install, systemd management, upgrade.
* `playwright-mcp.service.template` - systemd unit template.
* `.env.example` - host/port/browser/mode configuration.
* `.env` - local runtime config (git-ignored, created via `make env-setup`).

## Quick start

```bash
cd services/AI/playwrightMcpAI
cp .env.example .env      # defaults work as-is
make install               # downloads the Playwright chromium build (~300MB)
make start                  # installs + enables + starts the systemd unit
make status
```

The server listens on `http://127.0.0.1:9012/mcp` by default (see
`.env`). Point an MCP client at it, e.g.:

```json
{
  "mcpServers": {
    "playwright": { "url": "http://127.0.0.1:9012/mcp" }
  }
}
```

or register it with Claude Code directly:

```bash
claude mcp add playwright --transport http http://127.0.0.1:9012/mcp
```

## Configuration (`.env`)

| Var | Default | Notes |
|---|---|---|
| `PLAYWRIGHT_MCP_HOST` | `127.0.0.1` | The server has no auth of its own - only widen this to `0.0.0.0` on a trusted LAN, and never expose it through the Cloudflare tunnel. |
| `PLAYWRIGHT_MCP_PORT` | `9012` | |
| `PLAYWRIGHT_MCP_BROWSER` | `chromium` | `chromium`, `chrome`, `firefox`, `webkit`, `msedge` |
| `PLAYWRIGHT_MCP_HEADLESS` | `true` | Required on this headless server. |
| `PLAYWRIGHT_MCP_ISOLATED` | `true` | `true` = in-memory profile (nothing persisted between restarts). Set `false` for a profile that keeps logins/cookies across restarts. |

Changing `.env` requires `make restart` (or `make start` again) to regenerate
the unit file with the new flags.

## Make targets

* `make install` - downloads the Chromium build via `npx playwright install`.
  Runs `--with-deps` (installs OS packages via `apt`) when passwordless
  `sudo` is available, otherwise downloads just the browser binary and warns
  if OS-level shared libraries are still missing.
* `make start` / `make stop` / `make restart` / `make status` / `make logs`
* `make upgrade` - re-downloads the browser build (in case `@playwright/mcp`
  bumped its pinned Chromium) and restarts the service. `@playwright/mcp` is
  invoked as `npx -y @playwright/mcp@latest`, so the server itself always
  runs on the newest published version without a separate install step.

## Notes

* No API keys or secrets are involved, so `.env` is plain (git-ignored) here
  rather than committed via git-crypt.
* Browser control is powerful - anyone who can reach the MCP endpoint can
  make the driven browser visit arbitrary URLs and read/exfiltrate whatever
  it can see. Keep it bound to `127.0.0.1` unless you have a specific reason
  to widen it, and never route it through `cloudflared`.
