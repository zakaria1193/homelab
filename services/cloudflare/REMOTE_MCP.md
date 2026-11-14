# Remote MCP servers (Cloudflare Access + MCP OAuth)

Two MCP servers on the dell are published on the internet. Cloudflare Access
guards them. Only the owner's email may pass. Each MCP client signs in once
through OAuth, and Cloudflare is the OAuth server.

| Server | Public URL | Transport | LAN origin | Access app |
|---|---|---|---|---|
| arr-mcp | `https://arr-mcp.zakariafadli.com/mcp` | SSE | `http://192.168.1.10:10938/mcp` | `arr-mcp MCP` |
| Playwright MCP (headless) | `https://playwright.zakariafadli.com/mcp` | Streamable HTTP | `http://192.168.1.10:9012/mcp` | `playwright MCP` |

The headful Playwright instance (`:9013`) is **not** published.

**Playwright is offline since 2026-11-14.** Both Playwright instances now listen
on `127.0.0.1` only (they expose an RCE-equivalent tool), so the gateway's
tunnel can no longer reach `192.168.1.10:9012` and
`https://playwright.zakariafadli.com/mcp` answers `502`. To publish it again,
run `cloudflared` on the dell itself with origin `http://127.0.0.1:9012`.

## How it works

1. The client calls the public URL with no token. Access answers `401`.
2. The client reads `/.well-known/oauth-authorization-server` on the same
   host. It points to `https://zfadli.cloudflareaccess.com`.
3. The client registers itself and opens a browser for sign-in.
4. You sign in with the allowed email. Access hands the client a token.
5. Later calls carry the token. The tunnel (`pi home`, on the Pi) forwards
   them to the dell.

This is the "Managed OAuth" option on each Access application.

## Connect from claude.ai (web, desktop, mobile)

Do this once. The connector then works in every Claude app on your account.

1. Open **claude.ai → Settings → Connectors**.
2. Click **Add custom connector**.
3. Name: `arr-mcp`. URL: `https://arr-mcp.zakariafadli.com/mcp`. Click **Add**.
4. Click **Connect**. A Cloudflare Access page opens.
5. Sign in with the allowed email (Access sends a one-time code to it).
6. Approve. The connector shows as connected.
7. Repeat with name `playwright` and URL
   `https://playwright.zakariafadli.com/mcp`.

In a chat, turn the connector on from the tools menu if it is off.

## Connect from Claude Code (a machine off the LAN)

On the dell itself, keep using the local URLs (`claude mcp list` shows
`http://127.0.0.1:10938/mcp` and `:9012`). They need no sign-in.

On any other machine:

```bash
claude mcp add --scope user --transport sse  arr-mcp-remote    https://arr-mcp.zakariafadli.com/mcp
claude mcp add --scope user --transport http playwright-remote https://playwright.zakariafadli.com/mcp
```

Then start `claude`, run `/mcp`, pick each server and choose **Authenticate**.
A browser opens on the Access sign-in page. After sign-in, `/mcp` shows them
as connected.

The claude.ai connectors from the section above also show up in Claude Code
as `claude.ai arr-mcp` and `claude.ai playwright`. If you set those up, you do
not need the `claude mcp add` lines.

Note: arr-mcp speaks SSE, so a `--transport http` entry for it fails with
`405 Method Not Allowed`. Use `--transport sse`.

## Check that it works

```bash
# Both should print 401 - Access is in front and asking for a token.
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://arr-mcp.zakariafadli.com/mcp
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://playwright.zakariafadli.com/mcp

# Both should print JSON whose issuer is https://zfadli.cloudflareaccess.com
curl -s https://arr-mcp.zakariafadli.com/.well-known/oauth-authorization-server
curl -s https://playwright.zakariafadli.com/.well-known/oauth-authorization-server
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Connect fails with a `502`/`530` | The service on the dell is down, or the tunnel is | `make -C services/AI/arrMcpAI status` / `make -C services/AI/playwrightMcpAI status`; check the `cloudflared` add-on on the Pi |
| Sign-in page says you are not allowed | Wrong email | Use the email in the Access policy (Zero Trust → Access → Applications → the app → Policies) |
| It worked, then tools stop loading | Token expired | claude.ai: Settings → Connectors → disconnect and connect again. Claude Code: `/mcp` → the server → re-authenticate |
| arr-mcp tools load but every call fails | An *arr API key is wrong | `make -C services/AI/arrMcpAI test-tokens` |

## Changing the setup

- Access apps, policies, the tunnel route and DNS are managed with
  `CLOUDFLARE_ACCESS_TUNNEL_FROM_HOME_IP_ONLY` from `services/cloudflare/.env`
  (see [README.md](README.md)). It only works from the home IP.
- Routes are listed in `services/status/README.md` → *Published routes*. The
  `remote =` values in `services/status/services.conf` must match.
- Anyone who passes Access can drive the Playwright browser, so keep the
  policy to the owner's email only.
