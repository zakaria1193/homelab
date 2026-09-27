"""Antigravity Remote Control instances, driven from the cockpit.

Matches the architecture and lifecycle of claude_rc.py:
- Reads instances off disk (.env.<name>)
- Inspects systemd user units (agy-remote-control[-<name>])
- Drives the Makefile targets for start, stop, restart, upgrade, logs
- Creates and deletes instances and registers them in services.conf
"""

import os
import re
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
AGY_RC_DIR = os.environ.get("STATUS_AGY_RC_DIR") or os.path.join(
    REPO_ROOT, "services", "AI", "antigravityRcAI"
)
MAKE_TIMEOUT = float(os.environ.get("STATUS_RC_TIMEOUT") or "60")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
VERBS = ("start", "restart", "stop", "upgrade", "status", "doctor")
DEFAULT_LABEL = "default"

DEFAULTS = {
    "AGY_RC_WORKDIR": REPO_ROOT,
    "AGY_RC_NAME": "homelab",
    "AGY_RC_PORT": "4400",
}


def unit_for(name=""):
    return "agy-remote-control-%s" % name if name else "antigravity-cli-daemon"


def env_file_for(name):
    return os.path.join(AGY_RC_DIR, ".env.%s" % name if name else ".env")


def config_section_for(name):
    return "antigravity-rc-%s" % name if name else "antigravity-rc"


def _read_env(path):
    values = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        return {}
    return values


def _systemd_state(unit):
    """(state, detail, scope) for a unit in user scope."""
    try:
        out = subprocess.run(
            ["systemctl", "--user", "show", unit, "--no-page",
             "--property=LoadState,ActiveState,SubState,UnitFileState,MainPID"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "unknown", "failed to check systemd", "user"

    props = dict(
        line.split("=", 1) for line in out.strip().splitlines() if "=" in line
    )
    if props.get("LoadState") in ("", "not-found", None):
        return "down", "no unit installed", "user"

    active = props.get("ActiveState", "unknown")
    state = {"active": "up", "failed": "down", "activating": "warn"}.get(
        active, "down" if active == "inactive" else "unknown"
    )
    pid = props.get("MainPID", "0")
    pid_str = " · PID %s" % pid if pid and pid != "0" else ""
    detail = "%s (%s)%s" % (active, props.get("SubState", "?"), pid_str)
    return state, detail, "user"


def _names():
    names = [""]
    for entry in sorted(os.listdir(AGY_RC_DIR) if os.path.isdir(AGY_RC_DIR) else []):
        if not entry.startswith(".env.") or entry == ".env.example":
            continue
        name = entry[len(".env."):]
        if name.endswith(".example"):
            name = name[: -len(".example")]
        if name and name not in names and NAME_RE.match(name):
            names.append(name)
    return names


def describe(name=""):
    env_path = env_file_for(name)
    values = _read_env(env_path)
    unit = unit_for(name)
    state, detail, scope = _systemd_state(unit)
    workspace = values.get("AGY_RC_WORKDIR", DEFAULTS["AGY_RC_WORKDIR"])
    instance_name = values.get("AGY_RC_NAME", name or DEFAULTS["AGY_RC_NAME"])
    port = values.get("AGY_RC_PORT", DEFAULTS["AGY_RC_PORT"] if not name else "")
    log_file = os.path.expanduser("~/.antigravity/agy_daemon%s.log" % ("_" + name if name else ""))

    return {
        "name": name,
        "label": name or DEFAULT_LABEL,
        "instance_name": instance_name,
        "unit": "%s.service" % unit,
        "env_file": os.path.relpath(env_path, REPO_ROOT),
        "has_env": os.path.isfile(env_path),
        "workspace": workspace,
        "workspace_exists": os.path.isdir(workspace),
        "hub_port": port or "auto",
        "dashboard_url": "https://antigravity.google.com/",
        "log_file": log_file,
        "state": state,
        "detail": detail,
        "scope": scope,
        "removable": bool(name),
    }


def instances():
    return [describe(name) for name in _names()]


def known(name):
    return name in _names()


def validate_name(name):
    if not NAME_RE.match(name or ""):
        return "Use 1-32 characters: lowercase letters, digits and dashes."
    if name in _names():
        return "An instance named %r already exists." % name
    return ""


def deduce_name_from_dir(path):
    path = os.path.realpath(os.path.expanduser(str(path or "").strip()))
    try:
        git_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()
        if git_root:
            base = os.path.basename(git_root)
            return re.sub(r"[^a-z0-9-]+", "-", base.lower()).strip("-")
    except Exception:
        pass
    base = os.path.basename(path.rstrip("/"))
    return re.sub(r"[^a-z0-9-]+", "-", base.lower()).strip("-") or "workspace"


def validate_workspace(raw):
    raw = (raw or "").strip()
    if not raw:
        return {"ok": False, "path": "", "message": "Give the workspace directory."}
    path = os.path.expanduser(raw)
    if not os.path.isabs(path):
        path = os.path.join(REPO_ROOT, path)
    path = os.path.realpath(path)
    if not os.path.exists(path):
        return {"ok": False, "path": path, "message": "%s does not exist." % path}
    if not os.path.isdir(path):
        return {"ok": False, "path": path, "message": "%s is not a directory." % path}
    if not os.access(path, os.R_OK | os.X_OK):
        return {"ok": False, "path": path, "message": "%s is not readable." % path}
    return {"ok": True, "path": path, "message": "", "deduced_name": deduce_name_from_dir(path)}


def run(verb, name=""):
    if verb not in VERBS:
        return {"ok": False, "output": "unknown action %r" % verb}
    if not known(name):
        return {"ok": False, "output": "unknown instance %r" % name}

    argv = ["make", "-C", AGY_RC_DIR, verb]
    if name:
        argv.append("INSTANCE=%s" % name)
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=MAKE_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "%s timed out after %ds" % (verb, MAKE_TIMEOUT)}
    except OSError as exc:
        return {"ok": False, "output": "could not run make: %s" % exc}

    output = (done.stdout + done.stderr).strip() or "(no output)"
    return {"ok": done.returncode == 0, "output": output}


ENV_TEMPLATE = """\
# ------------------------------------------------------------------------------
# Antigravity Remote Control - `{name}` instance
#
# Created from the homelab cockpit. Started with `make start INSTANCE={name}`,
# which installs the user unit `{unit}`.
# ------------------------------------------------------------------------------

AGY_RC_WORKDIR={workspace}
AGY_RC_NAME={instance_name}
AGY_RC_PORT={port}
"""


def create(name, workspace, port="", session="", config_path=None):
    name = (name or "").strip()
    if not name and workspace:
        name = deduce_name_from_dir(workspace)
    problem = validate_name(name)
    if problem:
        return {"ok": False, "message": problem, "output": ""}
    checked = validate_workspace(workspace)
    if not checked["ok"]:
        return {"ok": False, "message": checked["message"], "output": ""}

    body = ENV_TEMPLATE.format(
        name=name,
        unit=unit_for(name),
        workspace=checked["path"],
        instance_name=session or name,
        port=port or "",
    )
    for path in (env_file_for(name) + ".example", env_file_for(name)):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)

    result = run("start", name)
    if result["ok"] and config_path:
        register(name, checked["path"], config_path)
    return {
        "ok": result["ok"],
        "message": "Started %s in %s." % (unit_for(name), checked["path"])
        if result["ok"] else "Wrote env files, but make start failed.",
        "output": result["output"],
    }


def delete(name, config_path=None):
    if not name or not known(name):
        return {"ok": False, "message": "Unknown instance %r." % name, "output": ""}

    result = run("stop", name)
    removed = []
    for path in (env_file_for(name), env_file_for(name) + ".example"):
        if os.path.isfile(path):
            os.remove(path)
            removed.append(os.path.basename(path))
    if config_path:
        unregister(name, config_path)
    return {
        "ok": result["ok"],
        "message": "Removed %s%s." % (
            unit_for(name), " and " + ", ".join(removed) if removed else ""
        ),
        "output": result["output"],
    }


def register(name, workspace, config_path):
    section = config_section_for(name)
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return False
    if ("[%s]" % section) in text:
        return False

    where = os.path.relpath(workspace, REPO_ROOT)
    if where.startswith(".."):
        where = workspace
    block = (
        "\n# Created from the cockpit: Antigravity instance for %s\n"
        "[%s]\n"
        "group = AI\n"
        "type = systemd-user\n"
        "pinned = 1\n"
        "unit = %s\n"
        "icon = antigravity\n"
        "remote = https://antigravity.google.com/\n"
        "alt_link = /antigravity-rc\n"
        "alt_label = server\n"
        "logs = file:~/.antigravity/agy_daemon_%s.log\n"
        "note = always-on Antigravity %s workspace session\n"
        "dir = %s\n" % (name, section, unit_for(name), name, name, where)
    )
    with open(config_path, "a", encoding="utf-8") as handle:
        handle.write(block)
    return True


def unregister(name, config_path):
    section = "[%s]" % config_section_for(name)
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines(keepends=True)
    except OSError:
        return False
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == section)
    except StopIteration:
        return False
    head = start
    while head > 0 and lines[head - 1].lstrip().startswith("#"):
        head -= 1
    end = start + 1
    while end < len(lines) and not lines[end].lstrip().startswith("["):
        end += 1
    while end > start and lines[end - 1].strip() == "":
        end -= 1
    while head > 0 and lines[head - 1].strip() == "":
        head -= 1
    tail = lines[end:]
    while tail and not tail[0].strip():
        tail.pop(0)
    with open(config_path, "w", encoding="utf-8") as handle:
        handle.write("".join(lines[:head] + (["\n"] if tail else []) + tail))
    return True
