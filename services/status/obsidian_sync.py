#!/usr/bin/env python3
"""Obsidian Remotely Save sync: trigger it and record when it last ran.

Used by obsidian_sync_daemon.py (the hourly keeper) and by the cockpit's
obsidian-sync card. pjm writes the same state file after its own syncs.
"""

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time


def _write_file_atomically(fpath, content):
    """Write text content to file atomically via a temporary file."""
    dir_name = os.path.dirname(fpath)
    os.makedirs(dir_name, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
        tf.write(content)
        temp_name = tf.name
    os.replace(temp_name, fpath)


def is_obsidian_running():
    """Check whether the Obsidian desktop application is currently running."""
    try:
        if sys.platform.startswith("linux") and os.path.isdir("/proc"):
            for pid in os.listdir("/proc"):
                if not pid.isdigit():
                    continue
                comm_path = os.path.join("/proc", pid, "comm")
                if os.path.isfile(comm_path):
                    try:
                        with open(comm_path, "r", encoding="utf-8", errors="ignore") as f:
                            if f.read().strip().lower() == "obsidian":
                                return True
                    except (OSError, IOError):
                        pass
        if shutil.which("pgrep"):
            res = subprocess.run(["pgrep", "-x", "obsidian"], capture_output=True, timeout=2, check=False)
            if res.returncode == 0 and res.stdout.strip():
                return True
        if shutil.which("ps"):
            res = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True, text=True, timeout=2, check=False)
            if any(line.strip().lower() == "obsidian" for line in res.stdout.splitlines()):
                return True
    except Exception:
        pass
    return False


def get_sync_state_file():
    """Get location of the sync state JSON file."""
    override = os.environ.get("STATUS_OBSIDIAN_SYNC_STATE")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    home = os.path.expanduser("~")
    return os.path.join(home, ".config", "obsidian", "sync_state.json")


def get_sync_state():
    """Read the current Obsidian sync state."""
    fpath = get_sync_state_file()
    if os.path.isfile(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {
        "last_sync_timestamp": 0.0,
        "last_sync_time": None,
        "last_trigger": "never",
        "status": "idle",
        "detail": "No sync has been recorded yet.",
    }


def record_sync_event(trigger_reason="manual", status="ok", detail=""):
    """Record a sync event to the sync state JSON file."""
    fpath = get_sync_state_file()
    try:
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        now_ts = time.time()
        now_iso = datetime.datetime.now().isoformat()
        state = {
            "last_sync_timestamp": now_ts,
            "last_sync_time": now_iso,
            "last_trigger": trigger_reason,
            "status": status,
            "detail": detail,
        }
        _write_file_atomically(fpath, json.dumps(state, indent=2))
        return state
    except Exception as exc:
        return {"error": str(exc)}


def dispatch_obsidian_sync(reason="manual"):
    """Synchronously dispatch Obsidian Remotely Save sync and record state."""
    uri = "obsidian://remotely-save-sync"
    detail = ""
    status = "ok"

    try:
        time.sleep(0.3)

        if sys.platform == "darwin":
            if shutil.which("open"):
                res = subprocess.run(["open", uri], capture_output=True, text=True, timeout=5, check=False)
                detail = res.stdout.strip() or res.stderr.strip() or "Dispatched via open"
            else:
                status = "error"
                detail = "open command not found"
        elif sys.platform == "win32":
            try:
                os.startfile(uri)  # type: ignore
                detail = "Dispatched via os.startfile"
            except Exception as e:
                res = subprocess.run(["cmd", "/c", "start", "", uri], shell=True, capture_output=True, text=True, timeout=5, check=False)
                detail = res.stdout.strip() or str(e)
        else:
            # Linux / Unix
            env = dict(os.environ)
            try:
                uid = os.getuid()
            except Exception:
                uid = 1000

            if "DISPLAY" not in env:
                env["DISPLAY"] = ":0"
            if "XAUTHORITY" not in env:
                for auth in [
                    f"/run/user/{uid}/gdm/Xauthority",
                    f"/run/user/{uid}/Xauthority",
                    os.path.expanduser("~/.Xauthority"),
                ]:
                    if os.path.isfile(auth):
                        env["XAUTHORITY"] = auth
                        break
            if "DBUS_SESSION_BUS_ADDRESS" not in env:
                bus_path = f"/run/user/{uid}/bus"
                if os.path.exists(bus_path):
                    env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus_path}"

            xdg_open = shutil.which("xdg-open")
            if xdg_open:
                try:
                    res = subprocess.run(
                        [xdg_open, uri],
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    detail = res.stdout.strip() or res.stderr.strip() or "Dispatched via xdg-open"
                except subprocess.TimeoutExpired:
                    subprocess.Popen(
                        [xdg_open, uri],
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    detail = "Dispatched and launched Obsidian in background"
            else:
                status = "error"
                detail = "xdg-open not found"
    except Exception as exc:
        status = "error"
        detail = str(exc)

    record_sync_event(trigger_reason=reason, status=status, detail=detail)
    return {
        "ok": status == "ok",
        "status": status,
        "trigger": reason,
        "detail": detail,
        "timestamp": time.time(),
    }
