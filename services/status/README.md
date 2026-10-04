# Homelab Cockpit

An always-on web page for **operating** the homelab: the things you actually
click — a Claude session terminal, the web UI of whatever is up — sit in
an always-visible row per group, and the per-service diagnostics (state, logs,
shells) stay folded away behind *logs & shells* until you need them.

Every group renders the same way:

```
AI                                    4 up
  [ ● kandev ] [ ● hermes-ai WAN ] [ ● openhands-ai WAN ] …
  ▸ 4 services · logs & shells                                   ← folded by default
```

Above all of that, the header always carries a **plan-usage health bar** per
CLI. Both cards report the exact same metric the same way - "% of the limit
used", rising and turning amber/red as a period runs out - and the row says so
once so neither card has to:

```
plan limits · % used
[ Claude  5h ████████░░ 88% used   wk ██░░░░░░░░ 7% used  ]
[ Antigravity  5h n/a   wk ██████████ 100% used ]
```

Links follow how you reached the page: over `homelab.zakariafadli.com` the
chips lead with the Cloudflare hostnames, over `192.168.1.10:8300` they lead
with the LAN addresses, and the other one is always the small `LAN` / `WAN`
button next to it. Fold state is remembered per group in `localStorage`.

- **Cockpit:** <http://192.168.1.10:8300/> · <https://homelab.zakariafadli.com/>
- **Claude sessions:** `/claude-rc` · `/api/claude-rc`
- **Projects** (status + link per live project; also the *Projects* tab): `/projects` · `/api/projects`.
  The list is `projects.json`, edited from the page with **Edit** (add, rename, relink,
  reorder, remove); each save commits that file. A project named like a cockpit
  service takes that service's state, any other is probed over HTTP on its link.
  A project can also carry a `github` repo URL: the page links it and shows its open
  visibility (private or public) and open PR and issue counts. Those come from one `gh api graphql` call, made only when the
  page loads (`/api/projects?github=1`), not on the auto-refresh timer.
- **tmux sessions:** `/tmux` · `/api/tmux`
- **JSON API:** `/api/status`
- **Logs:** `/logs?service=<name>` (HTML) · `/api/logs?service=<name>&lines=500` (plain text)
- **Shell:** `/terminal?service=<name>` or `/terminal?session=<name>` — persistent named tmux sessions (`cockpit-<service>`), surviving reloads/disconnects
  (`&where=host` opens the container's *compose* directory on the host instead)
- **Sign in:** `/login` · `/logout`
- **Health probe:** `/healthz` (never requires auth, for uptime checks)

It depends on the **Python standard library only** — no pip installs, no
containers, no build step — so it comes up clean on a fresh machine.

## Directory Structure

| File | Purpose |
|---|---|
| `Makefile` | Standard homelab automation (`install`, `start`, `status`, `logs`, `upgrade`, `stop`) |
| `status_server.py` | Entry point: `--once` prints one probe sweep, otherwise serves the cockpit |
| `cockpit/config.py` | Every `STATUS_*` setting, and `services.conf` parsing |
| `cockpit/probes.py` | One probe per check type (systemd, docker, http, port, logfile), log sources, working dirs |
| `cockpit/snapshot.py` | The cached status payload behind `/api/status` |
| `cockpit/actions.py` | Enable/disable a unit; add/remove a preconfigured AI session |
| `cockpit/auth.py` | Cloudflare Access, the login cookie, terminal tickets |
| `cockpit/handler.py` | HTTP routing and the JSON API |
| `cockpit/pages/` | The HTML pages, one module each (`main.py` is the cockpit itself) |
| `terminal.py` | WebSocket + PTY bridge behind the per-service shells |
| `tmux_manager.py` | Inventory, lifecycle and persistent session management for named tmux sessions |
| `claude_rc.py` | Inventory, validation and lifecycle of the Claude Remote Control instances |
| `usage.py` | Polls `claude`/`agy` `/usage` for the header's plan-usage health bars |
| `services.conf` | Inventory of monitored services — **this is the file you edit** |
| `.env.example` | Environment template (port, auth, refresh intervals, tmux prefix) |
| `.env` | Local overrides, git-ignored, created by `make env-setup` |
| `homelab-status.service.template` | Reference systemd unit |
| `tmux-server.service.template` | Reference unit for the tmux server that owns the shells |
| `tests/test_tmux_persistence.sh` | Asserts a cockpit restart does not kill the shells (`make test`) |
| `ideas_manager.py` | The `/idea` board's backend: reads and writes the Obsidian ideas vault; also a CLI for the Idea Feasibility Agent |
| `ideas_page.py` | The `/idea` board page (kanban) |

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
| `make test` | Asserts the shells survive a cockpit restart (restarts it; `SKIP_RESTART=1` to skip) |
| `make attach` | Lists the sessions, or attaches to one: `make attach SESSION=<name>` |
| `make tmux-setup` | Installs and starts `tmux-server.service`; runs as part of `make start` |
| `make tmux-adopt` | Hands a running tmux server over to that unit — **kills every session first** |
| `make tmux-status` | The unit's status plus `tmux ls` |
| `make tmux-stop` | Stops, disables and removes the unit — **kills every session** |
| `make clean` | Alias for `make stop` |

## Shells That Outlive the Cockpit

Every browser shell is a named tmux session (`cockpit-<service>`), so closing
the tab or losing the connection leaves it running. Surviving a restart of the
cockpit takes one more thing: **the tmux server must not belong to
`homelab-status.service`**.

systemd kills a unit's entire cgroup when it stops, and a tmux server started
on demand by `status_server.py` lands in exactly that cgroup — so every
`make upgrade`, every crash-and-restart, killed all the shells with it.
`tmux-server.service` owns the server instead:

```
/system.slice/tmux-server.service      tmux -D          ← the sessions live here
/system.slice/homelab-status.service   status_server.py ← restarts freely
```

`make start` installs both, ordered so the socket exists before the first
terminal is opened. To check who owns what: `make tmux-status`.

### From SSH

The unit keeps the **default socket** (`/tmp/tmux-$UID/default`), so the
sessions the browser shows are the sessions a plain SSH login sees — no `-L`,
no wrapper:

```bash
ssh homelab
tmux ls                        # cockpit-radarr, cockpit-jellyfin, …
tmux attach -t cockpit-radarr  # same shell the browser terminal is on
make -C ~/my_repos/homelab/services/status attach SESSION=radarr
```

Two clients can attach at once; tmux resizes to the smaller one, and
`window-size latest` makes the newest client win instead. The cockpit sets its
own options (`status off`) **per session**, so your `~/.tmux.conf` status bar
and bindings still apply to sessions you start yourself.

### What still kills a session

- `make tmux-stop`, `systemctl restart tmux-server`, or `tmux kill-server` —
  that unit *is* the server.
- A reboot. Sessions are processes, not files; nothing here is snapshotted.
- `make stop` no longer does: the cockpit goes away and the shells keep
  running, including anything long-lived you left in one. `make tmux-status`
  lists what is still out there.

## Monitoring a New Service

Add a section to `services.conf` and run `make upgrade`. Each section name is
the label shown on the card.

```ini
[my-service]
group  = AI                                ; heading the entry appears under
type   = systemd                           ; see the table below
link   = http://%(host)s:9000              ; optional: LAN web UI
remote = https://my-service.example.com    ; optional: tunnel URL for the same UI
pinned = 1                                 ; optional: always in the quick row
icon   = terminal                          ; optional: terminal | claude
note   = short annotation                  ; optional
```

A chip that sets `command` gains a **shell button** next to its name, which is
how a web session and its local terminal become one chip instead of two.

The **AI Sessions** tab has one row per workspace. It joins two sources on
the workspace directory: the `type = shell` launchers in the `AI Sessions`
group (local `claude`, `agy` and shell terminals) and the Remote Control
servers (`services/AI/claudeRcAI/.env.<name>`, and Antigravity's). A launcher
whose `dir` is an RC server's workspace is the same row, so a server created
from `/claude-rc` lands on the right row with no extra config. A server with
no launcher gets its own row; its terminals open through whichever entry has
that `dir` (its `[claude-rc-<name>]` section). A row with no Claude server
offers `+ RC`, which opens the create form with the path filled in.

`icon` draws a glyph before the name in the quick row. `shell` launchers
default to `terminal`; the Remote Control entries set `claude`, so a chip that
opens a Claude tab is never mistaken for one that opens a local shell. Both are
inline SVG, so they render with no outbound access.

| `type` | Probe | Extra keys |
|---|---|---|
| `systemd` | `systemctl show` — auto-detects user vs system scope | `unit` (defaults to section name) |
| `systemd-user` / `systemd-system` | Same, but pins the scope | `unit` |
| `docker` | `docker ps` state + health | `container` (defaults to section name) |
| `http` | HTTP GET; 2xx–4xx = up, 5xx = degraded | `url` |
| `port` | TCP connect | `probe_host` (default `127.0.0.1`), `port` |
| `logfile` | Freshness + success/failure patterns in a log file | `path` (relative paths resolve from the repo root), `ok_pattern`, `fail_pattern`, `max_age_hours` |
| `shell` | *none* — a terminal launcher, never probed, never counted | `command`, `dir` |

Config order decides both the order of the groups and the order within one.

`%(host)s` in a `link` expands to the `[DEFAULT] host` value, which
`STATUS_LINK_HOST` in `.env` overrides; `%(pi)s` is the Raspberry Pi gateway.

### The quick row

Each group's always-visible row holds, in order:

1. its `shell` launchers,
2. every service that is **up** and has a `link` or `remote`,
3. plus anything marked `pinned = 1`, up or not,

ordered by what the chip opens — Claude sessions (`icon = claude`) first, then
local shells, then plain links — with config order deciding within each kind.

Everything else — and every service's state, logs and shells — lives in the
folded block underneath. That is the whole layout: no other configuration
decides what is shown where.

One entry can be lifted out of its group entirely with `headline = 1`: it is
rendered in the page header, next to the up/degraded totals. That is for the
thing you operate the homelab *with* rather than one of the things being
watched — the `homelab claude agent` session is the only one marked so far.

### Logos and the Pi badge

Every chip and card carries a logo. It is looked up from the entry's own name,
so `[jellyfin]`, `[sonarr]`, `[docker]` or `[home-assistant]` need no config at
all; `icon = ...` only exists for names that do not match one, and for the
generic marks `terminal`, `claude`, `bridge`, `briefcase`, `upgrade` and
`logfile`. The marks are inline SVG, so the page still renders with no outbound
access.

Anything whose `link`, `url` or `probe_host` points at `%(pi)s` is additionally
badged with the Raspberry Pi berry, so "which box is this on" is answered
without opening the card.

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

- **Containers** (`type = docker`) get two: **shell** runs `docker exec -it
  <container>` *inside* the container (preferring `bash`, falling back to
  `sh`), and **compose** opens a host shell in the container's `dir` — where
  its `docker-compose.yml` lives — so `docker compose` itself is one click
  away.
- **Everything else** gets your login shell in that service's directory. The
  directory comes from the unit's own systemd `WorkingDirectory`, so it tracks
  the service without extra configuration; `logfile` checks open next to their
  log, and anything else falls back to the repo root. Override per service with
  `dir = ...` in `services.conf`.
- The session opens by typing the entry's `command` if it has one, else **`make
  help`** when the directory holds a `Makefile`, else **`docker compose ps`**
  when it holds a compose file — so the thing you would have typed first is
  already on screen.

A `shell` entry is a terminal and nothing else — no probe, no state, no place
in the totals. It is for a launcher with no service behind it at all; a CLI
that rides on an existing Remote Control unit (the homelab session's Claude
and Antigravity consoles, see above) uses `command` on that unit's own entry
instead, so the terminal button sits next to the web session it complements
rather than existing as a separate, disconnected chip.

Because the PTY runs your login shell, anything in your `.zshrc` — aliases
included — works verbatim as a `command`.

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
environment has `STATUS_PASSWORD` stripped so the cockpit's own credential is
never visible inside it.

Closing the tab or navigating away kills the PTY and everything running in it —
there is no reattach — so the page asks the browser to confirm while a session
is connected. Browsers word that prompt themselves and ignore any message the
page supplies.

> [!WARNING]
> A browser shell is remote code execution as the account running this daemon.
> On an internet-facing hostname it is only as strong as your basic-auth
> password — prefer a Cloudflare Access policy in front of it. Set
> `STATUS_TERMINAL=0` in `.env` and `make restart` to remove the feature.

### Claude sessions (`/claude-rc`)

One `claude remote-control` process serves exactly one directory, so every
always-on workspace is its own instance: its own `.env.<name>` in
`services/AI/claudeRcAI` and its own `claude-rc-ai-<name>` unit. The **Claude
sessions** page (linked from the header and the footer) is the front-end for
all of them:

- every instance with its state, workspace, spawn mode, capacity, permission
  mode and env file;
- **start / restart / stop**, each one running that instance's Makefile target;
- **delete**, which stops the unit, removes its env files and unregisters it
  from `services.conf`;
- **create**, which validates the workspace path *as you type* — it must exist,
  be a directory, be readable, and be a git repository when spawn mode is
  `worktree` — then writes `.env.<name>` and `.env.<name>.example`, runs
  `make start INSTANCE=<name>`, and appends the new section to `services.conf`
  so the instance shows up on the cockpit;
- **logs** and **restart in a shell** for each instance; the shell route exists
  for system units on a host without passwordless sudo, since a terminal can
  ask for the password where the API cannot.

Nothing on this page builds a command from what the browser sent: the instance
name is matched against the instances found on disk and the verb against a
fixed list, and only then is `make` invoked. `STATUS_RC_MANAGE=0` makes the
page read-only.

> [!WARNING]
> This page starts, stops and creates daemons. It sits behind the same
> basic-auth credential as the browser shells — treat the two as one blast
> radius.

### Signing in

With `STATUS_USER` / `STATUS_PASSWORD` set, a browser is sent to `/login`: a
form with a **Keep me signed in** box. Ticked, it sets a cookie that lasts
`STATUS_SESSION_DAYS` (30 by default) so the password is asked for once per
device rather than once per browser restart; unticked, the cookie lasts only
as long as the browser is open.

The cookie is `HttpOnly`, `SameSite=Lax`, `Secure` whenever cloudflared says
the request arrived over TLS, and carries nothing but an expiry and an HMAC of
it. The signing key is derived from the credential itself, so there is no
session store to keep, restarts do not log anyone out, and **changing
`STATUS_PASSWORD` invalidates every remembered session at once** — as does
`/logout` (linked in the page footer) for the device you are on.

Basic auth still works and is what non-browser clients get: `/api/status`,
`/api/logs` and anything else that does not ask for HTML is answered with a
`401 WWW-Authenticate` challenge rather than a redirect, so `curl -u` and
scripts are unaffected.

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
command = make upgrade 2>&1 | tee -a upgrade.log
```

The card turns amber if the last run logged an error, if it never printed its
success line, or if it has not run in `max_age_hours`. `command` is what gives
a `logfile` job a **retrigger** button: it puts the same shell button every
other card gets, opens in the log's own directory (`type = logfile`'s `dir`
fallback), and - because a `command` types and runs itself the moment the
shell opens - clicking it is a one-click "run it now". `tee -a` appends to the
exact file `path` points at, so the very next "logs" click shows this run, not
just the last cron one.

### Plan-usage health bars

The header always shows a **Claude** and an **Antigravity** card with a 5-hour
and a weekly limit bar, green under 60% used, amber to 85%, red above. Both
cards report the same metric the same way - "% of the limit used" - and the
`plan limits · % used` caption above them says so once rather than making each
meter repeat it; `agy` reports its numbers as *remaining*, so `usage.py`
inverts them (`100 - remaining`) before they ever reach the page, and nothing
downstream of that has to know the difference. Each meter also shows when it
resets, formatted for how far out it is: a countdown for the 5-hour window
("in 3h 12m", since a date would not be legible for something that short) and
a weekday + time for the weekly one ("Mon 6:00 PM", since a countdown in
minutes stops being legible for something that long). Hovering a bar spells
the same thing out in the tooltip.

Neither CLI exposes this as a flag - `/usage` is a slash command meant for an
interactive session - so `usage.py` gets it by running `claude -p "/usage"` /
`agy -p "/usage"` in print mode and parsing the text. `agy` prints one
tab-separated line per model group and period instead - Gemini (what
Antigravity actually drives you with) and an ancillary "Claude and GPT
models" allowance for picking a different model, on separate billing cycles.
Gemini's own reading leads for each period; the other group only fills in
when Gemini has none, so a real Gemini "disabled" limit still shows
something instead of the headline number being dominated by a side quota
that resets on its own unrelated schedule. A period every group reports
"disabled" for has no bar at all rather than a meaningless 0%.

Each CLI startup takes a couple of seconds, far too slow for the page's own
15-second poll, so the result is cached for `STATUS_USAGE_REFRESH` (5 minutes
by default) and refreshed in the background: a request that lands on a stale
cache gets the old numbers immediately while a fetch runs behind it, so a
health bar never itself makes the page pause. `STATUS_USAGE=0` turns the
feature off outright (bars simply disappear) for a box that runs neither CLI.

## The ideas board (`/idea`)

The board is a view over markdown files in the Obsidian vault
(`~/Documents/notes_perso/Project ideas`, or `PROJECT_IDEAS_DIR`).

To edit the notes by hand, read `0 - How to edit boards.md` in that folder. It
is the short user guide to the format (boards, cards, status vs labels).

- **Which files are boards.** Any note in that folder that declares itself a
  backend, with `myJira: backend` or a `myJira/backend` tag in its
  frontmatter, or an inline `#myJira/backend`. New tagged notes appear as board
  tabs and file choices without a code change. If nothing is tagged, it falls
  back to `Money making.md` and `FOSS projects.md`. `Idea Feasibility Agent.md` (the
  Idea Feasibility Agent's rules) is never a board.
- **Per-project boards.** `PROJECTS/<project>.md` is one board per project.
  Create one with *+ New board* on the page, the *+ Board* button on a
  ticket (which links the two, so the ticket then shows *📋 Board*),
  `POST /api/ideas/boards/create` (`{name, sections, parent}`), or
  `python3 ideas_manager.py new-board "<project>" --sections "Features,Bugs"`.
  An existing untagged note of that name is tagged, never overwritten.
- **Status and labels are separate.** A card has exactly one status, its
  column: no tag (untagged), `#status/next`, `#status/ongoing`,
  `#status/shelved` or `#status/rejected`, read from the ticket line only.
  Older `[ONGOING]` / `[REJECTED]` / `[SHELVED ON CAPITAL]` / `#board/...`
  markers are still read and replaced on the next status change. A card has
  any number of labels (`#owned`, `#saas`...), shown as badges and edited on
  their own in the *Edit* dialog.
- **Rejecting is a status change.** The card stays on its board with the
  reason as a note. `python3 ideas_manager.py archive [--dry-run]` later moves
  every rejected / shelved card into `<board> [REJECTED].md` /
  `<board> [SHELVED].md` (not boards, so off the page), under the same
  headings.
- **`#owned`** marks a founder mandate. The Idea Feasibility Agent must not run kill gates
  on it (rules in `Idea Feasibility Agent.md` §6). Tick *Owned* when dropping an idea.
- **Callouts.** An indented `> [!info]- Title` block under a ticket is shown
  as a folded *Detailed Analysis* box on the card.
- **Rejection challenges.** Rejected and shelved cards have a
  *⚖️ Challenge Rejection* button. It adds `#rejection_challenged` and a
  `- **Challenge (date)**:` line (`POST /api/ideas/challenge`). The Idea Feasibility Agent lists
  and answers them on each heartbeat:

  ```bash
  python3 ideas_manager.py challenged
  python3 ideas_manager.py answer <id> accepted|upheld "<rationale>"
  ```

  An answer swaps the tag to `#rejection_answered` and writes a
  `- **Feasibility Answer (date)**: [verdict] ...` line. An accepted challenge moves
  the card back to Next. The same ruling is available as
  `POST /api/ideas/answer-challenge` (`{id, answer, verdict, target_status}`).

## Customization (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `STATUS_HOST` | `0.0.0.0` | Bind address — keep `0.0.0.0` for LAN and `cloudflared` access |
| `STATUS_PORT` | `8300` | Listen port |
| `STATUS_TITLE` | `Homelab Cockpit` | Page title |
| `STATUS_LINK_HOST` | `192.168.1.10` | Host used to build card links |
| `STATUS_REFRESH` | `15` | Seconds between browser refreshes |
| `STATUS_CACHE_TTL` | `10` | Server-side probe cache, so many viewers don't multiply probe load |
| `STATUS_TIMEOUT` | `4` | Per-probe timeout |
| `STATUS_USER` / `STATUS_PASSWORD` | empty | Credentials for the login form and basic auth; **set both before exposing publicly** |
| `STATUS_CF_ACCESS_ENABLED` | `1` | Enable Cloudflare Access Zero Trust header & JWT validation |
| `STATUS_CF_ACCESS_AUD` | empty | Cloudflare Access Application Audience (AUD) Tag to validate |
| `STATUS_CF_ACCESS_TEAM_DOMAIN` | empty | Cloudflare Access Team Domain (e.g. `myteam.cloudflareaccess.com`) |
| `STATUS_CF_ACCESS_ALLOWED_EMAILS` | empty | Comma-separated list of allowed user emails |
| `STATUS_REQUIRE_CF_ACCESS` | `0` | Set to `1` to reject requests missing valid Cloudflare Access credentials |
| `STATUS_SESSION_DAYS` | `30` | How long "keep me signed in" lasts |
| `STATUS_LOG_LINES` | `200` | Default log window |
| `STATUS_LOG_LINES_MAX` | `2000` | Upper bound a client may request |
| `STATUS_ACCESS_LOG` | empty | Set to `1` to log every request to journald |
| `STATUS_TERMINAL` | `1` | Set to `0` to disable browser shells entirely |
| `STATUS_TERMINAL_IDLE` | `900` | Seconds of silence before a shell is closed |
| `STATUS_TERMINAL_SHELL` | account shell | Shell used for non-container services |
| `STATUS_RC_MANAGE` | `1` | Set to `0` to make `/claude-rc` read-only |
| `STATUS_RC_DIR` | `services/AI/claudeRcAI` | Where the Remote Control instances live |
| `STATUS_RC_TIMEOUT` | `180` | Seconds a `make start`/`stop` may take |
| `STATUS_USAGE` | `1` | Set to `0` to hide the Claude/Antigravity plan-usage bars |
| `STATUS_USAGE_TIMEOUT` | `30` | Seconds the `-p "/usage"` call may take, per CLI |
| `STATUS_USAGE_REFRESH` | `300` | Seconds a usage snapshot is trusted before refreshing in the background |

## Cloudflare Tunnel & Cloudflare Access (Zero Trust)

Because the cockpit exposes interactive PTY terminal access and full system logs, **it MUST be protected as a private application behind Cloudflare Zero Trust Access** on public hostnames.

### Setting Up Cloudflare Access (Zero Trust Private Application)

1. Open **[Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)**.
2. Navigate to **Access** -> **Applications** -> **Add an Application** -> **Self-hosted**.
3. Configure Application Settings:
   - **Application Name**: `Homelab Cockpit`
   - **Domain**: `homelab.zakariafadli.com` (or your configured subdomain)
   - **Session Duration**: Select desired duration (e.g. 24 hours).
4. Create Access Policies:
   - Action: **Allow**
   - Policy Name: `Homelab Admin Access`
   - Rule: Include **Emails** or **Emails Ending In** (e.g., your email address or Google/GitHub Identity Provider).
5. Configure `.env` integration (optional but recommended):
   - Copy the **Application Audience (AUD) Tag** from the Application overview tab in Cloudflare.
   - Set in `services/status/.env`:
     ```ini
     STATUS_CF_ACCESS_ENABLED=1
     STATUS_CF_ACCESS_AUD=<your-application-aud-tag>
     STATUS_CF_ACCESS_TEAM_DOMAIN=<your-team-domain>.cloudflareaccess.com
     STATUS_CF_ACCESS_ALLOWED_EMAILS=your.email@domain.com
     STATUS_REQUIRE_CF_ACCESS=1
     ```

### Cloudflare Tunnel Ingress

The cockpit binds `0.0.0.0` and handles Cloudflare Access headers seamlessly:

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

### Published routes

These are the `remote =` values in `services.conf`; keep the two in sync when a
route changes.

| Hostname | Origin | Entry |
|---|---|---|
| `homelab.zakariafadli.com` | `http://192.168.1.10:8300` | `homelab cockpit` |
| `playwright.zakariafadli.com` | `http://192.168.1.11:9012` | `playwright-mcp` (group `AI`) |
| `ai.zakariafadli.com` | `http://192.168.1.10:3030` | `openhands-ai` |
| `hermes.zakariafadli.com` | `http://192.168.1.10:8100` | `hermes-ai` |
| `chloejobs.zakariafadli.com` | `http://192.168.1.10:8200` | `ai-job-search` |
| `media.zakariafadli.com` | `http://192.168.1.10:8096` | `jellyfin` |
| `sonarr.zakariafadli.com` | `http://192.168.1.10:8989` | `sonarr` |
| `radarr.zakariafadli.com` | `http://192.168.1.10:7878` | `radarr` |
| `readarr.zakariafadli.com` | `http://192.168.1.10:8787` | `readarr` |
| `prowlarr.zakariafadli.com` | `http://192.168.1.10:9696` | `prowlarr` |
| `keep.zakariafadli.com` | `http://192.168.1.10:3000` | `karakeep` |
| `hass.zakariafadli.com` | `http://192.168.1.11:8123` | `home-assistant` |
| `ssh.zakariafadli.com` | `ssh://192.168.1.10:22` | `ssh` |
| `sshpi.zakariafadli.com` | `ssh://192.168.1.11:22` | `raspberry-pi` |

The two `ssh://` routes are not browser links, so they are recorded in the
`note` of their entry rather than as a `remote`. Transmission has no route and
is LAN-only.

> [!IMPORTANT]
> This page exposes service states **and logs**. Before publishing it, either
> put a Cloudflare Access policy in front of the hostname, or set
> `STATUS_USER` / `STATUS_PASSWORD` in `.env` and `make restart`.
> `/healthz` stays open either way so uptime checks keep working.
