#!/usr/bin/env bash
# ==============================================================================
# auto-heal-and-notify.sh
# Invoked after an AI upgrade failure.
# 1. Takes the list of failed systemd units.
# 2. Collects journal logs.
# 3. Runs `agy` non-interactively to inspect and attempt to heal/fix the service.
# 4. Re-runs `make -C /home/zfadli/my_repos/homelab/services/AI verify`.
# 5. If still failing (or if agy errored), sends a Slack alert with details.
# ==============================================================================

set -uo pipefail

FAILED_UNITS="${1:-}"
REPO_ROOT="/home/zfadli/my_repos/homelab"
NOTIFY="$REPO_ROOT/tools/slackbot-notify.sh"

if [[ -z "$FAILED_UNITS" ]]; then
  echo "No failed units specified. Exiting."
  exit 0
fi

echo "=================================================="
echo "⚡ Triggering agy self-healing for: $FAILED_UNITS"
echo "=================================================="

# Collect recent journal logs for context
LOG_CONTEXT=""
for u in $FAILED_UNITS; do
  LOG_CONTEXT="$LOG_CONTEXT"$'\n'"--- Unit: $u ---"$'\n'
  LOG_CONTEXT="$LOG_CONTEXT$(journalctl -u "$u" --user -n 30 --no-pager 2>/dev/null || journalctl -u "$u" -n 30 --no-pager 2>/dev/null)"
done

# Run agy in non-interactive print mode with dangerously-skip-permissions so it can fix files/restart services
AGY_PROMPT="The following homelab AI systemd unit(s) failed health check verification after upgrade: $FAILED_UNITS.

Recent journal logs:
$LOG_CONTEXT

Task:
1. Inspect the services in /home/zfadli/my_repos/homelab/services/AI/.
2. Diagnose why the unit(s) failed to start or stay active (dependencies, node/python runtime, config, ports, systemd unit).
3. Apply any necessary fixes in the service directory or systemd config.
4. Restart the failing service(s) and confirm they are actively running (systemctl status / systemctl --user status).
Keep your actions focused on getting the service back to a healthy active state."

echo "Starting agy agent execution..."
AGY_OUTPUT=""
if command -v agy >/dev/null 2>&1; then
  AGY_OUTPUT="$(agy --dangerously-skip-permissions --print "$AGY_PROMPT" 2>&1 || true)"
  echo "$AGY_OUTPUT"
else
  echo "Warning: agy CLI not found in PATH."
fi

# Re-run verify check to verify if agy resolved the issue
echo "=================================================="
echo "Verifying AI services post-healing attempt..."
echo "=================================================="
if make -C "$REPO_ROOT/services/AI" verify; then
  echo "✅ Healing succeeded! All AI services are now running."
  if [[ -x "$NOTIFY" ]]; then
    "$NOTIFY" --title "AI Services Auto-Healed" --status ok "The following services failed post-upgrade but were successfully healed by agy:
• Units: \`$FAILED_UNITS\`
All AI services are now active and running."
  fi
  exit 0
else
  echo "🚨 Healing failed or incomplete. Sending Slack alert..."
  if [[ -x "$NOTIFY" ]]; then
    ALERT_MSG="The following AI services failed verification after upgrade and could not be fully recovered by agy:
• Failing Units: \`$FAILED_UNITS\`

Recent journal snippets:
\`\`\`
$(echo "$LOG_CONTEXT" | tail -n 25)
\`\`\`

Action required: inspect with \`journalctl -u <unit> -n 50\` or homelab cockpit."

    "$NOTIFY" --title "AI Services Upgrade Failure" --status error "$ALERT_MSG"
  fi
  exit 1
fi
