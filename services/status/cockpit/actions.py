"""Changes the page can make: enable/disable a unit, add/remove a
preconfigured AI session in services.conf."""

import configparser
import os
import re
import subprocess

from . import conf_edit
from .config import CONFIG_PATH, REPO_ROOT, TIMEOUT
from .probes import _systemd_resolve, find_check
from .snapshot import invalidate


def toggle_unit_enable(service_name, target_enabled=None):
    """Enable or disable a systemd service unit.

    If target_enabled is None, toggles current state.
    Returns a dict with {"ok": bool, "enabled": bool, "message": str}.
    """
    check = find_check(service_name)
    if not check:
        return {"ok": False, "message": f"service '{service_name}' not found"}
    if not check["type"].startswith("systemd"):
        return {"ok": False, "message": f"service '{service_name}' is not a systemd unit"}

    unit = check["unit"]
    props, scope_user = _systemd_resolve(unit, check["type"])
    if not props or props.get("LoadState") != "loaded":
        return {"ok": False, "message": f"unit '{unit}' not installed or loaded"}

    current_state = props.get("UnitFileState", "")
    currently_enabled = current_state in ("enabled", "enabled-runtime")

    if target_enabled is None:
        new_enabled = not currently_enabled
    else:
        new_enabled = bool(target_enabled)

    action = "enable" if new_enabled else "disable"

    if scope_user:
        cmd = ["systemctl", "--user", action, unit]
    else:
        cmd = ["sudo", "-n", "systemctl", action, unit]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": f"timed out running {action} on {unit}"}
    except OSError as exc:
        return {"ok": False, "message": f"failed to run command: {exc}"}

    if res.returncode != 0:
        err = (res.stderr or res.stdout or "").strip()
        return {"ok": False, "message": f"systemctl {action} failed: {err}"}

    invalidate()  # the next poll re-probes immediately

    return {
        "ok": True,
        "enabled": new_enabled,
        "message": f"{check['name']} {action}d successfully",
    }


def add_ai_session(name, dir_path, note=""):
    """Add a preconfigured AI session to services.conf and git-commit it."""
    if any(c in f"{dir_path}{note}" for c in "\r\n"):
        # One line per value: a newline would write extra keys or sections.
        return {"ok": False, "message": "Directory and note must be a single line"}
    expanded_dir = os.path.realpath(os.path.expanduser(dir_path.strip()))
    if not os.path.exists(expanded_dir):
        return {"ok": False, "message": f"Directory not found: {expanded_dir}"}
    raw_name = (name or "").strip().lower()
    if not raw_name:
        try:
            git_root = subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=expanded_dir,
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=10,
            ).strip()
            if git_root:
                raw_name = os.path.basename(git_root).lower()
        except Exception:
            pass
        if not raw_name:
            raw_name = os.path.basename(expanded_dir.rstrip("/")).lower()
    clean_name = re.sub(r"[^a-zA-Z0-9_-]", "-", raw_name).strip("-")
    if not clean_name:
        return {"ok": False, "message": "Invalid session name (use alphanumeric and hyphens)"}

    fields = [
        ("group", "AI Sessions"),
        ("type", "shell"),
        ("command", "claude"),
        ("icon", "terminal"),
        ("note", note.strip() or clean_name),
        ("dir", expanded_dir),
        ("custom", "1"),
    ]
    result = conf_edit.add_section(
        CONFIG_PATH,
        clean_name,
        fields,
        commit_message=f"feat(status): add preconfigured AI session {clean_name}",
        repo_root=REPO_ROOT,
    )
    if not result["ok"]:
        return {"ok": False, "message": result["message"] or f"Session [{clean_name}] already exists"}

    return {"ok": True, "name": clean_name}


def delete_ai_session(name):
    """Delete a preconfigured AI session from services.conf and git-commit it."""
    clean_name = name.strip()
    if not os.path.isfile(CONFIG_PATH):
        return {"ok": False, "message": "services.conf not found"}

    # Only sessions added from the page; every other entry is edited by hand.
    parser = configparser.ConfigParser()
    parser.read(CONFIG_PATH)
    if not parser.has_section(clean_name):
        return {"ok": False, "message": f"Session [{clean_name}] not found in config"}
    if parser.get(clean_name, "custom", fallback="0").strip() != "1":
        return {"ok": False, "message": f"[{clean_name}] was not added from the page, so it cannot be removed here"}

    result = conf_edit.remove_section(
        CONFIG_PATH,
        clean_name,
        commit_message=f"feat(status): remove preconfigured AI session {clean_name}",
        repo_root=REPO_ROOT,
    )
    if not result["ok"]:
        return {"ok": False, "message": result["message"] or f"Session [{clean_name}] not found in config"}

    return {"ok": True}
