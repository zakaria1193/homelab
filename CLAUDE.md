# Homelab — Setup, Deployment & Operating Manual

This repository is the whole homelab as code: every service is a directory with
a `Makefile`, a `.env.example`, a systemd unit template and a README, and every
running thing is listed on one page (the **cockpit**). This file is what an
agent needs to rebuild or operate it; [AGENTS.md](AGENTS.md) holds the full
standards those services are written to.

---

## 1. Standards (mandatory — see [AGENTS.md](AGENTS.md))

- **Self-Contained & Reproducible Service Makefiles** (`make install`,
  `make start`, `make status`, `make logs`, `make upgrade`, `make stop`).
- **Full Visual Web UI Standard**: `make start` must launch the real web
  frontend (e.g. `npx @openhands/agent-canvas`), not a headless API binary.
- **Native systemd, not Docker**, unless the service already ships as a
  compose stack (`services/media`, `services/karakeep`).
- **Systemd User Service Fallback**: fall back to `systemctl --user` when
  passwordless `sudo` is unavailable, so setup never blocks on a password.
- **Cloudflare Tunnelling (`cloudflared`)** for remote and cross-LAN access;
  bind services to `0.0.0.0` and check `ss -tuln` before picking a port.
- **Non-interactive Systemd Keep-Alive Supervisor Loops** for headless CLIs.
- **Environment Secrets & `.env.example` Standards**.
- **Encrypted `.env` Commits via `git-crypt`**: service `.env` files ARE
  committed, as ciphertext. Register the path in `/.gitattributes` (one line
  per file, never a `*.env` glob), un-ignore it with `!.env` in the service's
  `.gitignore`, then `git add -f` it — and always verify the staged blob starts
  with the `\0GITCRYPT\0` header before committing, since this repo is public.
- **Mandatory Service Decommissioning & Removal Protocol** (stop the unit,
  remove the unit file, `daemon-reload`, clean artifacts, `git rm` + commit).
- **Cockpit Registration**: every service MUST have a section in
  `services/status/services.conf`, carrying both its LAN `link` and its
  Cloudflare `remote` hostname, a `dir` pointing at its `Makefile` (or, for
  containers, at its `docker-compose.yml`), and it MUST be removed from that
  file as part of decommissioning. The cockpit is an *operating* console —
  quick links and terminals up front, diagnostics folded — so use `pinned = 1`
  sparingly and `type = shell` for pure terminal launchers.

---

## 2. Topology

| Host | Address | Runs |
|---|---|---|
| **dell** (primary server) | `192.168.1.10` | everything below unless noted; this repo lives at `~/my_repos/homelab` |
| **pi** (Raspberry Pi 4) | `192.168.1.11` | Home Assistant, the `cloudflared` tunnel origin |

Public hostnames are `*.zakariafadli.com`, served through one Cloudflare
Tunnel. The cockpit page leads with LAN URLs when you reach it by IP and with
tunnel URLs when you reach it by hostname, so one page works from both sides.

## 3. Repository map

```
AGENTS.md                     standards every service is written to
services/status/              THE COCKPIT - start here (port 8300)
services/AI/                  natively-installed AI daemons, one dir each
  Makefile                      `make status|summary|upgrade` across all of them
  paperclipAI/                  Paperclip agent platform + its MCP server
  hermesAI/  openhandsAI/  arrMcpAI/  playwrightMcpAI/  ai-job-search/daemon/
  claudeRcAI/                   Claude Remote Control, one instance per workspace
  antigravityRcAI/              Antigravity Remote Control, one daemon per machine
services/media/               docker compose: jellyfin, sonarr, radarr, readarr,
                              prowlarr, transmission
services/karakeep/            docker compose: karakeep + meilisearch + chrome
```

## 4. Bootstrapping a fresh machine

Do it in this order. Each step is verifiable before the next one starts.

**4.1 Prerequisites**

```bash
sudo apt update && sudo apt install -y git git-crypt make curl python3 nodejs npm
sudo snap install docker                           # this host runs the snap
                                                   # (unit: snap.docker.dockerd)
curl -fsSL https://claude.ai/install.sh | bash     # the `claude` CLI
loginctl enable-linger "$USER"                     # user units survive logout
```

`sudo -n true` deciding the systemd scope is the single most important
environment fact: with passwordless sudo the Makefiles install **system** units
in `/etc/systemd/system`, without it **user** units in
`~/.config/systemd/user`. Both are supported everywhere; just know which one
you got, because `systemctl status <unit>` needs `--user` in the second case.

**4.2 Clone and unlock the secrets**

```bash
git clone <this repo> ~/my_repos/homelab && cd ~/my_repos/homelab
git-crypt unlock            # or `git-crypt unlock <keyfile>` - without this,
                            # committed .env files stay ciphertext on disk
git-crypt status -e         # lists the paths that must be encrypted
```

Only the paths in `/.gitattributes` travel with the repo
(`services/AI/paperclipAI/.env`, `services/status/.env`). Every other service
starts from its own `.env.example` and needs its keys filled in — the table in
§5 says which.

**4.3 Bring up the cockpit first**

```bash
make -C services/status install
make -C services/status start        # http://<host>:8300
make -C services/status status
```

It is stdlib-only Python and depends on nothing else, so it comes up on a bare
machine and then *shows you* what the rest of the bootstrap is doing.

**4.4 AI services**

Each directory is independent and follows the same interface:

```bash
cd services/AI/<service>
cp .env.example .env && $EDITOR .env    # fill in the keys from §5
make install && make start && make status
```

`make -C services/AI summary` prints one line per AI service (unit, scope,
active, enabled, uptime) and never needs sudo — the fastest way to see where a
bootstrap stands.

**4.5 Docker stacks**

```bash
cd services/media    && docker compose up -d
cd services/karakeep && docker compose up -d
```

**4.6 Claude Remote Control instances**

The default instance serves this repo; extra instances serve other workspaces.
Create them from the cockpit — **Claude sessions** (`/claude-rc`) — which
validates the workspace path, writes `.env.<name>` and `.env.<name>.example`,
starts `claude-rc-ai-<name>` and registers it on the page. From a terminal the
same thing is `make -C services/AI/claudeRcAI start INSTANCE=<name>` after
writing `.env.<name>.example` by hand. Commit the `.example`; the real
`.env.<name>` is git-ignored.

Remote Control reuses the login in `~/.claude`, so run `claude` once
interactively on a fresh machine and sign in before starting any instance. Each
workspace must also be trusted once (open it with `claude` and accept the
prompt), and `worktree` spawn mode requires the workspace to be a git repo.

**4.7 Cloudflare Tunnel**

On the tunnel host (the Pi), `/etc/cloudflared/config.yml` maps each hostname to
a LAN origin; the current routes are tabulated in
`services/status/README.md` → *Published routes*. Add a route with:

```bash
cloudflared tunnel route dns <tunnel-name> <hostname>
sudo systemctl restart cloudflared
```

Keep that table, the tunnel config and the `remote =` values in
`services.conf` in sync — the cockpit is what makes a drift visible.

**4.8 Scheduled maintenance**

```cron
0 4 * * 0 make -C ~/my_repos/homelab/services/AI upgrade >> ~/my_repos/homelab/services/AI/upgrade.log 2>&1
```

The cockpit watches that log (`type = logfile`) and turns amber if the weekly
run fails or stops happening.

**4.9 Verify**

```bash
make -C services/AI summary                  # every AI unit active
curl -fsS http://localhost:8300/healthz      # cockpit alive
python3 services/status/status_server.py --once | head -20   # one full probe sweep
docker compose -f services/media/docker-compose.yml ps
```

Then open `http://<host>:8300/` — green across every group *is* the definition
of a finished bootstrap, because a service that is not on that page does not
exist (AGENTS.md §6).

## 5. Service inventory

| Service | Directory | Unit / container | Port | Public hostname | Keys needed |
|---|---|---|---|---|---|
| Cockpit | `services/status` | `homelab-status` | 8300 | `homelab.` | `STATUS_USER`/`STATUS_PASSWORD` (committed, git-crypt) |
| Paperclip | `services/AI/paperclipAI` | `paperclip-ai` | 3100 | `paperclip.` | committed, git-crypt |
| Paperclip MCP | `services/AI/paperclipAI` | `paperclip-mcp` | 9011 (localhost) | `paperclip-mcp.` | `PAPERCLIP_API_KEY`, `PAPERCLIP_COMPANY_ID` |
| Hermes | `services/AI/hermesAI` | `hermes-ai` | 8100 | `hermes.` | `HERMES_DASHBOARD_BASIC_AUTH_*` |
| OpenHands | `services/AI/openhandsAI` | `openhands-ai` | 3030 | `ai.` | `LLM_MODEL` |
| AI job search | `services/AI/ai-job-search/daemon` | `ai-job-search` | 8200 | `chloejobs.` | see its README |
| arr-mcp | `services/AI/arrMcpAI` | `arr-mcp-backend` | 10938 | — | `*_API_KEY` for each *arr |
| Playwright MCP | `services/AI/playwrightMcpAI` | `playwright-mcp` | 9012 (localhost) | — | none |
| Claude Remote Control | `services/AI/claudeRcAI` | `claude-rc-ai[-<name>]` | — | claude.ai/code | none (`~/.claude` login) |
| Antigravity Remote Control | `services/AI/antigravityRcAI` | `agy-remote-control` *(user)* | — | antigravity.google.com | none (one-time Google sign-in) |
| Jellyfin | `services/media` | `jellyfin` | 8096 | `media.` | — |
| Sonarr / Radarr / Readarr / Prowlarr | `services/media` | same names | 8989 / 7878 / 8787 / 9696 | `sonarr.` etc. | — |
| Transmission | `services/media` | `transmission` | 9091 | — | — |
| Karakeep | `services/karakeep` | `karakeep-web-1` (+ `-meilisearch-1`, `-chrome-1`) | 3000 | `keep.` | see its compose file |
| Home Assistant | *(on the Pi)* | — | 8123 | `hass.` | — |

## 6. Day-2 operations

- **See everything**: the cockpit, or `make -C services/AI summary`.
- **One service**: `make -C services/<path> status | logs | restart`.
- **Upgrade everything AI**: `make -C services/AI upgrade` (also the weekly cron).
- **After editing `services.conf`**: `make -C services/status upgrade` — it
  validates the config with a probe sweep before restarting the daemon.
- **Claude sessions**: `/claude-rc` on the cockpit for start/stop/restart/create,
  or `make -C services/AI/claudeRcAI <target> INSTANCE=<name>`.
- **Adding a service**: AGENTS.md §1–§3 for the service itself, §6 for its
  cockpit entry — both in the same commit.
- **Removing one**: AGENTS.md §5, and delete its `services.conf` section.
