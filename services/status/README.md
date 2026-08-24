# Homelab Status Dashboard

An always-on web page showing the live state of **every** homelab service — AI
daemons, media containers, Karakeep, infrastructure, and scheduled maintenance
jobs — with the recent logs of each reachable in one click.

- **Dashboard:** <http://192.168.1.10:8300/>
- **JSON API:** `/api/status`
- **Logs:** `/logs?service=<name>` (HTML) · `/api/logs?service=<name>&lines=500` (plain text)
- **Shell:** `/terminal?service=<name>` — a real PTY in that service's directory, or inside its container
- **Health probe:** `/healthz` (never requires auth, for uptime checks)

It depends on the **Python standard library only** — no pip installs, no
containers, no build step — so it comes up clean on a fresh machine.

## Directory Structure

| File | Purpose |
|---|---|
| `Makefile` | Standard homelab automation (`install`, `start`, `status`, `logs`, `upgrade`, `stop`) |
| `status_server.py` | The dashboard: probes, HTML UI, JSON API, log viewer, terminal routes |
| `terminal.py` | WebSocket + PTY bridge behind the per-service shells |
| `services.conf` | Inventory of monitored services — **this is the file you edit** |
| `.env.example` | Environment template (port, auth, refresh intervals) |
| `.env` | Local overrides, git-ignored, created by `make env-setup` |
| `homelab-status.service.template` | Reference systemd unit |

## Quick Start

```bash
make install     # verify python3 / systemctl / docker are present
make start       # generate the systemd unit, enable it, serve on :8300
make status      # daemon status
make logs        # follow this service's own logs
make check       # one-shot snapshot printed to the terminal as JSON
```

## Make Targets

| Target | Description |
|---|---|
| `make install` | Verifies prerequisites (python3 ≥ 3.7; warns if docker/systemctl are missing) |
| `make start` | Writes the unit, enables and starts it (system scope via sudo, user scope as fallback) |
| `make status` | `systemctl status homelab-status --no-pager` |
| `make logs` | `journalctl -u homelab-status -f` |
| `make upgrade` | Validates `services.conf`, then restarts the daemon to pick up changes |
| `make stop` | Stops, disables, and removes the unit from both scopes |
| `make check` | Runs every probe once and prints the JSON snapshot |
| `make clean` | Alias for `make stop` |

## Monitoring a New Service

Add a section to `services.conf` and run `make upgrade`. Each section name is
the label shown on the card.

```ini
[my-service]
group = AI                       ; heading the card appears under
type  = systemd                  ; systemd | systemd-user | systemd-system | docker | http | port | logfile
link  = http://%(host)s:9000     ; optional: card title links to the service UI
note  = short annotation         ; optional
```

| `type` | Probe | Extra keys |
|---|---|---|
| `systemd` | `systemctl show` — auto-detects user vs system scope | `unit` (defaults to section name) |
| `systemd-user` / `systemd-system` | Same, but pins the scope | `unit` |
| `docker` | `docker ps` state + health | `container` (defaults to section name) |
| `http` | HTTP GET; 2xx–4xx = up, 5xx = degraded | `url` |
| `port` | TCP connect | `probe_host` (default `127.0.0.1`), `port` |
| `logfile` | Freshness + success/failure patterns in a log file | `path` (relative paths resolve from the repo root), `ok_pattern`, `fail_pattern`, `max_age_hours` |

`%(host)s` in a `link` expands to the `[DEFAULT] host` value, which
`STATUS_LINK_HOST` in `.env` overrides — set it to whatever address your browser
uses (LAN IP or tunnel hostname).

### Logs

Every card links to its logs. The source is derived from the check type —
`journalctl` for systemd units (correct scope picked automatically), `docker
logs` for containers, and a file tail for `logfile` checks. Checks that have no
natural log source (`http`, `port`) can point at one explicitly:

```ini
logs = journal:ssh.service     ; or docker:jellyfin, or file:services/AI/upgrade.log
```

The log viewer offers 50/200/1000/2000-line windows, a reload button, and an
optional 5-second auto-refresh. Only names present in `services.conf` are
accepted, so the endpoint cannot be used to read arbitrary files.

### Shells

Every card also has a **shell** link opening a real PTY in the browser:

- **Containers** (`type = docker`) get `docker exec -it <container>` — a shell
  *inside* the container, preferring `bash` and falling back to `sh`.
- **Everything else** gets your login shell in that service's directory. The
  directory comes from the unit's own systemd `WorkingDirectory`, so it tracks
  the service without extra configuration; `logfile` checks open next to their
  log, and anything else falls back to the repo root. Override per service with
  `dir = ...` in `services.conf`.
- If the directory holds a `Makefile`, the session opens by running **`make
  help`**, so the service's own targets are the first thing on screen.

The transport is a WebSocket handled by `terminal.py` (handshake and framing are
implemented against the standard library — still no pip installs). The browser
side uses xterm.js from a CDN, the one piece that needs outbound internet; the
page says so plainly if it cannot load.

Authentication: `/ws/terminal` is the single endpoint that does not use basic
auth, because browsers do not reliably replay basic-auth headers on a WebSocket
upgrade. Instead the already-authenticated page mints a **single-use ticket**
(32 random bytes, 60-second TTL) bound to one service name, and the socket
redeems it. The client picks a service, never a command. Sessions are killed on
disconnect and after `STATUS_TERMINAL_IDLE` seconds of silence, and the shell's
environment has `STATUS_PASSWORD` stripped so the dashboard's own credential is
never visible inside it.

> [!WARNING]
> A browser shell is remote code execution as the account running this daemon.
> On an internet-facing hostname it is only as strong as your basic-auth
> password — prefer a Cloudflare Access policy in front of it. Set
> `STATUS_TERMINAL=0` in `.env` and `make restart` to remove the feature.

### Scheduled jobs

Cron jobs have no unit to query, so they are tracked through their log. The
weekly AI upgrade run is wired up this way:

```cron
0 4 * * 0 make -C ~/my_repos/homelab/services/AI upgrade >> ~/my_repos/homelab/services/AI/upgrade.log 2>&1
```

```ini
[ai-services-upgrade]
group = Maintenance
type = logfile
path = services/AI/upgrade.log
ok_pattern = All AI services upgraded successfully
fail_pattern = Error 2
max_age_hours = 192          ; warn if the weekly run has not happened in 8 days
```

The card turns amber if the last run logged an error, if it never printed its
success line, or if it has not run in `max_age_hours`.

## Customization (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `STATUS_HOST` | `0.0.0.0` | Bind address — keep `0.0.0.0` for LAN and `cloudflared` access |
| `STATUS_PORT` | `8300` | Listen port |
| `STATUS_TITLE` | `Homelab Status` | Page title |
| `STATUS_LINK_HOST` | `192.168.1.10` | Host used to build card links |
| `STATUS_REFRESH` | `15` | Seconds between browser refreshes |
| `STATUS_CACHE_TTL` | `10` | Server-side probe cache, so many viewers don't multiply probe load |
| `STATUS_TIMEOUT` | `4` | Per-probe timeout |
| `STATUS_USER` / `STATUS_PASSWORD` | empty | HTTP basic auth; **set both before exposing publicly** |
| `STATUS_LOG_LINES` | `200` | Default log window |
| `STATUS_LOG_LINES_MAX` | `2000` | Upper bound a client may request |
| `STATUS_ACCESS_LOG` | empty | Set to `1` to log every request to journald |
| `STATUS_TERMINAL` | `1` | Set to `0` to disable browser shells entirely |
| `STATUS_TERMINAL_IDLE` | `900` | Seconds of silence before a shell is closed |
| `STATUS_TERMINAL_SHELL` | account shell | Shell used for non-container services |

## Cloudflare Tunnel

The dashboard binds `0.0.0.0` and needs no special headers, so publishing it is
a plain ingress rule on whichever host runs `cloudflared` (the Raspberry Pi
gateway):

```yaml
# /etc/cloudflared/config.yml on the tunnel host
ingress:
  - hostname: homelab.zakariafadli.com
    service: http://192.168.1.10:8300
  # ... existing rules ...
  - service: http_status:404
```

```bash
sudo systemctl restart cloudflared
cloudflared tunnel route dns <tunnel-name> homelab.zakariafadli.com
```

> [!IMPORTANT]
> This page exposes service states **and logs**. Before publishing it, either
> put a Cloudflare Access policy in front of the hostname, or set
> `STATUS_USER` / `STATUS_PASSWORD` in `.env` and `make restart`.
> `/healthz` stays open either way so uptime checks keep working.
