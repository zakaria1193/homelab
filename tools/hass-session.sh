#!/usr/bin/env bash
# Home Assistant SSHFS on-demand session launcher
# Mounts ~/hass_sshfs_workspace from the Raspberry Pi on start,
# runs Claude Code or Antigravity, and unmounts on exit.

set -e

TARGET_DIR="$HOME/hass_sshfs_workspace"
RPI_HOST="192.168.1.11"
RPI_USER="zfadli"
RPI_PATH="/homeassistant"

mkdir -p "$TARGET_DIR"

if ! mountpoint -q "$TARGET_DIR"; then
    echo "[SSHFS] Mounting $RPI_USER@$RPI_HOST:$RPI_PATH to $TARGET_DIR..."
    sshfs -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3 "$RPI_USER@$RPI_HOST:$RPI_PATH" "$TARGET_DIR"
fi

cleanup() {
    local exit_code=$?
    echo ""
    echo "[SSHFS] Session ending..."
    cd "$HOME" || true
    # Unmount if no other session is in TARGET_DIR
    if ! fuser -m "$TARGET_DIR" 2>/dev/null | grep -qv "$$"; then
        echo "[SSHFS] Unmounting $TARGET_DIR..."
        fusermount -uz "$TARGET_DIR" 2>/dev/null || sudo umount -l "$TARGET_DIR" 2>/dev/null || true
        echo "[SSHFS] Cleanly unmounted."
    else
        echo "[SSHFS] Another active session is using $TARGET_DIR; mount preserved."
    fi
    exit "$exit_code"
}
trap cleanup EXIT INT TERM

cd "$TARGET_DIR"

CMD="${1:-bash}"
shift 2>/dev/null || true

case "$CMD" in
    claude)
        claude "$@"
        ;;
    agy)
        agy "$@"
        ;;
    shell|bash|zsh)
        "${SHELL:-bash}" "$@"
        ;;
    *)
        "$CMD" "$@"
        ;;
esac
