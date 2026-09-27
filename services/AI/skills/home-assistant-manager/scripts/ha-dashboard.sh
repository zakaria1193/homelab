#!/usr/bin/env bash
# Read or replace a STORAGE-mode Lovelace dashboard on the live instance via the HA
# websocket API (lovelace/config[/save]). Takes effect immediately on browser refresh —
# no restart, no .storage file edits.
#
#   ha-dashboard.sh get  <url_path> [out.json]   # fetch live config (default: stdout)
#   ha-dashboard.sh push <url_path> <in.json|in.yaml>
#
# <url_path> e.g. dashboard-sensors (see .storage/lovelace_dashboards), "-" = default dashboard.
# Env: HA_SSH (default: rpi)
set -euo pipefail
HOST="${HA_SSH:-rpi}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cmd="${1:?get|push}"; url="${2:?url_path}"

ssh "$HOST" 'cat > /tmp/ha-ws.py' < "$DIR/ha-ws.py"
case "$cmd" in
  get)
    if [ -n "${3:-}" ]; then
      ssh "$HOST" "bash -lc 'python3 /tmp/ha-ws.py get $url'" > "$3"
    else
      ssh "$HOST" "bash -lc 'python3 /tmp/ha-ws.py get $url'"
    fi ;;
  push)
    src="${3:?config file}"
    # YAML is converted locally so the repo copy (dashboards/*.yaml) can be pushed as-is.
    python3 -c 'import sys,json,yaml; p=sys.argv[1]; d=json.load(open(p)) if p.endswith(".json") else yaml.safe_load(open(p)); json.dump(d,sys.stdout)' "$src" \
      | ssh "$HOST" 'cat > /tmp/ha-dash.json'
    ssh "$HOST" "bash -lc 'python3 /tmp/ha-ws.py save $url /tmp/ha-dash.json'" ;;
  *) echo "usage: $0 get|push <url_path> [file]" >&2; exit 2 ;;
esac
