#!/usr/bin/env bash
# ==============================================================================
# slackbot-notify.sh - Homelab Slack Notification CLI Tool
# ==============================================================================
# Usage:
#   tools/slackbot-notify.sh "Message to send"
#   tools/slackbot-notify.sh --title "Header Title" --status error "Something failed"
#   echo "Piped message" | tools/slackbot-notify.sh
#   tools/slackbot-notify.sh --help
#
# Configuration:
#   Supports:
#     1) SLACK_CLI auth credentials from ~/.slack/credentials.json (Automatic!)
#     2) SLACK_WEBHOOK_URL (Incoming Webhook)
#     3) SLACK_BOT_TOKEN / SLACK_TOKEN + SLACK_CHANNEL_ID
#
#   Loaded automatically from (in order of priority):
#     - Environment variables
#     - /home/zfadli/my_repos/homelab/.env
#     - ~/.config/homelab/slack.env
#     - ~/.slack/credentials.json
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load configuration if present in .env files
for env_file in "$REPO_ROOT/.env" "$HOME/.config/homelab/slack.env" "/etc/homelab/slack.env"; do
  if [[ -f "$env_file" ]]; then
    while IFS='=' read -r key val || [[ -n "$key" ]]; do
      key="${key#"${key%%[![:space:]]*}"}"
      if [[ "$key" =~ ^SLACK_ ]]; then
        val="${val#"${val%%[![:space:]]*}"}"
        val="${val%"${val##*[![:space:]]}"}"
        if [[ "$val" =~ ^\"(.*)\"$ ]] || [[ "$val" =~ ^\'(.*)\'$ ]]; then
          val="${BASH_REMATCH[1]}"
        fi
        export "$key=$val"
      fi
    done < "$env_file"
  fi
done

# If no token or webhook set, check ~/.slack/credentials.json from slack-cli
if [[ -z "${SLACK_WEBHOOK_URL:-}" && -z "${SLACK_BOT_TOKEN:-}" && -z "${SLACK_TOKEN:-}" ]]; then
  SLACK_CREDS="$HOME/.slack/credentials.json"
  if [[ -f "$SLACK_CREDS" ]]; then
    AUTO_TOKEN="$(python3 -c '
import json, os, sys
try:
    with open(os.path.expanduser("~/.slack/credentials.json")) as f:
        d = json.load(f)
    first_team = list(d.keys())[0]
    print(d[first_team]["token"])
except Exception:
    pass
' 2>/dev/null || true)"
    if [[ -n "$AUTO_TOKEN" ]]; then
      export SLACK_TOKEN="$AUTO_TOKEN"
    fi
  fi
fi

print_usage() {
  cat <<'HELP'
Usage:
  slackbot-notify.sh [OPTIONS] [MESSAGE]

Options:
  -t, --title <text>       Title/Header for the message
  -s, --status <level>     Status level: ok, info, warn, error, failure (default: info)
  -c, --channel <id>       Override target channel (e.g. C025HCL2677 or #general)
  -w, --webhook <url>      Override SLACK_WEBHOOK_URL
  -h, --help               Show this help message

Examples:
  tools/slackbot-notify.sh "Weekly upgrade completed successfully"
  tools/slackbot-notify.sh -t "AI Services Alert" -s error "Hermes service failed to restart"
  journalctl -u hermes-ai -n 10 | tools/slackbot-notify.sh -t "Hermes Crash Log" -s error
HELP
}

TITLE=""
STATUS="info"
CHANNEL_OVERRIDE=""
WEBHOOK_OVERRIDE=""
MESSAGE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--title)
      TITLE="$2"
      shift 2
      ;;
    -s|--status)
      STATUS="$2"
      shift 2
      ;;
    -c|--channel)
      CHANNEL_OVERRIDE="$2"
      shift 2
      ;;
    -w|--webhook)
      WEBHOOK_OVERRIDE="$2"
      shift 2
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    --)
      shift
      MESSAGE="$*"
      break
      ;;
    -*)
      echo "Unknown option: $1" >&2
      print_usage >&2
      exit 1
      ;;
    *)
      if [[ -z "$MESSAGE" ]]; then
        MESSAGE="$1"
      else
        MESSAGE="$MESSAGE $1"
      fi
      shift
      ;;
  esac
done

# Read from standard input if no message passed as argument
if [[ -z "$MESSAGE" ]] && [[ ! -t 0 ]]; then
  MESSAGE="$(cat)"
fi

if [[ -z "$MESSAGE" ]]; then
  echo "Error: No message provided." >&2
  print_usage >&2
  exit 1
fi

# Resolve webhook from CSV mapping file if available
RESOLVED_CSV_WEBHOOK=""
TARGET_LOOKUP="${CHANNEL_OVERRIDE:-}"
if [[ -n "$TARGET_LOOKUP" ]]; then
  for csv_file in "$HOME/.config/homelab/slack_webhooks.csv" "$REPO_ROOT/slack_webhooks.csv"; do
    if [[ -f "$csv_file" ]]; then
      RESOLVED_CSV_WEBHOOK="$(python3 -c '
import csv, sys, os
target = sys.argv[1].lower().lstrip("#")
csv_path = sys.argv[2]
try:
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ch = (row.get("channel") or "").strip().lower().lstrip("#")
            wh = (row.get("webhook_url") or "").strip()
            if ch == target and wh:
                print(wh)
                sys.exit(0)
except Exception:
    pass
' "$TARGET_LOOKUP" "$csv_file" 2>/dev/null || true)"
      if [[ -n "$RESOLVED_CSV_WEBHOOK" ]]; then
        break
      fi
    fi
  done
fi

WEBHOOK_URL="${WEBHOOK_OVERRIDE:-${RESOLVED_CSV_WEBHOOK:-${SLACK_WEBHOOK_URL:-}}}"
TOKEN="${SLACK_BOT_TOKEN:-${SLACK_TOKEN:-}}"
# Default channel if not set
DEFAULT_CHANNEL="C025HCL2677" # #general in workspace fadlis
CHANNEL="${CHANNEL_OVERRIDE:-${SLACK_CHANNEL_ID:-$DEFAULT_CHANNEL}}"

if [[ -z "$WEBHOOK_URL" && -z "$TOKEN" ]]; then
  cat <<'ERR' >&2
Error: Slack credentials not found.
Please run `slack-cli login` or configure SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN in ~/.config/homelab/slack.env or ~/.config/homelab/slack_webhooks.csv
ERR
  exit 2
fi

# Pick color and emoji icon based on status
EMOJI="ℹ️"
COLOR="#2eb886" # green / info
case "${STATUS,,}" in
  ok|success)
    EMOJI="✅"
    COLOR="#36a64f"
    ;;
  warn|warning)
    EMOJI="⚠️"
    COLOR="#ecb22e"
    ;;
  error|fail|failure|fatal)
    EMOJI="🚨"
    COLOR="#e01e5a"
    ;;
  info)
    EMOJI="ℹ️"
    COLOR="#439fe0"
    ;;
esac

HEADER_TEXT=""
if [[ -n "$TITLE" ]]; then
  HEADER_TEXT="$EMOJI *$TITLE*\n\n"
fi
FULL_TEXT="${HEADER_TEXT}${MESSAGE}"

# Send via Webhook
if [[ -n "$WEBHOOK_URL" ]]; then
  PAYLOAD="$(python3 -c '
import json, sys

color = sys.argv[1]
title = sys.argv[2]
msg = sys.argv[3]

payload = {
    "attachments": [
        {
            "color": color,
            "blocks": []
        }
    ]
}

blocks = payload["attachments"][0]["blocks"]

if title:
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": title[:150]
        }
    })

blocks.append({
    "type": "section",
    "text": {
        "type": "mrkdwn",
        "text": msg[:3000]
    }
})

print(json.dumps(payload))
' "$COLOR" "$TITLE" "$MESSAGE")"

  RESPONSE="$(curl -s -X POST -H 'Content-type: application/json' --data "$PAYLOAD" "$WEBHOOK_URL")"
  if [[ "$RESPONSE" == "ok" ]]; then
    echo "[OK] Slack notification sent via webhook."
    exit 0
  else
    echo "Failed to send Slack webhook notification. Response: $RESPONSE" >&2
    exit 3
  fi
fi

# Send via Slack Web API (token)
if [[ -n "$TOKEN" ]]; then
  PAYLOAD="$(python3 -c '
import json, sys

channel = sys.argv[1]
color = sys.argv[2]
title = sys.argv[3]
msg = sys.argv[4]

payload = {
    "channel": channel,
    "attachments": [
        {
            "color": color,
            "blocks": []
        }
    ]
}

blocks = payload["attachments"][0]["blocks"]

if title:
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": title[:150]
        }
    })

blocks.append({
    "type": "section",
    "text": {
        "type": "mrkdwn",
        "text": msg[:3000]
    }
})

print(json.dumps(payload))
' "$CHANNEL" "$COLOR" "$TITLE" "$MESSAGE")"

  RESPONSE="$(curl -s -X POST "https://slack.com/api/chat.postMessage" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-type: application/json" \
    --data "$PAYLOAD")"

  OK="$(python3 -c 'import json, sys; res=json.loads(sys.argv[1]); print("true" if res.get("ok") else "false")' "$RESPONSE")"
  if [[ "$OK" == "true" ]]; then
    echo "[OK] Slack notification sent to channel $CHANNEL."
    exit 0
  else
    echo "Failed to send Slack message via API. Response: $RESPONSE" >&2
    exit 3
  fi
fi
