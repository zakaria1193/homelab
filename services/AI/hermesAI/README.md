# Hermes AI Instance

This folder contains configuration and systemd management targets for deploying [Hermes Agent](https://hermes-agent.nousresearch.com/) (by Nous Research) as a systemd background service on your homelab.

## Overview

Hermes Agent is an autonomous, open-source AI agent runtime featuring:
- **Persistent Memory & Learning Loop**: Remembers user preferences and builds reusable skills over time.
- **Messaging Gateway**: Connects to platforms such as Telegram, Discord, Slack, and Signal.
- **Built-in Automations**: Cron scheduling, web browsing, sandboxed code execution, and Model Context Protocol (MCP) integrations.
- **Systemd Daemon Execution**: Runs headlessly 24/7 as a background service managed by `systemd`.

---

## Directory Structure

```
services/AI/hermesAI/
├── Makefile                      # Service management & systemd automation commands
├── .env.example                  # Environment template for API keys & gateway tokens
├── .env                          # Local environment file (git-ignored, created via make env-setup)
├── hermes-ai.service.template    # Systemd service unit template
└── README.md                     # Documentation
```

---

## Quick Start Guide

### 1. Install Hermes Agent CLI
Run the make target to install `hermes-agent`:
```bash
make install
```

### 2. Configure Environment Secrets
Create your `.env` file from the provided template:
```bash
make env-setup
```
Edit `.env` to configure your preferred LLM provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, etc.) and messaging bot tokens (`TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`).

Optionally run the interactive Hermes wizard:
```bash
make setup
```

### 3. Deploy via Systemd
Generate the systemd service unit, register it with systemd, and start the daemon:
```bash
make systemd-setup
```

---

## Systemd Management Commands

| Command | Description |
|---|---|
| `make systemd-setup` | Creates unit file, moves to `/etc/systemd/system/`, enables and starts service |
| `make systemd-status` | Displays `systemctl status hermes-ai` |
| `make systemd-logs` | Tails live logs via `journalctl -u hermes-ai -f` |
| `make systemd-restart` | Restarts the systemd daemon (`make restart`) |
| `make systemd-stop` | Stops, disables, and removes the systemd service file |
| `make clean` | Cleanly uninstalls the systemd service |

---

## Service Options

You can override variables when calling `make`:

```bash
# Run with a custom port (default: 8100)
make systemd-setup HERMES_PORT=8100

# Run with a custom command for ExecStart
make systemd-setup HERMES_CMD="gateway run"

# Custom config directory location
make systemd-setup HERMES_HOME="/home/zfadli/.hermes-custom"
```

