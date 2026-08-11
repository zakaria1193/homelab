# OpenHands AI Service (`openhandsAI`)

OpenHands is an open-source AI platform for software development and agentic task execution. This service deploys OpenHands locally using Python virtual environments (`openhands-ai`) integrated with `systemd` background daemon management.

---

## Directory Structure

```
services/AI/openhandsAI/
├── Makefile                        # Automation targets (install, start, stop, status, logs, upgrade)
├── .env.example                    # Environment configuration template
├── .env                            # Local environment configuration (git-ignored)
├── .gitignore                      # Git ignore rules for logs, env, and temporary state
├── openhands-ai.service.template   # Systemd unit template
└── README.md                       # Service documentation
```

---

## Quick-Start Guide

### 1. Installation
Install `openhands-ai` into a virtual environment via `uv` or `pip`:
```bash
make install
```

### 2. Start Service
Prepare `.env`, generate the systemd unit file, enable, and start the `openhands-ai` background service:
```bash
make start
```
The service will be accessible on `http://0.0.0.0:3030` (or the port defined in `.env`).

### 3. Check Status
Inspect systemd daemon status:
```bash
make status
```

### 4. View Logs
Tail live service journalctl logs:
```bash
make logs
```

### 5. Upgrade
Upgrade `openhands-ai` package to the latest version and restart the daemon:
```bash
make upgrade
```

### 6. Stop Service
Stop, disable, and clean up the systemd unit:
```bash
make stop
# or
make clean
```

---

## Cloudflare Tunneling & Network Compatibility

- **Network Binding**: Binds to `0.0.0.0` by default to allow reverse-proxy access across LAN and Cloudflare Tunnels (`cloudflared`).
- **Configuration**: Host and port settings can be adjusted in `.env`:
  - `OPENHANDS_HOST=0.0.0.0`
  - `OPENHANDS_PORT=3030`
  - `HOSTS="192.168.1.10 openhands.zakariafadli.com"`

---

## Service Endpoints

- **API Status**: `http://192.168.1.10:3030/` (returns JSON status metadata)
- **Interactive Web API / Docs**: `http://192.168.1.10:3030/docs` (Swagger UI)

