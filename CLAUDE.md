# Homelab Service Setup & Deployment Guidelines

This repository follows standardized guidelines for creating, managing, and maintaining services.

See [AGENTS.md](AGENTS.md) for full instructions on:
- **Self-Contained & Reproducible Service Makefiles** (`make install`, `make start`, `make status`, `make logs`, `make upgrade`, `make stop`).
- **Full Visual Web UI Standard**: Ensure `make start` launches full visual web frontends (e.g., `npx @openhands/agent-canvas`) rather than headless API-only binaries.
- **Systemd User Service Fallback**: Automatic fallback to `systemctl --user` when passwordless `sudo` is unavailable.
- **Cloudflare Tunneling Compatibility (`cloudflared`)** for remote and cross-LAN access.
- **Non-interactive Systemd Keep-Alive Supervisor Loops**.
- **Environment Secrets & `.env.example` Standards**.
- **Encrypted `.env` Commits via `git-crypt`**: service `.env` files ARE committed, as ciphertext. Register the path in `/.gitattributes` (one line per file, never a `*.env` glob), un-ignore it with `!.env` in the service's `.gitignore`, then `git add -f` it — and always verify the staged blob starts with the `\0GITCRYPT\0` header before committing, since this repo is public.
- **Mandatory Service Decommissioning & Removal Protocol** (stop systemd service, remove unit file, reload daemon, clean artifacts, and `git rm` + commit).
- **Status Dashboard Registration**: every service MUST have a section in `services/status/services.conf`, carrying both its LAN `link` and its Cloudflare `remote` hostname, a `dir` pointing at its `Makefile` (or, for containers, at its `docker-compose.yml`), and it MUST be removed from that file as part of decommissioning. The dashboard is an *operating* console — quick links and terminals up front, diagnostics folded — so use `pinned = 1` sparingly and `type = shell` for pure terminal launchers.

