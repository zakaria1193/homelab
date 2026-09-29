# playwrightMcpAI

Runs [`@playwright/mcp`](https://github.com/microsoft/playwright-mcp), Microsoft's
official Playwright MCP server, as a headless-Chromium HTTP/SSE endpoint any
MCP client (Claude Code, Antigravity, etc.) can dial to drive a real browser -
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
| `PLAYWRIGHT_MCP_HOST` | `0.0.0.0` | Bind address (`0.0.0.0` for local network access, `127.0.0.1` for localhost only). |
| `PLAYWRIGHT_MCP_PORT` | `9012` | Port to listen on for HTTP/SSE MCP transport. |
| `PLAYWRIGHT_MCP_ALLOWED_HOSTS` | `*` | Allowed `Host` headers (`*` allows LAN IPs, localhost, and reverse proxy). |
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

## Instances: headless for testing, headful alongside it

One instance per browser mode, following the `INSTANCE=` pattern from
`services/AI/claudeRcAI`:

| instance | unit | port | mode |
|---|---|---|---|
| default | `playwright-mcp` | 9012 | headless - what MCP clients point at |
| `headful` | `playwright-mcp-headful` | 9013 | real visible window on i3 workspace 6 |

```bash
make start                     # headless, .env
make start INSTANCE=headful    # headful,  .env.headful
make status INSTANCE=headful
```

Both run the anti-detection bundle; only the browser mode differs. Keeping the
headless one on its own port means a test run never pops a window, and the two
never contend for a profile.

### Why there is a generated bundle

`playwright-extra` + `puppeteer-extra-plugin-stealth` — the stack
`ai-job-search/tools/auto_apply/runner.js` uses — works by wrapping the
`chromium` object *inside the calling process* before it launches. `@playwright/mcp`
owns its own launch, and exposes no plugin hook, so the plugin cannot simply be
`use()`d here.

Every evasion does its work through two public hooks, though:

| hook | what it does | how it is carried over |
|---|---|---|
| `onPageCreated(page)` | `page.evaluateOnNewDocument(fn, ...args)` | flattened into `stealth/stealth-init.js`, loaded with `--init-script` |
| `beforeLaunch(options)` | mutates `args` / `ignoreDefaultArgs` | written to `stealth/stealth-launch.json`, fed to `browser.launchOptions` |

`stealth/generate.js` hands each evasion a fake page and a fake options object,
records what it asks for, and writes both artefacts. Regenerate after bumping
the plugin:

```bash
make stealth      # also runs as part of `make install` and `make start`
```

14 of the 17 evasions carry over. Deliberately excluded:

- **`user-agent-override`** — uses CDP `Network.setUserAgentOverride`, not an
  init script. Its main job is stripping `HeadlessChrome` from the UA, which is
  moot for a headful real browser. Set `PLAYWRIGHT_MCP_LOCALE` (and
  `PLAYWRIGHT_MCP_CHANNEL=chrome`) instead of reaching for it.
- **`sourceurl`** — rewrites puppeteer's own evaluate call sites; nothing to port.
- **`defaultArgs`** — not excluded, but launch-side only; it lands in
  `stealth-launch.json` rather than the init script.

Verify a running instance from inside a driven page:

```js
browser_evaluate({ function: "() => navigator.webdriver" })   // => false
```

### Window placement

When headful, the browser is stamped with `--class=$PLAYWRIGHT_MCP_WM_CLASS`
(default `PlaywrightHeadful`). i3 assigns on that marker rather than on the
profile path, so the rule is shared with every other headful automation:

```
assign [class="^PlaywrightHeadful$"] → $ws6    # zfa_configs/i3/common/2_workspaces.sh
```

`ai-job-search/tools/auto_apply/runner.js` passes the same marker. Each tool
keeps its **own profile and its own identity** — nothing is shared beyond the
window-class convention, which matters because auto-apply enforces a fixed
candidate identity and must never share a cookie jar with general browsing.

### Scope note

Headful needs `DISPLAY`/`XAUTHORITY`. A **user** unit inherits them from the
graphical session automatically (`systemctl --user show-environment`); a system
unit does not, so the Makefile writes them into the unit explicitly when
`PLAYWRIGHT_MCP_HEADLESS=false`. A user unit is the better home for a headful
browser — see AGENTS.md on the systemd user-service fallback.
