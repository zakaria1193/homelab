# Cron Job Manager & Viewer (`tools/cron-manager`)

A Python CLI tool and module for managing, inspecting, and triggering scheduled maintenance routines, updates, and custom background scripts across the homelab.

---

## Files

| File | Description |
|---|---|
| `cron_manager.py` | Executable CLI & Python module (`list`, `add`, `toggle`, `delete`, `run`) |
| `crontab.json` | Centralized JSON registry of scheduled jobs |
| `test_cron_manager.py` | Unit tests (`python3 -m unittest discover -s tools/cron-manager -p 'test_*.py'`) |

---

## CLI Commands

```bash
# List all registered jobs
python3 tools/cron-manager/cron_manager.py list

# Add a new job
python3 tools/cron-manager/cron_manager.py add \
  --id "backup-vault" \
  --name "Obsidian Vault Backup" \
  --schedule "0 2 * * *" \
  --category "Backup" \
  --command "tar -czf ~/vault.tar.gz ~/Documents/notes_perso"

# Toggle job state (Enable / Disable)
python3 tools/cron-manager/cron_manager.py toggle --id "security-audit"

# Run a job on demand (triggers Slack notification via tools/slackbot-notify.sh)
python3 tools/cron-manager/cron_manager.py run --id "security-audit"
```
