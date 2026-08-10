# Homelab Service Setup & Deployment Guidelines for Agents

This document defines mandatory guidelines and standards for creating, managing, and maintaining services within this homelab repository.

---

## 1. Self-Contained & Reproducible Service Architecture

Every service directory under `services/` (e.g., `services/AI/acpxAI`, `services/AI/hermesAI`, `services/AI/paperclipAI`) MUST be 100% self-contained and reproducible on a fresh machine.

### Required Files in Every Service Directory:
- **`Makefile`**: Standard automation script for installation, setup, systemd management, and logging.
- **`.env.example`**: Clean environment configuration template with default variables and comments for API keys, network hosts, and secrets.
- **`.env`**: Local runtime environment file (git-ignored, created via `make env-setup`).
- **`<service-name>.service.template`**: Systemd unit template for system-level daemon deployment.
- **`README.md`**: Complete documentation outlining overview, directory structure, quick-start guide, available make targets, and customization options.

---

## 2. Standard `Makefile` Targets & Requirements

Every service `Makefile` MUST implement the following standardized target interface to guarantee single-command reproducibility:

| Target | Description | Requirement |
|---|---|---|
| `make help` | Displays available targets and configurable options with defaults | Mandatory |
| `make install` | Installs all required CLI tools, SDKs, and ACP adapters globally or locally | Mandatory (e.g. `acpx`, `agy-acp`, `claude-agent-acp`) |
| `make upgrade` | Upgrades installed CLI tools, SDKs, and packages to their latest versions and restarts active services | Mandatory |
| `make env-setup` | Creates local `.env` from `.env.example` without overwriting existing `.env` | Mandatory |
| `make setup` | Initializes config files (`config init`) and ensures active sessions | Mandatory |
| `make systemd-setup` | Generates systemd unit file, installs to `/etc/systemd/system/`, reloads daemon, enables & starts service | Mandatory |
| `make systemd-status` | Displays `systemctl status <service>` (prefixed with `-` to handle non-zero exit codes cleanly) | Mandatory |
| `make systemd-restart` / `make restart` | Restarts the systemd service | Mandatory |
| `make systemd-stop` | Stops, disables, and removes the systemd service file | Mandatory |
| `make systemd-logs` / `make systemd-log` / `make logs` | Displays recent logs or tails live logs (`journalctl -u <service> -f`) | Mandatory |
| `make clean` | Stops and removes systemd unit cleanly | Mandatory |

---

## 3. Cloudflare Tunneling Compatibility (`cloudflared`)

Services deployed in this homelab are accessed remotely and across the local network via **Cloudflare Tunnels (`cloudflared`)**, which may run on the same local host OR on another machine on the LAN (e.g., Raspberry Pi 4 gateway, Dell primary server).

To ensure 100% compatibility with Cloudflare Tunnels:

1. **Network Binding**:
   - Web dashboards and API gateways MUST bind to `0.0.0.0` or be configurable via environment variables (`HOST=0.0.0.0` or `DASHBOARD_HOST=0.0.0.0`).
2. **Allowed Hostnames & CORS**:
   - Services must allow reverse-proxy hostnames and IP addresses configured via `.env` or Makefile options (e.g., `HOSTS="192.168.1.10 my-service.domain.com"`).
3. **Authentication & Security**:
   - Exposed web interfaces (such as dashboards) MUST support basic authentication or token authentication (`HERMES_DASHBOARD_BASIC_AUTH_...`) when accessible via Cloudflare Tunnels.
4. **IPC & Subprocess Daemons**:
   - Headless background CLI services (like `acpx-ai`) run continuous supervisor keep-alive loops (`while true; do sleep 60; acpx status || acpx sessions ensure; done`) so systemd services remain `active (running)`.

---

## 4. Environment Secrets & Git Hygiene

- NEVER commit `.env` files or API keys into git. `.env` MUST be listed in `.gitignore`.
- Always update `.env.example` whenever new environment variables or feature flags are added.

---

## 5. Mandatory Service Decommissioning & Removal Protocol

When removing or decommissioning a service from this repository, agents MUST strictly follow this 4-step sequence:

1. **Stop & Disable Running Systemd Service**:
   Run `make systemd-stop` or `make clean` within the target service directory (`sudo systemctl stop <service>` and `sudo systemctl disable <service>`).
2. **Clean Up Systemd Unit Files**:
   Remove `/etc/systemd/system/<service>.service` and run `sudo systemctl daemon-reload` to unregister the unit from systemd completely.
3. **Clean Up Runtime & Local Files**:
   Remove local runtime sockets, caches, or state directories if necessary.
4. **Git Removal & Commit**:
   Remove the service directory from git (`git rm -r services/.../<service-name>`) and commit the removal with a clean, descriptive commit message (e.g. `feat(services): remove deprecated <service-name> service`).
