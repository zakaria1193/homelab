# Security Checker Service (`services/security/security-checker`)

A self-contained, reproducible homelab service that periodically audits exposed network endpoints, systemd daemon states, authentication controls, and Cloudflare Access protection.

---

## Directory Structure

```
services/security/security-checker/
├── Makefile                          # Automation targets (install, start, status, logs, run, upgrade, stop)
├── .env.example                      # Environment configuration template
├── .env                              # Local runtime environment file
├── security_checker.py               # Main security audit script
├── security-checker.service.template # Systemd service unit template
├── security-checker.timer.template   # Systemd timer unit template (weekly execution)
└── README.md                         # Documentation
```

---

## Management Interface

| Target | Description |
|---|---|
| `make install` | Verifies Python 3 prerequisites |
| `make start` | Installs systemd service & timer, enables and runs initial audit |
| `make status` | Displays systemd timer and service status |
| `make logs` | Follows live service logs via journalctl |
| `make run` | Runs `security_checker.py` audit on demand |
| `make upgrade` | Re-installs and restarts timer |
| `make stop` | Stops and removes systemd service & timer |
| `make clean` | Alias for `make stop` |

---

## AI Security Audit Engine

The security checker discovers services from `services/status/services.conf` and uses an AI CLI tool to audit service safety (checking for unauthenticated remote access, exposed terminal endpoints, or insecure options):

- **Default AI Engine**: `SECURITY_CHECKER_AI_CLI=agy` (Antigravity CLI)
- **Engine Selection**: Easily overridden in `.env`:
  ```ini
  # Use Claude CLI instead of agy:
  SECURITY_CHECKER_AI_CLI=claude
  
  # Enable/Disable AI security audits (1 = enabled, 0 = disabled):
  SECURITY_CHECKER_ENABLE_AI=1
  ```
