# ai-job-search (AI Job Search & Application Assistant)

ai-job-search has its own standalone repository, `~/my_repos/ai-job-search` (github.com/zakaria1193/ai-job-search).
This folder is the homelab side: the encrypted `.env`, the standard make targets, and the cockpit entry.

## Quick start

```
make install    # clones ai-job-search if missing, checks python/bun/cli tools
make start      # creates .env from .env.example, installs the systemd unit, starts service
make status
make logs
```

Open `http://<host>:8200/`. The cockpit has an `ai-job-search` card (`services.conf`).

## Settings

`.env` here is **git-crypt encrypted** (registered in `/.gitattributes`) and is the file the
systemd unit reads. Defaults and sample keys are in `.env.example`.

## Targets

| Target | What it does |
|---|---|
| `make install` | Clone ai-job-search if missing, check dependencies |
| `make start` / `stop` / `restart` | Systemd unit setup, lifecycle management |
| `make status` / `logs` | Daemon status and live log |
| `make upgrade` | `git pull` ai-job-search, check dependencies, restart |
| `make check` / `test` | Run unit tests |

Tunnel: `chloejobs.zakariafadli.com` → `http://192.168.1.10:8200`, behind Cloudflare Access.
