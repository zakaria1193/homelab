"""Management and inventory of tmux sessions for the homelab cockpit.

All terminal shells started from the cockpit run as named tmux sessions (prefixed
with `cockpit-` or `STATUS_TMUX_PREFIX`) so sessions persist across browser
disconnects, reloads, or service restarts.
"""

import os
import re
import shutil
import subprocess
import time

TMUX_PREFIX = os.environ.get("STATUS_TMUX_PREFIX", "cockpit-")
NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")


def is_available():
    """Whether the tmux executable is present on the host."""
    return shutil.which("tmux") is not None


def sanitize_name(name):
    """Clean a string to be a valid tmux session name (no colons or spaces)."""
    raw = str(name or "").strip()
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw).strip("-")
    return clean or "default"


def session_name_for_check(check_or_name, where="auto", cmd=""):
    """Derive the standard tmux session name for a service check."""
    if isinstance(check_or_name, dict):
        name = check_or_name.get("name", "terminal")
    else:
        name = str(check_or_name or "terminal")

    clean = sanitize_name(name)
    if where == "host":
        clean += "-host"
    if cmd:
        clean += "-%s" % sanitize_name(cmd)

    if clean.startswith(TMUX_PREFIX):
        return clean
    return "%s%s" % (TMUX_PREFIX, clean)


def has_session(session_name):
    """Check if a tmux session currently exists."""
    if not is_available() or not session_name:
        return False
    try:
        res = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return res.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _human_duration(seconds):
    seconds = max(int(seconds), 0)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return "%dd %dh" % (days, hours)
    if hours:
        return "%dh %dm" % (hours, minutes)
    return "%dm" % minutes


def list_sessions():
    """Return an inventory of active tmux sessions."""
    if not is_available():
        return []

    cmd = [
        "tmux",
        "list-sessions",
        "-F",
        "#{session_name}\t#{session_created}\t#{session_attached}\t#{session_windows}\t#{session_width}x#{session_height}",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return []

    if res.returncode != 0 or not res.stdout.strip():
        return []

    now = time.time()
    sessions = []
    for line in res.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        name, created_str, attached_str, windows_str, size = parts[:5]
        try:
            created_ts = int(created_str)
        except ValueError:
            created_ts = int(now)
        try:
            attached_count = int(attached_str)
        except ValueError:
            attached_count = 0
        try:
            windows_count = int(windows_str)
        except ValueError:
            windows_count = 1

        age = max(0, int(now - created_ts))
        is_cockpit = name.startswith(TMUX_PREFIX)
        service_name = name[len(TMUX_PREFIX):] if is_cockpit else ""

        sessions.append(
            {
                "name": name,
                "created": created_ts,
                "created_human": "%s ago" % _human_duration(age),
                "attached": attached_count > 0,
                "attached_count": attached_count,
                "windows": windows_count,
                "size": size,
                "is_cockpit": is_cockpit,
                "service_name": service_name,
            }
        )

    # Sort: cockpit sessions first, then newest first
    sessions.sort(key=lambda s: (not s["is_cockpit"], -s["created"]))
    return sessions


def configure_tmux_server():
    """Ensure global options are set for full-screen responsive sizing."""
    if not is_available():
        return
    tmux_status = os.environ.get("STATUS_TMUX_STATUS_BAR", "off")
    for opt, val in [
        ("window-size", "latest"),
        ("default-size", "220x60"),
        ("status", tmux_status),
    ]:
        try:
            subprocess.run(["tmux", "set-option", "-g", opt, val], capture_output=True, timeout=2, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        subprocess.run(["tmux", "set-window-option", "-g", "aggressive-resize", "on"], capture_output=True, timeout=2, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def ensure_session(session_name, cwd=None, inner_argv=None, init_command=""):
    """Ensure a tmux session exists; creates it with inner_argv and init_command if new."""
    if not is_available():
        return session_name

    configure_tmux_server()

    if has_session(session_name):
        return session_name

    if inner_argv is None:
        inner_argv = [os.environ.get("SHELL", "/bin/sh"), "-l"]

    cmd = ["tmux", "new-session", "-d", "-s", session_name, "-x", "220", "-y", "60"]
    if cwd and os.path.isdir(cwd):
        cmd += ["-c", cwd]
    cmd += inner_argv

    try:
        subprocess.run(cmd, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return session_name

    if init_command and init_command.strip():
        time.sleep(0.3)
        try:
            subprocess.run(
                ["tmux", "send-keys", "-t", session_name, init_command.strip(), "C-m"],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    return session_name


def kill_session(session_name):
    """Terminate an active tmux session."""
    if not is_available():
        return {"ok": False, "message": "tmux is not installed on the host."}

    clean = sanitize_name(session_name)
    if not has_session(clean):
        return {"ok": False, "message": "Session %r not found." % session_name}

    try:
        res = subprocess.run(
            ["tmux", "kill-session", "-t", clean],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        ok = res.returncode == 0
        msg = (res.stdout + res.stderr).strip() or ("Session %s terminated." % clean)
        return {"ok": ok, "message": msg}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "message": "Failed to kill session: %s" % exc}


def create_session(name, cwd=None, command=None):
    """Create a new tmux session."""
    if not is_available():
        return {"ok": False, "message": "tmux is not installed on the host."}

    raw = (name or "").strip()
    if not raw:
        return {"ok": False, "message": "Session name cannot be empty."}

    clean = sanitize_name(raw)
    session_name = clean if clean.startswith(TMUX_PREFIX) else ("%s%s" % (TMUX_PREFIX, clean))

    if has_session(session_name):
        return {"ok": False, "message": "Session %r already exists." % session_name}

    if cwd:
        cwd = os.path.expanduser(cwd)
        if not os.path.isdir(cwd):
            return {"ok": False, "message": "Working directory %r does not exist." % cwd}

    ensure_session(session_name, cwd=cwd, init_command=command or "")
    return {"ok": True, "message": "Created session %s." % session_name, "session": session_name}


def rename_session(old_name, new_name):
    """Rename an active tmux session."""
    if not is_available():
        return {"ok": False, "message": "tmux is not installed on the host."}

    raw_old = (old_name or "").strip()
    raw_new = (new_name or "").strip()
    if not raw_old:
        return {"ok": False, "message": "Original session name is required."}
    if not raw_new:
        return {"ok": False, "message": "New session name cannot be empty."}

    clean_old = sanitize_name(raw_old)
    clean_new = sanitize_name(raw_new)

    if not clean_old.startswith(TMUX_PREFIX):
        clean_old = "%s%s" % (TMUX_PREFIX, clean_old)
    if not clean_new.startswith(TMUX_PREFIX):
        clean_new = "%s%s" % (TMUX_PREFIX, clean_new)

    if not has_session(clean_old):
        return {"ok": False, "message": "Session %r not found." % clean_old}
    if clean_old != clean_new and has_session(clean_new):
        return {"ok": False, "message": "Session %r already exists." % clean_new}

    try:
        res = subprocess.run(
            ["tmux", "rename-session", "-t", clean_old, clean_new],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        ok = res.returncode == 0
        msg = (res.stdout + res.stderr).strip() or ("Session renamed to %s." % clean_new)
        return {"ok": ok, "message": msg, "session": clean_new}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "message": "Failed to rename session: %s" % exc}
