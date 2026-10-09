"""Probes: how each check type in services.conf is turned into a state,
plus the per-service helpers built on them (logs, working directory)."""

import os
import pwd
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import claude_rc
import obsidian_sync

from .config import (
    DOWN,
    LOG_LINES_MAX,
    LOG_TIMEOUT,
    REPO_ROOT,
    SHELL,
    TERMINAL_ENABLED,
    TERMINAL_SHELL,
    TIMEOUT,
    UNKNOWN,
    UP,
    WARN,
    load_checks,
    resolve_path,
)


def _run(cmd):
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=TIMEOUT, check=False
    )


def _boot_uptime():
    with open("/proc/uptime") as handle:
        return float(handle.read().split()[0])


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


def _systemd_properties(unit, user):
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd += [
        "show",
        "-p", "ActiveState",
        "-p", "SubState",
        "-p", "UnitFileState",
        "-p", "LoadState",
        "-p", "ActiveEnterTimestampMonotonic",
        unit,
    ]
    try:
        result = _run(cmd)
    except (subprocess.TimeoutExpired, OSError):
        return {}
    props = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition("=")
        props[key] = value
    return props


def _systemd_resolve(unit, wanted):
    """Return (properties, is_user_scope) for a unit, auto-detecting scope."""
    scopes = [True, False] if wanted == "systemd" else [wanted == "systemd-user"]
    for user in scopes:
        candidate = _systemd_properties(unit, user)
        if candidate.get("LoadState") == "loaded":
            return candidate, user
    return {}, False


def check_systemd(check):
    """Probe a unit, auto-detecting user vs system scope unless pinned."""
    unit = check["unit"]
    props, scope_user = _systemd_resolve(unit, check["type"])

    if not props or props.get("LoadState") != "loaded":
        return {"state": UNKNOWN, "detail": "unit not installed", "meta": "systemd"}

    active = props.get("ActiveState", "unknown")
    sub = props.get("SubState", "")
    enabled = props.get("UnitFileState", "")
    scope = "user" if scope_user else "system"

    uptime = ""
    monotonic = int(props.get("ActiveEnterTimestampMonotonic", "0") or 0)
    if monotonic > 0:
        uptime = _human_duration(_boot_uptime() - monotonic / 1_000_000)

    if active == "active":
        state = UP
    elif active in ("activating", "reloading", "deactivating"):
        state = WARN
    else:
        state = DOWN

    detail = "%s (%s)" % (active, sub) if sub else active
    meta = " · ".join(filter(None, ["systemd/%s" % scope, enabled, uptime]))
    return {
        "state": state,
        "detail": detail,
        "meta": meta,
        "unit_file_state": enabled,
        "unit_enabled": enabled in ("enabled", "enabled-runtime"),
        "scope_user": scope_user,
    }


def check_docker(check):
    name = check["container"]
    try:
        result = _run(
            [
                "docker", "ps", "-a",
                "--filter", "name=^%s$" % name,
                "--format", "{{.State}}\t{{.Status}}",
            ]
        )
    except (subprocess.TimeoutExpired, OSError):
        return {"state": UNKNOWN, "detail": "docker unavailable", "meta": "docker"}

    line = result.stdout.strip().splitlines()
    if not line:
        return {"state": UNKNOWN, "detail": "no such container", "meta": "docker"}

    container_state, _, status = line[0].partition("\t")
    if container_state == "running":
        state = WARN if "unhealthy" in status else UP
    elif container_state in ("restarting", "created", "paused"):
        state = WARN
    else:
        state = DOWN
    return {"state": state, "detail": status or container_state, "meta": "docker"}


def check_http(check):
    url = check["url"]
    request = Request(url, headers={"User-Agent": "homelab-cockpit/1.0"})
    started = time.monotonic()
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            code = response.status
    except HTTPError as exc:
        code = exc.code
    except (URLError, socket.timeout, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return {"state": DOWN, "detail": "unreachable: %s" % reason, "meta": "http"}

    elapsed = int((time.monotonic() - started) * 1000)
    # 401/403 mean the service is up and simply asking for credentials.
    state = UP if code < 500 else WARN
    return {"state": state, "detail": "HTTP %d" % code, "meta": "http · %dms" % elapsed}


def check_port(check):
    host, port = check["host"], check["port"]
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT):
            pass
    except OSError as exc:
        return {"state": DOWN, "detail": "closed: %s" % exc.strerror, "meta": "tcp"}
    elapsed = int((time.monotonic() - started) * 1000)
    return {"state": UP, "detail": "port %d open" % port, "meta": "tcp · %dms" % elapsed}


def tail_file(path, lines):
    """Read the last `lines` lines without loading a huge file into memory."""
    chunk = 256 * 1024
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(size - chunk, 0))
        data = handle.read()
    text = data.decode("utf-8", errors="replace")
    if size > chunk:
        text = text.split("\n", 1)[-1]  # drop the partial first line
    return "\n".join(text.splitlines()[-lines:])


def check_logfile(check):
    """Report on a job that only leaves behind a log file (e.g. a cron task)."""
    path = check["path"]
    if not path:
        return {"state": UNKNOWN, "detail": "no path configured", "meta": "logfile"}
    if not os.path.isfile(path):
        return {"state": UNKNOWN, "detail": "log file not found", "meta": path}

    age = time.time() - os.path.getmtime(path)
    detail = "last run %s ago" % _human_duration(age)
    state = UP

    tail = tail_file(path, 200)
    fail_pat = check.get("fail_pattern")
    ok_pat = check.get("ok_pattern")
    fail_idx = tail.rfind(fail_pat) if fail_pat else -1
    ok_idx = tail.rfind(ok_pat) if ok_pat else -1

    if fail_idx != -1 and (ok_idx == -1 or fail_idx > ok_idx):
        state = WARN
        detail = "last run reported errors (%s ago)" % _human_duration(age)
    elif ok_pat and ok_idx == -1:
        state = WARN
        detail = "last run did not report success (%s ago)" % _human_duration(age)

    max_age = check["max_age_hours"]
    if max_age and age > max_age * 3600:
        state = WARN
        detail = "stale: no run in %s" % _human_duration(age)

    size = "%.0f KiB" % (os.path.getsize(path) / 1024)
    return {"state": state, "detail": detail, "meta": "logfile · %s" % size}


PROBES = {
    "systemd": check_systemd,
    "systemd-user": check_systemd,
    "systemd-system": check_systemd,
    "docker": check_docker,
    "http": check_http,
    "port": check_port,
    "logfile": check_logfile,
}


def login_shell():
    if TERMINAL_SHELL:
        return TERMINAL_SHELL
    try:
        return pwd.getpwuid(os.getuid()).pw_shell or "/bin/sh"
    except KeyError:
        return os.environ.get("SHELL", "/bin/sh")


def working_dir(check):
    """Directory a shell for this service should open in.

    Explicit `dir` wins; otherwise a systemd unit tells us its own
    WorkingDirectory, which for homelab services is the service directory.
    """
    if check["dir"]:
        if os.path.isdir(check["dir"]):
            return check["dir"]

    if check["type"].startswith("systemd"):
        props, user_scope = _systemd_resolve(check["unit"], check["type"])
        if props:
            cmd = ["systemctl"]
            if user_scope:
                cmd.append("--user")
            cmd += ["show", "-p", "WorkingDirectory", "--value", check["unit"]]
            try:
                found = _run(cmd).stdout.strip()
            except (subprocess.TimeoutExpired, OSError):
                found = ""
            # systemd may report it as "/path" or "!/path" (ignore-failure).
            found = found.lstrip("!-").strip()
            if found and os.path.isdir(found):
                return found

    if check["type"] == "logfile" and check["path"]:
        parent = os.path.dirname(check["path"])
        if os.path.isdir(parent):
            return parent

    return REPO_ROOT


def log_source(check):
    """Where this service's logs come from, as (kind, target).

    Config may override with `logs = journal:<unit>` / `docker:<name>` /
    `file:<path>`; otherwise it is derived from the check type.
    """
    override = check.get("logs", "")
    if override:
        kind, _, target = override.partition(":")
        kind, target = kind.strip(), target.strip()
        return kind, resolve_path(target) if kind == "file" else target
    kind = check["type"]
    if kind.startswith("systemd"):
        return "journal", check["unit"]
    if kind == "docker":
        return "docker", check["container"]
    if kind == "logfile":
        return "file", check["path"]
    return "", ""


def fetch_logs(check, lines):
    """Return (text, source_label) for a configured service. Never shells out
    with anything a client supplied: the target always comes from services.conf.
    """
    kind, target = log_source(check)
    lines = max(1, min(lines, LOG_LINES_MAX))

    if kind == "journal":
        _, user_scope = _systemd_resolve(target, check["type"])
        cmd = ["journalctl"]
        if user_scope:
            cmd.append("--user")
        cmd += ["-u", target, "-n", str(lines), "--no-pager", "--output", "short-iso"]
        label = "journalctl %s-u %s" % ("--user " if user_scope else "", target)
    elif kind == "docker":
        cmd = ["docker", "logs", "--tail", str(lines), "--timestamps", target]
        label = "docker logs %s" % target
    elif kind == "file":
        if not target or not os.path.isfile(target):
            return "Log file not found: %s" % (target or "<unset>"), target
        try:
            return tail_file(target, lines), target
        except OSError as exc:
            return "Could not read %s: %s" % (target, exc), target
    else:
        return (
            "No log source for this check type (%s).\n"
            "Add `logs = journal:<unit>` / `docker:<name>` / `file:<path>` "
            "to its services.conf section." % check["type"]
        ), ""

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=LOG_TIMEOUT, check=False
        )
    except subprocess.TimeoutExpired:
        return "Timed out running: %s" % " ".join(cmd), label
    except OSError as exc:
        return "Could not run %s: %s" % (cmd[0], exc), label

    output = (result.stdout or "") + (result.stderr or "")
    return output.strip() or "(no log output)", label


def rc_check(name):
    """Synthesise a shell for `rc:<verb>:<instance>`, or None if that is not one.

    A privileged instance action (a system unit, no passwordless sudo) cannot
    run from the API, but it can run in a terminal, where sudo may ask for the
    password. The command is built here from a known verb and a known instance
    - never from the text the browser sent - so this stays as constrained as
    every other shell the page offers.
    """
    if not name.startswith("rc:"):
        return None
    _, _, rest = name.partition("rc:")
    verb, _, instance = rest.partition(":")
    if not claude_rc.known(instance):
        return None
    if verb == "logs":
        # The journal of an instance's unit, through the page that already
        # knows how to show a journal.
        return {
            "name": name, "group": "AI", "type": "systemd",
            "unit": claude_rc.unit_for(instance), "container": "",
            "url": "", "host": "", "port": 0, "link": "", "remote": "",
            "note": "", "icon": "claude", "pinned": False, "headline": False,
            "alt_links": [],
            "node": "", "logs": "", "ok_pattern": "", "fail_pattern": "",
            "max_age_hours": 0.0, "path": "", "command": "",
            "dir": claude_rc.RC_DIR,
        }
    if verb not in claude_rc.VERBS:
        return None
    return {
        "name": name,
        "group": "AI",
        "type": SHELL,
        "unit": claude_rc.unit_for(instance),
        "container": "",
        "url": "", "host": "", "port": 0, "link": "", "remote": "",
        "note": "", "icon": "claude", "pinned": False, "headline": False,
        "alt_links": [],
        "node": "", "logs": "", "ok_pattern": "", "fail_pattern": "",
        "max_age_hours": 0.0, "path": "",
        "command": "make %s%s" % (verb, " INSTANCE=%s" % instance if instance else ""),
        "dir": claude_rc.RC_DIR,
    }


def find_check(name):
    """Look a service up by exact configured name (never by client-supplied path)."""
    return rc_check(name) or next(
        (c for c in load_checks() if c["name"] == name), None
    )


def run_check(check):
    probe = PROBES.get(check["type"])
    if probe is None:
        result = {"state": UNKNOWN, "detail": "unknown check type '%s'" % check["type"], "meta": ""}
    else:
        try:
            result = probe(check)
        except Exception as exc:  # a broken probe must not take down the page
            result = {"state": UNKNOWN, "detail": "probe error: %s" % exc, "meta": ""}
    result.update(
        {
            "name": check["name"],
            "group": check["group"],
            "type": check["type"],
            "link": check["link"],
            "remote": check["remote"],
            "endpoint": check.get("endpoint", ""),
            "alt_link": check.get("alt_link", ""),
            "alt_label": check.get("alt_label", ""),
            "alt_icon": check.get("alt_icon", ""),
            "alt_links": check.get("alt_links", []),
            "note": check["note"],
            "pinned": check["pinned"],
            "headline": check["headline"],
            "node": check["node"],
            "icon": check["icon"],
            "command": check["command"],
            # An entry that names a `command` has one obvious thing to run, so
            # its shell is worth a button on the chip rather than only on the
            # card - that is what merges a web session and its local terminal
            # into a single chip.
            "has_chip_shell": TERMINAL_ENABLED and bool(check["command"]),
            "has_logs": bool(log_source(check)[0]),
            "has_terminal": TERMINAL_ENABLED,
            # Containers get a second shell on the host, next to their compose
            # file, so `docker compose` itself is one click away too.
            "has_host_shell": TERMINAL_ENABLED
            and check["type"] == "docker"
            and bool(check["dir"]),
            "can_toggle": (
                check["type"].startswith("systemd")
                and result.get("unit_file_state") in ("enabled", "disabled", "enabled-runtime", "linked", "linked-runtime")
            ),
            "unit_file_state": result.get("unit_file_state", ""),
            "unit_enabled": result.get("unit_enabled", False),
        }
    )
    if check["name"] == "obsidian-sync":
        try:
            app_running = obsidian_sync.is_obsidian_running()
            sync_st = obsidian_sync.get_sync_state()
            last_ts = sync_st.get("last_sync_timestamp", 0)
            ago = _human_duration(time.time() - last_ts) if last_ts > 0 else "never"
            trig = sync_st.get("last_trigger", "sync")

            if app_running:
                status_note = f"Obsidian app running (30m auto-sync active) · last sync: {ago} ago ({trig})"
            else:
                next_in_s = max(0, 3600 - (time.time() - last_ts)) if last_ts > 0 else 0
                next_str = _human_duration(next_in_s) if next_in_s > 0 else "due now"
                status_note = f"Obsidian app closed · keeper active · synced {ago} ago · next in {next_str}"

            cur_detail = result.get("detail", "")
            result["detail"] = f"{cur_detail} · {status_note}" if cur_detail else status_note
        except Exception:
            pass
    return result
