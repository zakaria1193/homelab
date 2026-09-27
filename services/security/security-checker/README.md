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
