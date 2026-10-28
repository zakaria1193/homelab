#!/usr/bin/env bash
# ==============================================================================
# auto-heal-and-notify.sh
# Invoked after an AI upgrade failure - a failed systemd unit, a failed
# Docker container in services/media or services/karakeep, or both.
# 1. Takes the list of failed systemd units and/or failed containers
#    (as "project:service" tokens, e.g. "media:jellyfin").
# 2. Collects journal logs for units, `docker compose logs` for containers.
# 3. Runs the healing agent (whichever tool `homelab:auto-heal`/`maintenance`
#    resolves to) non-interactively to inspect and attempt to heal/fix it.
# 4. Re-runs `make -C $REPO_ROOT/services/AI verify AUTO_HEAL=0`, so that
#    re-check cannot recurse into this script again. It must be a make
#    argument: `upgrade` calls `verify AUTO_HEAL=1`, and make hands that to
#    every nested make through MAKEFLAGS, where it beats an env variable.
#    That re-check covers both units and containers.
# 5. If still failing (or if the healing agent errored), sends a Slack alert.
# ==============================================================================

set -uo pipefail

FAILED_UNITS="${1:-}"
FAILED_CONTAINERS="${2:-}"
# REPO_ROOT can be overridden for tests.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
NOTIFY="$REPO_ROOT/tools/slackbot-notify.sh"
# aicli's code is its own repo, checked out next to this one; the config stays here.
AICLI_DIR="${AICLI_DIR:-$(dirname "$REPO_ROOT")/aicli}"
if [[ ! -d "$AICLI_DIR" && -d "$HOME/my_repos/aicli" ]]; then
  AICLI_DIR="$HOME/my_repos/aicli"
fi
AICLI="$AICLI_DIR/aicli.py"
export AICLI_CONFIG="${AICLI_CONFIG:-$REPO_ROOT/services/AI/aicliAI/aicli.toml}"

if [[ -z "$FAILED_UNITS" && -z "$FAILED_CONTAINERS" ]]; then
  echo "No failed units or containers specified. Exiting."
  exit 0
fi

DOCKER="$(command -v docker 2>/dev/null || true)"
[[ -z "$DOCKER" && -x /snap/bin/docker ]] && DOCKER=/snap/bin/docker

container_dir() {
  case "$1" in
    media) echo "$REPO_ROOT/services/media" ;;
    karakeep) echo "$REPO_ROOT/services/karakeep" ;;
    *) echo "" ;;
  esac
}

echo "=================================================="
echo "⚡ Triggering self-healing for units:[$FAILED_UNITS] containers:[$FAILED_CONTAINERS]"
echo "=================================================="

# Collect recent journal logs for failed units, and `docker compose logs` for
# failed containers, as context for the healing agent.
LOG_CONTEXT=""
for u in $FAILED_UNITS; do
  LOG_CONTEXT="$LOG_CONTEXT"$'\n'"--- Unit: $u ---"$'\n'
  LOG_CONTEXT="$LOG_CONTEXT$(journalctl -u "$u" --user -n 30 --no-pager 2>/dev/null || journalctl -u "$u" -n 30 --no-pager 2>/dev/null)"
done

for pc in $FAILED_CONTAINERS; do
  project="${pc%%:*}"
  service="${pc#*:}"
  dir="$(container_dir "$project")"
  LOG_CONTEXT="$LOG_CONTEXT"$'\n'"--- Container: $project/$service ---"$'\n'
  if [[ -n "$dir" && -n "$DOCKER" ]]; then
    LOG_CONTEXT="$LOG_CONTEXT$("$DOCKER" compose --project-directory "$dir" -f "$dir/docker-compose.yml" -p "$project" logs --tail 30 "$service" 2>&1)"
  else
    LOG_CONTEXT="$LOG_CONTEXT(no docker logs available: unknown stack or docker not found)"
  fi
done

# Ask aicli which tool `homelab:auto-heal`/`maintenance` resolves to today
# (claude or agy, whichever the cockpit's AI Routes tab or `aicli route`
# currently points maintenance at), instead of hardcoding agy.
HEAL_TOOL="$(python3 "$AICLI" resolve --client homelab:auto-heal --class maintenance --json 2>/dev/null \
  | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("tool") or "")
except ValueError:
    pass' 2>/dev/null)"

# --dangerously-skip-permissions and -p/--print are the same flag names on
# both claude and agy, so the healing prompt below needs no per-tool argv -
# `aicli run` already picks the resolved tool's own model/tier/effort.
AGY_PROMPT="The following homelab AI systemd unit(s) and/or Docker container(s) failed health check verification after upgrade.
Failed units: ${FAILED_UNITS:-none}
Failed containers (project:service): ${FAILED_CONTAINERS:-none}

Recent logs:
$LOG_CONTEXT

Task:
1. Inspect the services in $REPO_ROOT/services/AI/, and the
   Docker compose stacks in $REPO_ROOT/services/media and
   $REPO_ROOT/services/karakeep.
2. Diagnose why the unit(s) failed to start or stay active (dependencies,
   node/python runtime, config, ports, systemd unit), or why the container(s)
   failed (image, config, health check, compose file).
3. Apply any necessary fixes in the service directory, systemd config, or
   compose file. Never change a pinned image tag.
4. Restart the failing service(s) or container(s) and confirm they are
   actively running (systemctl status / systemctl --user status, or
   docker compose ps).
Keep your actions focused on getting the service back to a healthy active state."

echo "Starting the healing agent..."
AGY_OUTPUT=""
if [[ -z "$HEAL_TOOL" ]]; then
  echo "Warning: aicli could not resolve a healing agent (not checked out, or resolve failed)."
elif ! python3 "$AICLI" which "$HEAL_TOOL" >/dev/null 2>&1; then
  echo "Warning: the healing agent ($HEAL_TOOL) is not installed."
else
  # Bounded: the weekly cron waits on this, and the Slack alert comes after it.
  AGY_OUTPUT="$(timeout 1800 python3 "$AICLI" run --client homelab:auto-heal --class maintenance -- --dangerously-skip-permissions --print "$AGY_PROMPT" 2>&1 || true)"
  echo "$AGY_OUTPUT"
fi

# Re-run verify check to verify if the healing agent resolved the issue
echo "=================================================="
echo "Verifying AI services post-healing attempt..."
echo "=================================================="
if make -C "$REPO_ROOT/services/AI" verify AUTO_HEAL=0; then
  echo "✅ Healing succeeded!"
  echo "[OK] AI services and Docker stacks upgraded and running"
  if [[ -x "$NOTIFY" ]]; then
    "$NOTIFY" --title "AI Services Auto-Healed" --status ok "The following failed post-upgrade but were successfully healed by the healing agent (${HEAL_TOOL:-none}):
• Units: \`${FAILED_UNITS:-none}\`
• Containers: \`${FAILED_CONTAINERS:-none}\`
Everything is now active and running."
  fi
  exit 0
else
  echo "🚨 Healing failed or incomplete. Sending Slack alert..."
  echo "[FAIL] AI services and/or Docker stacks not all running after upgrade"
  if [[ -x "$NOTIFY" ]]; then
    ALERT_MSG="The following failed verification after upgrade and could not be fully recovered by the healing agent (${HEAL_TOOL:-none}):
• Failing Units: \`${FAILED_UNITS:-none}\`
• Failing Containers: \`${FAILED_CONTAINERS:-none}\`

Recent log snippets:
\`\`\`
$(echo "$LOG_CONTEXT" | tail -n 25)
\`\`\`

Action required: inspect with \`journalctl -u <unit> -n 50\`, \`docker compose logs\`, or homelab cockpit."

    "$NOTIFY" --title "AI Services Upgrade Failure" --status error "$ALERT_MSG"
  fi
  exit 1
fi
