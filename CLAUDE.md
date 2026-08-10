# Homelab Service Setup & Deployment Guidelines

This repository follows standardized guidelines for creating, managing, and maintaining services.

See [AGENTS.md](AGENTS.md) for full instructions on:
- **Self-Contained & Reproducible Service Makefiles** (`make install`, `make env-setup`, `make setup`, `make systemd-setup`, `make systemd-status`, `make systemd-restart`, `make systemd-stop`, `make systemd-logs`, `make clean`).
- **Cloudflare Tunneling Compatibility (`cloudflared`)** for remote and cross-LAN access.
- **Non-interactive Systemd Keep-Alive Supervisor Loops**.
- **Environment Secrets & `.env.example` Standards**.
- **Mandatory Service Decommissioning & Removal Protocol** (stop systemd service, remove unit file, reload daemon, clean artifacts, and `git rm` + commit).
