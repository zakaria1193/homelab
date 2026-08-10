# ACPX AI Instance

This folder contains configuration and systemd management targets for deploying [ACPX](https://github.com/openclaw/acpx) (Agent Client Protocol CLI) as a systemd background service on your homelab, configured to use **Claude** (`claude-agent-acp`) and **AGY** (`agy-acp`).

## Overview

ACPX is a headless, scriptable CLI client for the Agent Client Protocol (ACP) that enables structured interaction with AI coding agents (such as Claude Code, AGY, Codex, etc.):
- **Agent Client Protocol (ACP)**: Structured JSON-RPC client-agent communication.
- **Claude & AGY Integration**: Configured with global native ACP adapters:
  - `claude`: `/home/zfadli/.npm-global/bin/claude-agent-acp` (`@agentclientprotocol/claude-agent-acp`)
  - `agy`: `/home/zfadli/.npm-global/bin/agy-acp` (`agy-acp`)
- **Persistent Sessions**: Manages multi-turn conversation sessions scoped to repositories.
- **Queue Owner & TTL**: Runs a background session daemon to maintain context and process incoming prompts without setup overhead.
- **Systemd Daemon Execution**: Runs headlessly as a background service managed by `systemd`.

---

## Directory Structure

```
services/AI/acpxAI/
├── Makefile                      # Service management & systemd automation commands
├── .env.example                  # Environment template for API keys & ACPX settings
├── .env                          # Local environment file (git-ignored, created via make env-setup)
├── acpx-ai.service.template      # Systemd service unit template
└── README.md                     # Documentation
```

---

## Quick Start Guide

### 1. Install ACPX CLI & Adapters
Run the make target to install `acpx`, `agy-acp`, and `claude-agent-acp` globally via npm:
```bash
make install
```

### 2. Configure Environment Secrets & Agents
Create your `.env` file from the provided template:
```bash
make env-setup
```
Edit `.env` to configure your API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.) and set your default agent:
```env
ACPX_AGENT=claude
# or ACPX_AGENT=agy
```

Initialise / sync global ACPX config (`~/.acpx/config.json`):
```bash
make setup
```

### 3. Deploy via Systemd
Generate the systemd service unit, register it with systemd, and start the daemon:
```bash
make systemd-setup
```

---

## Agent Usage & Commands

You can prompt or check sessions using either **`claude`** or **`agy`**:

```bash
# Check status
acpx claude status
acpx agy status

# Run prompts
acpx claude "refactor auth module"
acpx agy "analyze repo structure"
```

---

## Systemd Management Commands

| Command | Description |
|---|---|
| `make systemd-setup` | Creates unit file, moves to `/etc/systemd/system/`, enables and starts service |
| `make systemd-status` | Displays `systemctl status acpx-ai` |
| `make systemd-logs` | Tails live logs via `journalctl -u acpx-ai -f` |
| `make systemd-log` | Alias for `systemd-logs` |
| `make systemd-restart` | Restarts the systemd service (`make restart`) |
| `make systemd-stop` | Stops, disables, and removes the systemd service file |
| `make clean` | Cleanly uninstalls the systemd service |

---

## Service Options

You can override variables when calling `make`:

```bash
# Run systemd service with AGY (via agy-acp) instead of Claude
make systemd-setup ACPX_AGENT=agy

# Custom permission policy (default: approve-reads)
make systemd-setup ACPX_PERMISSIONS=approve-all

# Custom config directory location
make systemd-setup ACPX_HOME="/home/zfadli/.acpx-custom"
```
