# pjm (project manager that runs claude and agy on tickets)

pjm has its own repo, `~/my_repos/pjm` (github.com/zakaria1193/pjm). Read its README for
what it does. This folder is the homelab side: the encrypted `.env`, the standard make
targets, the cockpit entry.

## Quick start

```
make install    # clones pjm if missing, checks tmux/claude/agy/gh
make start      # creates .env from .env.example, installs the unit, starts pjm
make status
make logs
```

Open `http://<host>:8400/`. The cockpit has a pinned `pjm` card (`services.conf`).

## Settings

`.env` here is **git-crypt encrypted** (registered in `/.gitattributes`) and is the file the
systemd unit reads. Defaults and every key are in `.env.example`. Slack tokens go in `.env`:

| Key | Meaning |
|---|---|
| `PJM_DATA` | Data folder: `~/Documents/notes_perso/pjm` (inside the Obsidian notes repo) |
| `PJM_SLACK_BOT_TOKEN`, `PJM_SLACK_APP_TOKEN` | The "pjm" Slack app (not the Homelab Bot) |
| `PJM_SLACK_ALLOWED_USERS` | Slack user ids allowed to answer from a thread |

## Targets

| Target | What it does |
|---|---|
| `make install` | Clone pjm if missing, check the host |
| `make start` / `stop` / `restart` | Systemd unit (system if `sudo -n` works, else user) |
| `make status` / `logs` | Daemon status and live log |
| `make upgrade` | `git pull` pjm, run its tests, restart |
| `make check` / `test` | pjm's own checks and unit tests |

Tunnel: `pjm.zakariafadli.com` → `http://192.168.1.10:8400`, same Access policy as the cockpit.
