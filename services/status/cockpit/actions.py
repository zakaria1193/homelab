"""Changes the page can make: enable/disable a unit, add/remove a
preconfigured AI session in services.conf."""

import configparser
import os
import re
import subprocess

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
                stderr=subprocess.DEVNULL
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

    parser = configparser.ConfigParser()
    parser.read(CONFIG_PATH)
    if parser.has_section(clean_name):
        return {"ok": False, "message": f"Session [{clean_name}] already exists"}

    block = f"\n[{clean_name}]\ngroup = AI Sessions\ntype = shell\ncommand = claude\nicon = terminal\nnote = {note.strip() or clean_name}\ndir = {expanded_dir}\ncustom = 1\n"
    with open(CONFIG_PATH, "a", encoding="utf-8") as f:
        f.write(block)

    # Auto-commit changes to git
    try:
        subprocess.run(["git", "add", CONFIG_PATH], cwd=REPO_ROOT, check=False)
        subprocess.run(
            ["git", "commit", "-m", f"feat(status): add preconfigured AI session {clean_name}"],
            cwd=REPO_ROOT,
            check=False,
        )
    except Exception:
        pass

    invalidate()

    return {"ok": True, "name": clean_name}


def delete_ai_session(name):
    """Delete a preconfigured AI session from services.conf and git-commit it."""
    clean_name = name.strip()
    if not os.path.isfile(CONFIG_PATH):
        return {"ok": False, "message": "services.conf not found"}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = rf"(?m)^\[{re.escape(clean_name)}\]\s*\n(?:^(?!\s*\[).*$\n?)*"
    new_content, count = re.subn(pattern, "", content)
    if count == 0:
        return {"ok": False, "message": f"Session [{clean_name}] not found in config"}

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    # Auto-commit changes to git
    try:
        subprocess.run(["git", "add", CONFIG_PATH], cwd=REPO_ROOT, check=False)
        subprocess.run(
            ["git", "commit", "-m", f"feat(status): remove preconfigured AI session {clean_name}"],
            cwd=REPO_ROOT,
            check=False,
        )
    except Exception:
        pass

    invalidate()

    return {"ok": True}
