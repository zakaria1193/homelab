# Homelab Service Setup & Deployment Guidelines for Agents

This document defines mandatory guidelines and standards for creating, managing, and maintaining services within this homelab repository.

---

## 1. Self-Contained & Reproducible Service Architecture

> [!IMPORTANT]
> **Native CLI & Systemd Deployment Standard**:
> - Services MUST be deployed natively via local package managers (`npx`, `npm`, `uv`, or `pip`) and managed using system-level `systemd` daemons.
> - **DO NOT USE DOCKER OR DOCKER COMPOSE** for service setups unless the user explicitly requests a containerized deployment.
> - All service execution scripts, flags, and binaries must be managed within standard `Makefile` targets.

> [!IMPORTANT]
> **Full Visual Web UI Deployment Standard**:
> - When deploying services that provide a web interface (such as OpenHands), agents MUST verify whether the service package requires a full web stack launcher (e.g., `npx @openhands/agent-canvas`) versus a headless API-only server (e.g., `agent-server`).
> - Service `Makefile` targets MUST launch the complete visual frontend stack by default so accessing `http://<host>:<port>/` in a web browser renders the visual application interface rather than a raw JSON API status payload.

> [!TIP]
> **Systemd User Service Fallback**:
> Service `Makefile` targets MUST check if non-interactive `sudo` is available (`sudo -n true`). If passwordless `sudo` is unavailable, Makefiles MUST automatically fall back to user-level systemd daemons (`systemctl --user` with unit files stored under `~/.config/systemd/user/`) to ensure automated single-command setup without hanging on interactive password prompts.



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
| `make install` | Installs all required CLI tools, SDKs, and dependencies | Mandatory (Step 1) |
| `make start` | Prepares `.env`, generates systemd unit file, enables & starts service | Mandatory (Step 2: Primary Start) |
| `make status` | Displays daemon & service status (`systemctl status <service>`) | Mandatory (Step 3) |
| `make logs` | Displays recent logs or tails live logs (`journalctl -u <service> -f`) | Mandatory (Step 4) |
| `make upgrade` | Upgrades installed CLI tools and packages to latest versions | Mandatory (Step 5) |
| `make stop` | Stops, disables, and removes systemd unit cleanly | Mandatory (Step 6: Primary Stop) |
| `make help` | Displays available targets in the chronological order above | Mandatory |
| `make systemd-setup` | Alias for `make start` | Systemd Compatible |
| `make systemd-stop` | Alias for `make stop` | Systemd Compatible |
| `make clean` | Alias for `make stop` | Mandatory |

---

## 3. Cloudflare Tunneling Compatibility (`cloudflared`)

Services deployed in this homelab are accessed remotely and across the local network via **Cloudflare Tunnels (`cloudflared`)**, which may run on the same local host OR on another machine on the LAN (e.g., Raspberry Pi 4 gateway, Dell primary server).

To ensure 100% compatibility with Cloudflare Tunnels:

1. **Network Binding**:
   - Web dashboards and API gateways MUST bind to `0.0.0.0` or be configurable via environment variables (`HOST=0.0.0.0` or `DASHBOARD_HOST=0.0.0.0`).
2. **Port Allocation & Conflict Prevention**:
   - Agents MUST inspect active listening ports on the host (`ss -tuln`) and search existing service configs BEFORE choosing a default service port to avoid collisions with active homelab services (e.g., `karakeep` on port 3000).
3. **Allowed Hostnames & CORS**:
   - Services must allow reverse-proxy hostnames and IP addresses configured via `.env` or Makefile options (e.g., `HOSTS="192.168.1.10 my-service.domain.com"`).
4. **Authentication & Security**:
   - Exposed web interfaces (such as dashboards) MUST support basic authentication or token authentication (`HERMES_DASHBOARD_BASIC_AUTH_...`) when accessible via Cloudflare Tunnels.
5. **IPC & Subprocess Daemons**:
   - Headless background CLI services (like `acpx-ai`) run continuous supervisor keep-alive loops (`while true; do sleep 60; acpx status || acpx sessions ensure; done`) so systemd services remain `active (running)`.

---

## 4. Environment Secrets & Git Hygiene

- NEVER commit a plaintext `.env` or API key into git. This repository is
  **public**: anything pushed unencrypted is public forever, even if deleted in
  a later commit.
- Always update `.env.example` whenever new environment variables or feature
  flags are added.

> [!IMPORTANT]
> **`.env` files ARE committed — encrypted with `git-crypt`.**
> A service is only reproducible on a fresh machine if its secrets travel with
> it, so each service's `.env` is committed as ciphertext rather than ignored.

### Committing a service `.env` via git-crypt

Run these from the repository root, in order:

1. **Register the file, one path per line** — append to `/.gitattributes`:
   ```
   services/<path>/.env filter=git-crypt diff=git-crypt
   ```
   Never broaden this to a bare `*.env` glob: that would sweep every other
   service's uncommitted secrets into the public history.
2. **Un-ignore it** in the service's own `.gitignore`, since the root
   `.gitignore` excludes `.env` globally:
   ```
   # Tracked, but git-crypt-encrypted (see /.gitattributes)
   !.env
   ```
3. **Confirm the repo is unlocked** (the filter is a no-op when locked, and the
   file would be committed as plaintext):
   ```bash
   git-crypt status -e          # must list the new path as "encrypted"
   ```
4. **Stage it** — `-f` is required because of the root `.gitignore`:
   ```bash
   git add -f services/<path>/.env
   ```
5. **Verify the staged blob is ciphertext BEFORE committing.** It must begin
   with the `\0GITCRYPT\0` magic header:
   ```bash
   git show :services/<path>/.env | head -c 12 | xxd
   # 00000000: 0047 4954 4352 5950 5400 ....    .GITCRYPT..
   ```
   Grep the staged blob for a known secret value as a second check. If either
   test shows plaintext, STOP and do not commit.
6. Commit and push as usual.

New machines run `git-crypt unlock` (or `git-crypt unlock <keyfile>`) once;
collaborators are added with `git-crypt add-gpg-user <key-id>`.

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
