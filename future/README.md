# Future Features & Scheduled Jobs Directory

This directory centralizes future specifications, scheduled routines, maintenance scripts, and the homelab **Cron Job Viewer & Editor**.

---

## 1. Cron Job Viewer & Editor (`future/cron_manager.py`)

A modular python CLI and backend manager for inspecting, adding, editing, toggling, and running scheduled maintenance & security jobs.

### Registered Jobs Registry (`future/crontab.json`)

The inventory regroups security audits, updates, and maintenance tasks:

| ID | Category | Schedule | Description |
|---|---|---|---|
| `security-audit` | Security | `0 9 * * 1` (Mondays 09:00) | Audits exposed endpoints, authentication headers, and sends Slack alerts. |
| `ai-services-upgrade` | Maintenance | `0 4 * * 0` (Sundays 04:00) | Upgrades AI CLI tools, validates config, and restarts cockpit. |
| `supabase-keepalive` | Maintenance | `30 3 * * 0` (Sundays 03:30) | Keeps free-tier Supabase projects active. |

---

## 2. CLI Usage Commands

```bash
# List all registered jobs
python3 future/cron_manager.py list

# Add a new scheduled job
python3 future/cron_manager.py add \
  --id "backup-vault" \
  --name "Obsidian Vault Backup" \
  --schedule "0 2 * * *" \
  --category "Backup" \
  --command "tar -czf ~/vault-backup.tar.gz ~/Documents/notes_perso" \
  --description "Daily backup of Obsidian notes vault."

# Toggle job state (Enable/Disable)
python3 future/cron_manager.py toggle --id "security-audit"

# Run a job on demand (triggers Slack notification via tools/slackbot-notify.sh)
python3 future/cron_manager.py run --id "security-audit"

# Delete a job
python3 future/cron_manager.py delete --id "backup-vault"
```

---

## 3. Weekly Security & Endpoint Audit (`future/weekly-security-audit.md`)

Contains the complete agent prompt specification for running weekly security audits via `/schedule` or cron routines.
