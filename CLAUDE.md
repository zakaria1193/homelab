# Homelab Service Setup & Deployment Guidelines

This repository follows standardized guidelines for creating, managing, and maintaining services.

See [AGENTS.md](AGENTS.md) for full instructions on:
- **Self-Contained & Reproducible Service Makefiles** (`make install`, `make start`, `make status`, `make logs`, `make upgrade`, `make stop`).
- **Full Visual Web UI Standard**: Ensure `make start` launches full visual web frontends (e.g., `npx @openhands/agent-canvas`) rather than headless API-only binaries.
- **Systemd User Service Fallback**: Automatic fallback to `systemctl --user` when passwordless `sudo` is unavailable.
- **Cloudflare Tunneling Compatibility (`cloudflared`)** for remote and cross-LAN access.
- **Non-interactive Systemd Keep-Alive Supervisor Loops**.
- **Environment Secrets & `.env.example` Standards**.
- **Mandatory Service Decommissioning & Removal Protocol** (stop systemd service, remove unit file, reload daemon, clean artifacts, and `git rm` + commit).

