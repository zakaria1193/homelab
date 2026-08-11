# Homelab Service Setup & Deployment Guidelines

This repository follows standardized guidelines for creating, managing, and maintaining services.

See [AGENTS.md](AGENTS.md) for full instructions on:
- **Self-Contained & Reproducible Service Makefiles** (`make start`, `make stop`, `make status`, `make logs`, `make help`, `make install`, `make upgrade`).
- **Cloudflare Tunneling Compatibility (`cloudflared`)** for remote and cross-LAN access.
- **Non-interactive Systemd Keep-Alive Supervisor Loops**.
- **Environment Secrets & `.env.example` Standards**.
- **Mandatory Service Decommissioning & Removal Protocol** (stop systemd service, remove unit file, reload daemon, clean artifacts, and `git rm` + commit).
