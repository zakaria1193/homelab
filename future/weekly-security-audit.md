# Weekly Homelab Security & Endpoint Audit Agent

This document defines the automated weekly security audit routine for homelab services.

---

## Agent Prompt Specification

```markdown
# Weekly Homelab Security & Exposed Endpoint Audit Prompt

Perform a comprehensive security audit of all public and local homelab services in `~/my_repos/homelab`.

### 1. Endpoint & Authentication Checks
Check the status of all public subdomains (`*.zakariafadli.com`) and LAN services:

- **Homelab Cockpit (`services/status`)**:
  - Run `make -C services/status status` and `make -C services/status check`.
  - Confirm `homelab-status.service` is active.
  - Verify that authentication (`STATUS_USER`/`STATUS_PASSWORD` or Cloudflare Access headers) is enforced and `/ws/terminal` single-use ticket protection is functioning.

- **Decommissioned / Disabled Services**:
  - Check `systemctl status openhands-ai hermes-ai`.
  - Ensure both `openhands-ai` and `hermes-ai` remain stopped and disabled.

- **Paperclip AI Control Plane (`paperclip.zakariafadli.com`)**:
  - Verify that public HTTP GET requests to `https://paperclip.zakariafadli.com` are protected by Cloudflare Access or return `401`/`303` authorization challenges rather than exposed JSON/HTML.

- **Media Stack Security (*arr services)**:
  - Check public endpoints: `sonarr.zakariafadli.com`, `radarr.zakariafadli.com`, `readarr.zakariafadli.com`, `prowlarr.zakariafadli.com`.
  - Ensure none of these endpoints return unauthenticated `200 OK` admin dashboards without a login prompt or Cloudflare Access challenge.

---

### 2. Reporting & Slack Alerting

Use `tools/slackbot-notify.sh` to send the audit results to Slack:

1. **If all security checks pass cleanly**:
   ```bash
   tools/slackbot-notify.sh \
     --title "Weekly Homelab Security Audit" \
     --status ok \
     "All exposed services are secure. Cockpit authentication is active, disabled services (openhands-ai, hermes-ai) remain stopped, and no unauthenticated endpoints were detected."
   ```

2. **If any unauthenticated endpoint or security vulnerability is detected**:
   ```bash
   tools/slackbot-notify.sh \
     --title "SECURITY ALERT: Exposed Unauthenticated Endpoint" \
     --status error \
     --channel "#alerts" \
     "Security check failed! Details: <describe the specific endpoint or failing service>"
   ```
```

---

## Scheduling Instructions

- **Slash Command**: Run `/schedule` in chat with cron expression `0 9 * * 1` (Every Monday at 09:00 AM).
- **Slack Alerting Script**: `tools/slackbot-notify.sh` automatically uses Slack webhooks or credentials configured in `~/.config/homelab/slack.env` / `~/.config/homelab/slack_webhooks.csv`.
