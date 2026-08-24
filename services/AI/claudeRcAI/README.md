# Claude Remote Control AI (`claude-rc-ai`)

Keeps a **Claude Code Remote Control server** (`claude rc` / `claude remote-control`)
running continuously against this repository, so there is always a live homelab
session reachable from [claude.ai/code](https://claude.ai/code) or the Claude
mobile app — no need to be at the machine to start one.

- **Workspace**: `/home/zfadli/my_repos/homelab` (the repo root)
- **Spawn mode**: `worktree` — the always-on session lives in the repo itself,
  while every extra session started from a phone or browser gets its own
  isolated git worktree, so remote work never collides with your terminal.
- **Capacity**: 32 concurrent sessions
- **Permissions**: `auto` (the auto-mode classifier decides; risky actions still prompt on the connected client)

## Instances

One `claude remote-control` process serves exactly **one** directory, so each
always-on workspace is its own instance of this service - same Makefile, same
targets, one `.env.<name>` apiece:

| Instance | Unit | Env file | Workspace | Spawn |
|---|---|---|---|---|
| *(default)* | `claude-rc-ai` | `.env` | the homelab repo root | `worktree` |
| `paperclip` | `claude-rc-ai-paperclip` | `.env.paperclip` | `services/AI/paperclipAI` (`~/paperclip_workspace`) | `same-dir` |

```bash
make start                     # the homelab instance
make start INSTANCE=paperclip  # the Paperclip MCP workspace
make status INSTANCE=paperclip
make logs   INSTANCE=paperclip
```

The Paperclip instance uses `same-dir` rather than `worktree` on purpose: that
workspace is a directory *inside* the homelab repo, not a repo of its own, so
worktree mode would branch the wrong tree — and sessions there exist to drive
Paperclip through the MCP config that only lives in the real directory. Its
sessions therefore all share `~/paperclip_workspace`.

**Adding a workspace** is one file: write `.env.<name>.example` with the `RC_*`
keys, then `make start INSTANCE=<name>`. Register the new unit in
`services/status/services.conf` in the same commit (see AGENTS.md §6).

Or do all three from the browser: the cockpit's **Claude sessions** page
(<http://192.168.1.10:8300/claude-rc>) lists every instance with its state and
workspace, starts / restarts / stops them, and creates a new one from a name
and a directory — checking the path exists, is a directory, and is a git repo
when the spawn mode is `worktree`, then writing both env files, starting the
unit and registering it on the cockpit. Deleting one there stops the unit and
removes those files again. Commit the generated `.env.<name>.example`
afterwards: the real `.env.<name>` is git-ignored, so the template is what
makes the instance reproducible on a fresh machine.

## Directory Structure

```
claudeRcAI/
├── Makefile                        # install / start / status / logs / upgrade / stop
├── .env.example                    # default-instance template (no secrets)
├── .env.paperclip.example          # `paperclip` instance template
├── .env, .env.paperclip            # local runtime config (git-ignored)
├── claude-rc-ai.service.template   # reference systemd unit
└── README.md
```

## Quick Start

```bash
make install   # install / repair the Claude Code native CLI
make start     # generate the systemd unit, enable it, and start the server
make status    # confirm it is active (running)
make logs      # follow the journal
```

The workspace must already be **trusted**: run `claude` once in
`/home/zfadli/my_repos/homelab` and accept the trust prompt, otherwise the
daemon exits with a workspace-trust error. Authentication reuses the existing
login in `~/.claude` — no API key is needed and none belongs in `.env`.

## Make Targets

| Target | Description |
|---|---|
| `make install` | Install / repair the Claude Code native CLI (`claude install stable`) |
| `make start` | Prepare `.env`, generate the systemd unit, enable and (re)start it |
| `make status` | `systemctl status claude-rc-ai` |
| `make logs` | `journalctl -u claude-rc-ai -f` |
| `make upgrade` | `claude update`, then restart the daemon if it is running |
| `make stop` | Stop, disable and remove the systemd unit |
| `make restart` | Restart the daemon |
| `make doctor` | Print the workspace path and run `claude doctor` |
| `make systemd-setup` / `make systemd-stop` / `make clean` | Aliases for start / stop |

## Configuration

Edit `.env` (sourced by systemd **and** included by the Makefile), then re-run
`make start` to regenerate the unit:

| Variable | Default | Description |
|---|---|---|
| `RC_WORKDIR` | repo root | Git repository the server runs in |
| `RC_SPAWN_MODE` | `worktree` | `worktree`, `same-dir`, or `session` |
| `RC_CAPACITY` | `32` | Max concurrent sessions |
| `RC_PERMISSION_MODE` | `auto` | `default`, `acceptEdits`, `auto`, `plan`, `dontAsk`, `bypassPermissions` |
| `RC_SESSION_PREFIX` | `homelab` | Prefix for auto-generated session names |
| `RC_SESSION_NAME` | `homelab` | Name of the always-on in-repo session |
| `RC_DEBUG_FILE` | *(unset)* | Optional verbose debug log path |

## Notes

- **Deployment**: `make start` installs to `/etc/systemd/system` when
  passwordless `sudo` is available (with `User=zfadli`), and falls back to
  `systemctl --user` with `loginctl enable-linger` otherwise, per
  [AGENTS.md](../../../AGENTS.md).
- **Logging**: the server's stdout is a repainting TUI (~5 lines/second), so the
  unit sets `StandardOutput=null` and keeps only `StandardError` in the journal.
  Set `RC_DEBUG_FILE` for real diagnostics.
- **Networking**: no listening port is opened — the server dials out to
  Anthropic, so it needs no Cloudflare tunnel or firewall rule.
- **Worktrees**: sessions spawned remotely create git worktrees of this repo.
  Prune stale ones with `git worktree prune` in `RC_WORKDIR`.
