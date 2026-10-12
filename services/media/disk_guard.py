#!/usr/bin/env python3
"""Pause Transmission before downloads eat the last of the disk.

Run once a minute by media-disk-guard.timer. When free space on the downloads
disk drops under the floor (default 100 GB) every active torrent is paused;
once free space is back above the floor plus a margin, exactly the torrents the
guard paused are started again. Torrents the user paused by hand stay paused.

Stdlib only. State and log live next to this file.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get("DISK_GUARD_STATE", HERE / "disk_guard_state.json"))
LOG = Path(os.environ.get("DISK_GUARD_LOG", HERE / "disk_guard.log"))

GB = 1024 ** 3
FLOOR = int(float(os.environ.get("DISK_GUARD_MIN_FREE_GB", "100")) * GB)
MARGIN = int(float(os.environ.get("DISK_GUARD_RESUME_MARGIN_GB", "20")) * GB)
RPC = os.environ.get("TRANSMISSION_RPC", "http://127.0.0.1:9091/transmission/rpc")
WATCH = os.environ.get("DLDIR", str(Path.home() / "content" / "downloads"))
HEARTBEAT_S = 3600
NOTIFY = HERE.parent.parent / "tools" / "slackbot-notify.sh"
SLACK_CHANNEL = os.environ.get("DISK_GUARD_SLACK_CHANNEL", "media-server")

STOPPED = 0  # Transmission torrent status: stopped


def log(msg):
    with LOG.open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} disk-guard: {msg}\n")
    print(msg)


def notify(status, title, message):
    """Post to Slack. A broken Slack must never stop the guard itself."""
    try:
        r = subprocess.run([str(NOTIFY), "-c", SLACK_CHANNEL, "-s", status, "-t", title, message],
                           capture_output=True, text=True, timeout=30)
        if r.returncode:
            log(f"Slack notify failed: {(r.stderr or r.stdout).strip()[:200]}")
    except (OSError, subprocess.SubprocessError) as e:
        log(f"Slack notify failed: {e}")


class Transmission:
    def __init__(self, url):
        self.url, self.sid = url, ""

    def call(self, method, **arguments):
        body = json.dumps({"method": method, "arguments": arguments}).encode()
        for _ in range(2):
            req = urllib.request.Request(self.url, body, {"X-Transmission-Session-Id": self.sid})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    return json.load(r)["arguments"]
            except urllib.error.HTTPError as e:
                if e.code != 409:
                    raise
                self.sid = e.headers["X-Transmission-Session-Id"]
        raise RuntimeError("Transmission kept refusing the session id")


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"paused_ids": [], "last_ok": 0}


def run(free, tx, now=None):
    """One decision. Returns 'paused', 'resumed' or 'ok'."""
    now = time.time() if now is None else now
    state = load_state()
    held = state.get("paused_ids", [])

    if free < FLOOR:
        active = [t["id"] for t in tx.call("torrent-get", fields=["id", "status"])["torrents"]
                  if t["status"] != STOPPED]
        if active:
            tx.call("torrent-stop", ids=active)
            held = sorted(set(held) | set(active))
            log(f"FREE {free / GB:.0f} GB < {FLOOR / GB:.0f} GB: paused {len(active)} torrent(s)")
            notify("error", "Media disk almost full",
                   f"Only {free / GB:.0f} GB free (floor {FLOOR / GB:.0f} GB). "
                   f"Paused {len(active)} Transmission torrent(s) until space is freed.")
        state["paused_ids"] = held
        STATE.write_text(json.dumps(state))
        return "paused" if active or held else "ok"

    if held and free >= FLOOR + MARGIN:
        tx.call("torrent-start", ids=held)
        log(f"free {free / GB:.0f} GB: resumed {len(held)} torrent(s)")
        notify("ok", "Media downloads resumed",
               f"{free / GB:.0f} GB free again. Resumed {len(held)} torrent(s).")
        state["paused_ids"] = []
        STATE.write_text(json.dumps(state))
        return "resumed"

    if now - state.get("last_ok", 0) >= HEARTBEAT_S and not held:
        log(f"[OK] free {free / GB:.0f} GB, floor {FLOOR / GB:.0f} GB")
        state["last_ok"] = now
        STATE.write_text(json.dumps(state))
    return "ok"


def main():
    free = shutil.disk_usage(WATCH).free
    try:
        run(free, Transmission(RPC))
    except (OSError, RuntimeError) as e:
        log(f"FAILED to reach Transmission ({e}); free {free / GB:.0f} GB")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
