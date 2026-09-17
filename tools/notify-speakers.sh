#!/usr/bin/env bash
# ==============================================================================
# notify-speakers.sh
# Sends TTS notifications to speakers via Home Assistant Webhooks.
# Usage:
#   ./notify-speakers.sh <room> <message>
#   ./notify-speakers.sh <message>             # Defaults to 'auto' presence detection
#
# Supported rooms:
#   - auto (default if omitted): routes to room with active presence (default: office)
#   - livingroom (aliases: couch, couch_room, salon) -> media_player.speaker
#   - office (aliases: desk, bureau) -> media_player.nesthubmax03c5_2
# ==============================================================================

set -euo pipefail

HASS_BASE_URL="${HASS_BASE_URL:-https://hass.zakariafadli.com}"

usage() {
  cat <<EOF
Usage:
  $(basename "$0") <room> <message>
  $(basename "$0") <message>             # Automatically routes based on presence (default: office)

Target rooms:
  auto       Directs to livingroom if presence is detected there, otherwise office
  livingroom Speaker in couch room / living room (Google Home)
  office     Desk display in office (Nest Hub Max)

Examples:
  $(basename "$0") "Notification to active room"
  $(basename "$0") auto "Meeting starting soon"
  $(basename "$0") livingroom "Dinner is ready!"
  $(basename "$0") office "Desk reminder"
EOF
  exit 1
}

if [[ $# -eq 0 ]]; then
  usage
fi

if [[ $# -eq 1 ]]; then
  RAW_ROOM="auto"
  MESSAGE="$1"
else
  FIRST_ARG_LOWER="${1,,}"
  case "$FIRST_ARG_LOWER" in
    auto|livingroom|living_room|living-room|couch|couch_room|couch-room|salon|office|office_room|office-room|desk|bureau)
      RAW_ROOM="$1"
      shift
      MESSAGE="$*"
      ;;
    *)
      RAW_ROOM="auto"
      MESSAGE="$*"
      ;;
  esac
fi

if [[ -z "${MESSAGE// }" ]]; then
  echo "Error: Message cannot be empty." >&2
  exit 1
fi

# Normalize room names and aliases
case "${RAW_ROOM,,}" in
  auto)
    WEBHOOK_ID="tts-auto"
    TARGET_NAME="Auto Presence (Office default)"
    ;;
  livingroom|living_room|living-room|couch|couch_room|couch-room|salon)
    WEBHOOK_ID="tts-livingroom"
    TARGET_NAME="Living Room (Speaker)"
    ;;
  office|office_room|office-room|desk|bureau)
    WEBHOOK_ID="tts-office"
    TARGET_NAME="Office (Nest Hub Max)"
    ;;
  *)
    echo "Error: Unknown room '$RAW_ROOM'." >&2
    echo "Supported rooms: auto, livingroom, office" >&2
    exit 1
    ;;
esac

WEBHOOK_URL="${HASS_BASE_URL%/}/api/webhook/${WEBHOOK_ID}"

# Prepare JSON payload
PAYLOAD=$(jq -nc --arg msg "$MESSAGE" --arg rm "${RAW_ROOM,,}" '{"message": $msg, "room": $rm}')

echo "📢 Sending TTS to ${TARGET_NAME} via ${WEBHOOK_URL}..."

HTTP_CODE=$(curl -s -S -o /dev/null -w "%{http_code}" -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

if [[ "$HTTP_CODE" -ge 200 && "$HTTP_CODE" -lt 300 ]]; then
  echo "✅ Notification sent successfully (HTTP $HTTP_CODE)."
  exit 0
else
  echo "❌ Failed to send notification (HTTP $HTTP_CODE)." >&2
  exit 1
fi
