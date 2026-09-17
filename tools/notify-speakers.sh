#!/usr/bin/env bash
# ==============================================================================
# notify-speakers.sh
# Sends TTS notifications to a room's speaker via Home Assistant Webhook.
# Usage: ./notify-speakers.sh <room> <message>
#
# Supported rooms:
#   - livingroom (aliases: living_room, couch, couch_room, salon) -> media_player.speaker
#   - office (aliases: desk, bureau) -> media_player.google_display
# ==============================================================================

set -euo pipefail

HASS_BASE_URL="${HASS_BASE_URL:-https://hass.zakariafadli.com}"

usage() {
  cat <<EOF
Usage: $(basename "$0") <room> <message>

Arguments:
  room       Target room: 'livingroom' (speaker) or 'office' (nest hub max)
  message    Text to speak on the speaker

Examples:
  $(basename "$0") livingroom "Dinner is ready!"
  $(basename "$0") office "Meeting starts in 5 minutes"
EOF
  exit 1
}

if [[ $# -lt 2 ]]; then
  usage
fi

RAW_ROOM="$1"
shift
MESSAGE="$*"

if [[ -z "${MESSAGE// }" ]]; then
  echo "Error: Message cannot be empty." >&2
  exit 1
fi

# Normalize room names and aliases
case "${RAW_ROOM,,}" in
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
    echo "Supported rooms: livingroom, office" >&2
    exit 1
    ;;
esac

WEBHOOK_URL="${HASS_BASE_URL%/}/api/webhook/${WEBHOOK_ID}"

# Prepare JSON payload
PAYLOAD=$(jq -nc --arg msg "$MESSAGE" '{"message": $msg}')

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
