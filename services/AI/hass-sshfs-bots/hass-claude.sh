#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Mount SSHFS if not mounted
make mount

# Ensure clean unmount on exit
cleanup() {
    echo ""
    echo "Unmounting Home Assistant SSHFS..."
    make unmount
}
trap cleanup EXIT INT TERM

# Run Claude CLI in this workspace
claude "$@"
