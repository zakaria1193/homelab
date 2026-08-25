#!/usr/bin/env python3
"""Homelab cockpit.

Serves an always-on HTML page (plus a JSON API) showing the live state of every
homelab service. Deliberately depends on the Python standard library only, so it
stays reproducible on a fresh machine with no package installs.

Checks are declared in services.conf; see that file for the supported keys.
"""

import base64
import configparser
import hashlib
import hmac
import html
import json
import os
import pwd
import secrets
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

import claude_rc
import terminal
import tmux_manager
import usage

HERE = os.path.dirname(os.path.abspath(__file__))
# services/status -> repository root; relative log paths resolve against it.
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))

# `systemctl --user` needs a session bus. Fill it in when we were launched
# without one (cron, a bare system unit) so user-scope units stay visible.
_runtime_dir = "/run/user/%d" % os.getuid()
if not os.environ.get("XDG_RUNTIME_DIR") and os.path.isdir(_runtime_dir):
    os.environ["XDG_RUNTIME_DIR"] = _runtime_dir

HOST = os.environ.get("STATUS_HOST", "0.0.0.0")
PORT = int(os.environ.get("STATUS_PORT", "8300"))
CONFIG_PATH = os.environ.get("STATUS_CONFIG", os.path.join(HERE, "services.conf"))
TITLE = os.environ.get("STATUS_TITLE", "Homelab Cockpit")
LINK_HOST = os.environ.get("STATUS_LINK_HOST", "")
CACHE_TTL = float(os.environ.get("STATUS_CACHE_TTL", "10"))
REFRESH = int(os.environ.get("STATUS_REFRESH", "15"))
TIMEOUT = float(os.environ.get("STATUS_TIMEOUT", "4"))
BASIC_USER = os.environ.get("STATUS_USER", "")
BASIC_PASSWORD = os.environ.get("STATUS_PASSWORD", "")
# "Remember me" on the login form: how long the signed cookie stays valid.
SESSION_COOKIE = "cockpit_session"
SESSION_DAYS = int(os.environ.get("STATUS_SESSION_DAYS") or "30")
LOG_LINES = int(os.environ.get("STATUS_LOG_LINES", "200"))
LOG_LINES_MAX = int(os.environ.get("STATUS_LOG_LINES_MAX", "2000"))
LOG_TIMEOUT = float(os.environ.get("STATUS_LOG_TIMEOUT", "15"))
# Browser shells are remote code execution: set STATUS_TERMINAL=0 to disable.
TERMINAL_ENABLED = os.environ.get("STATUS_TERMINAL", "1") not in ("0", "false", "no")
TERMINAL_IDLE = float(os.environ.get("STATUS_TERMINAL_IDLE", "900"))
TERMINAL_SHELL = os.environ.get("STATUS_TERMINAL_SHELL", "")
# The Claude Remote Control instances are started, stopped and created from the
# page; set STATUS_RC_MANAGE=0 to make that page read-only.
RC_MANAGE = os.environ.get("STATUS_RC_MANAGE", "1") not in ("0", "false", "no")
# The plan-usage health bars run `claude`/`agy` in `/usage` print mode, which
# is unavailable (or pointless) on a box that does not run either CLI.
USAGE_ENABLED = os.environ.get("STATUS_USAGE", "1") not in ("0", "false", "no")

UP, DOWN, WARN, UNKNOWN = "up", "down", "warn", "unknown"

# Pseudo check type: a terminal launcher with no service behind it.
SHELL = "shell"


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def resolve_path(value):
    """Expand ~ and resolve repo-relative paths from services.conf."""
    if not value:
        return ""
    expanded = os.path.expanduser(value)
    if os.path.isabs(expanded):
        return os.path.normpath(expanded)
    return os.path.normpath(os.path.join(REPO_ROOT, expanded))


def _parse_alt_links(section):
    alt_links_raw = section.get("alt_links", "").strip()
    alt_links = []
    if alt_links_raw:
        for part in alt_links_raw.split(","):
            part = part.strip()
            if not part:
                continue
            fields = [f.strip() for f in part.split("|")]
            href = fields[0]
            icon_name = fields[1].lower() if len(fields) > 1 and fields[1] else ""
            label = fields[2] if len(fields) > 2 and fields[2] else (icon_name or "alt")
            alt_links.append({"href": href, "icon": icon_name, "label": label})
    elif section.get("alt_link", ""):
        alt_links.append({
            "href": section.get("alt_link", ""),
            "icon": section.get("alt_icon", "").strip().lower(),
            "label": section.get("alt_label", ""),
        })
    return alt_links


def load_checks():
    parser = configparser.ConfigParser()
    if not parser.read(CONFIG_PATH):
        sys.exit("[ERROR] config file not found: %s" % CONFIG_PATH)
    if LINK_HOST:
        parser["DEFAULT"]["host"] = LINK_HOST
    # Everything the config points at %(pi)s physically runs on the Raspberry
    # Pi; the page badges those so "where does this live" needs no lookup.
    pi_host = parser["DEFAULT"].get("pi", "").strip()

    checks = []
    for name in parser.sections():
        section = parser[name]
        checks.append(
            {
                "name": name,
                "group": section.get("group", "Services"),
                "type": section.get("type", "systemd").strip().lower(),
                "unit": section.get("unit", name),
                "container": section.get("container", name),
                "url": section.get("url", ""),
                "host": section.get("probe_host", "127.0.0.1"),
                "port": section.getint("port", fallback=0),
                "link": section.get("link", ""),
                "remote": section.get("remote", ""),
                # An address you copy, not a page you open: rendered as text
                # with a copy button and never turned into a link.
                "endpoint": section.get("endpoint", ""),
                # A second front-end onto the same thing (the Antigravity web
                # session next to the Claude one), rendered as an extra button.
                "alt_link": section.get("alt_link", ""),
                "alt_label": section.get("alt_label", ""),
                "alt_icon": section.get("alt_icon", "").strip().lower(),
                "alt_links": _parse_alt_links(section),
                # Services that share a `chat_group` are different ways into
                # the SAME session (a web Remote Control console, a local
                # terminal) - the page merges them into one inert-named chip
                # with a button per way in, instead of one chip each.
                "chat_group": section.get("chat_group", "").strip().lower(),
                "note": section.get("note", ""),
                "command": section.get("command", ""),
                "icon": section.get("icon", "").strip().lower(),
                "pinned": section.getboolean("pinned", fallback=False),
                # Lifted out of its group into the page header: for the one or
                # two entries that operate the whole homelab rather than sit in it.
                "headline": section.getboolean("headline", fallback=False),
                "node": "",
                "dir": resolve_path(section.get("dir", "")),
                "path": resolve_path(section.get("path", "")),
                "logs": section.get("logs", ""),
                "ok_pattern": section.get("ok_pattern", ""),
                "fail_pattern": section.get("fail_pattern", ""),
                "max_age_hours": section.getfloat("max_age_hours", fallback=0.0),
            }
        )
        if pi_host and pi_host in " ".join(
            (checks[-1]["link"], checks[-1]["remote"], checks[-1]["url"], checks[-1]["host"])
        ):
            checks[-1]["node"] = "pi"
    return checks


# --------------------------------------------------------------------------- #
# Probes
# --------------------------------------------------------------------------- #
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
    return {"state": state, "detail": detail, "meta": meta}


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
    if check["fail_pattern"] and check["fail_pattern"] in tail:
        state = WARN
        detail = "last run reported errors (%s ago)" % _human_duration(age)
    elif check["ok_pattern"] and check["ok_pattern"] not in tail:
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
    if check["dir"] and os.path.isdir(check["dir"]):
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
            "alt_links": [], "chat_group": "",
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
        "alt_links": [], "chat_group": "",
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
            "link": check["link"],
            "remote": check["remote"],
            "endpoint": check.get("endpoint", ""),
            "alt_link": check.get("alt_link", ""),
            "alt_label": check.get("alt_label", ""),
            "alt_icon": check.get("alt_icon", ""),
            "alt_links": check.get("alt_links", []),
            "chat_group": check.get("chat_group", ""),
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
        }
    )
    return result


# --------------------------------------------------------------------------- #
# Cached snapshot
# --------------------------------------------------------------------------- #
_cache = {"at": 0.0, "payload": None}
_cache_lock = threading.Lock()


def snapshot(force=False):
    with _cache_lock:
        fresh = _cache["payload"] is not None and time.time() - _cache["at"] < CACHE_TTL
        if fresh and not force:
            return _cache["payload"]

        checks = load_checks()
        # `shell` entries are launchers, not services: they have nothing to
        # probe and never count towards the totals.
        probed = [c for c in checks if c["type"] != SHELL]
        with ThreadPoolExecutor(max_workers=max(len(probed), 1)) as pool:
            results = list(pool.map(run_check, probed))
        by_name = {r["name"]: r for r in results}

        groups = []
        index = {}
        for check in checks:  # config order decides both group and card order
            group = index.get(check["group"])
            if group is None:
                group = {"name": check["group"], "services": [], "launchers": []}
                index[check["group"]] = group
                groups.append(group)
            if check["type"] == SHELL:
                group["launchers"].append(
                    {
                        "name": check["name"],
                        "note": check["note"],
                        "command": check["command"],
                        # A launcher is a terminal unless it says otherwise.
                        "icon": check["icon"] or "terminal",
                        "enabled": TERMINAL_ENABLED,
                    }
                )
            else:
                group["services"].append(by_name[check["name"]])

        payload = {
            "title": TITLE,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "refresh": REFRESH,
            "totals": {
                state: sum(1 for r in results if r["state"] == state)
                for state in (UP, WARN, DOWN, UNKNOWN)
            },
            "count": len(results),
            # Rendered in the header next to the totals, not inside a group.
            "headline": [r for r in results if r["headline"]],
            "groups": groups,
            # Active tmux sessions inventory
            "tmux": {
                "count": len(tmux_manager.list_sessions()),
                "sessions": tmux_manager.list_sessions(),
            },
            # Plan-usage health bars, always shown at the top of the page
            # regardless of group folding - see usage.py for how they refresh.
            "usage": usage.snapshot() if USAGE_ENABLED else None,
        }
        _cache["at"] = time.time()
        _cache["payload"] = payload
        return payload


# --------------------------------------------------------------------------- #
# Terminal tickets
# --------------------------------------------------------------------------- #
# Browsers do not reliably attach basic-auth headers to WebSocket upgrades, so
# the authenticated page mints a short-lived single-use ticket instead. Each
# ticket is bound to one service or tmux session.
TICKET_TTL = 60.0
_tickets = {}
_ticket_lock = threading.Lock()


def _session_key():
    """Signing key for the remember-me cookie.

    Derived from the credential itself: nothing to store on disk, it survives a
    restart, and every outstanding session dies the moment the password
    changes - which is exactly what you want from "log everyone out".
    """
    return hashlib.sha256(
        ("homelab-cockpit|%s|%s" % (BASIC_USER, BASIC_PASSWORD)).encode("utf-8")
    ).digest()


def mint_session(days):
    """A cookie value that proves a login happened, valid for `days`."""
    expiry = int(time.time()) + max(1, days) * 86400
    signature = hmac.new(
        _session_key(), ("v1|%d" % expiry).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return "%d.%s" % (expiry, signature)


def valid_session(token):
    expiry_text, _, signature = (token or "").partition(".")
    try:
        expiry = int(expiry_text)
    except ValueError:
        return False
    if expiry < time.time():
        return False
    expected = hmac.new(
        _session_key(), ("v1|%d" % expiry).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


def issue_ticket(service, where, session=""):
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _ticket_lock:
        for stale, (_, _, _, expiry) in list(_tickets.items()):
            if expiry < now:
                del _tickets[stale]
        _tickets[token] = (service, where, session, now + TICKET_TTL)
    return token


def redeem_ticket(token):
    """Consume a ticket, returning the (service, where, session) it was issued for."""
    with _ticket_lock:
        entry = _tickets.pop(token, None)
    if entry is None:
        return None, None, None
    if len(entry) == 3:
        service, where, expiry = entry
        session = ""
    else:
        service, where, session, expiry = entry
    if expiry < time.time():
        return None, None, None
    return service, where, session


# --------------------------------------------------------------------------- #
# HTTP layer
# --------------------------------------------------------------------------- #
PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --raise: #1c2430; --border: #30363d; --text: #e6edf3;
    --muted: #8b949e; --up: #3fb950; --down: #f85149; --warn: #d29922; --unknown: #6e7681;
    --accent: #58a6ff; --usage-bg: rgba(88, 166, 255, 0.08); --usage-border: rgba(88, 166, 255, 0.35);
  }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --panel: #fff; --raise: #eef2f6; --border: #d0d7de;
            --text: #1f2328; --muted: #636c76; --accent: #0969da;
            --usage-bg: rgba(9, 105, 218, 0.06); --usage-border: rgba(9, 105, 218, 0.28); }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5
    ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  a { color: inherit; }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 24px 18px 64px; }
  header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 18px; }
  h1 { font-size: 22px; margin: 0; letter-spacing: -0.01em; }
  .sub { color: var(--muted); font-size: 13px; }
  /* ---- plan-usage health bars ---- */
  .usage-bars { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 14px 0 0;
    background: var(--usage-bg); border: 1px solid var(--usage-border); border-radius: 10px;
    padding: 10px 14px; }
  .usage-bars:empty { display: none; }
  .usage-caption { color: var(--muted); font-size: 11px; text-transform: uppercase;
    letter-spacing: 0.04em; }
  .usage-card { display: flex; align-items: center; gap: 10px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px; font-size: 12px; }
  .usage-card.offline { color: var(--muted); }
  .usage-card .uname { font-weight: 600; color: var(--text); }
  .meter { display: flex; align-items: center; gap: 6px; }
  .meter .mlabel { color: var(--muted); }
  .meter .mval { font-variant-numeric: tabular-nums; min-width: 4.6em; }
  .meter .mval.muted { color: var(--muted); }
  .meter .mval .reset { color: var(--muted); font-weight: 400; }
  .bar-track { width: 70px; height: 6px; border-radius: 3px; background: var(--raise);
    overflow: hidden; }
  .bar-fill { display: block; height: 100%; border-radius: 3px; background: var(--up); }
  .bar-fill.warn { background: var(--warn); }
  .bar-fill.down { background: var(--down); }

  .totals { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 14px 0 6px; }
  .pill { display: inline-flex; align-items: center; gap: 7px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px; font-size: 12px; }
  .pill b { font-variant-numeric: tabular-nums; }
  .dot { width: 9px; height: 9px; border-radius: 50%; flex: none; background: var(--unknown); }
  .up .dot, .dot.up { background: var(--up); }
  .down .dot, .dot.down { background: var(--down); }
  .warn .dot, .dot.warn { background: var(--warn); }
  .unknown .dot, .dot.unknown { background: var(--unknown); }

  /* ---- group ---- */
  section.group { margin: 26px 0 0; }
  .ghead { display: flex; align-items: baseline; gap: 12px; margin-bottom: 10px; }
  .ghead h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--muted); margin: 0; font-weight: 600; }
  .gsum { display: flex; gap: 10px; font-size: 12px; color: var(--muted);
    font-variant-numeric: tabular-nums; }
  .gsum span { display: inline-flex; align-items: center; gap: 5px; }

  /* ---- always-visible operation row ---- */
  .quick { display: flex; flex-wrap: wrap; gap: 8px; }
  .quick:empty { display: none; }
  .chip { display: inline-flex; align-items: center; background: var(--panel);
    border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  .chip > a { display: inline-flex; align-items: center; gap: 7px; padding: 7px 12px;
    text-decoration: none; font-size: 14px; }
  .chip > a:hover { background: var(--raise); }
  .chip .alt { display: inline-flex; align-items: center; border-left: 1px solid var(--border);
    padding: 7px 9px; font-size: 12px; color: var(--muted); }
  .chip .alt:hover { color: var(--text); }
  .chip.term { border-color: var(--accent); }
  .chip.term > a { color: var(--accent); font-weight: 500; }
  .ico { width: 15px; height: 15px; flex: none; }
  .ico.claude { width: 14px; height: 14px; }
  /* Which box it runs on, riding along after the name. */
  .node { display: inline-flex; align-items: center; opacity: 0.75; }
  .node .ico { width: 12px; height: 12px; }
  .chip.term code { font: 12px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: var(--muted); }
  .chip.offline > a { color: var(--muted); }
  /* An endpoint-only chip: same shape as a link chip, but deliberately inert -
     there is no page behind it, so nothing here invites a click. */
  .chip > .plain { display: inline-flex; align-items: center; gap: 7px;
    padding: 7px 12px; font-size: 14px; color: var(--text); cursor: default; }
  .chip.offline > .plain { color: var(--muted); }
  .chip .alt.copy { background: none; border-top: 0; border-right: 0; border-bottom: 0;
    font: inherit; cursor: pointer; }
  .chip .alt.copied, .acts .copied { color: var(--ok); }
  .acts .copy { background: none; font: inherit; cursor: pointer; font-size: 12px;
    color: var(--muted); border: 1px solid var(--border); border-radius: 5px; padding: 1px 8px; }
  .acts .copy:hover { color: var(--text); border-color: var(--muted); }
  .meta code { font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: var(--muted); }

  /* ---- folded detail ---- */
  details.more { margin-top: 10px; }
  details.more > summary { cursor: pointer; color: var(--muted); font-size: 12px;
    list-style: none; display: inline-flex; align-items: center; gap: 6px;
    padding: 3px 9px; border: 1px solid var(--border); border-radius: 6px; }
  details.more > summary::-webkit-details-marker { display: none; }
  details.more > summary:hover { color: var(--text); border-color: var(--muted); }
  details.more > summary::before { content: "\\25B8"; font-size: 10px; }
  details.more[open] > summary::before { content: "\\25BE"; }
  .grid { display: grid; gap: 10px; margin-top: 10px;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }
  .card { display: flex; align-items: flex-start; gap: 12px; background: var(--panel);
    border: 1px solid var(--border); border-left-width: 3px; border-radius: 8px; padding: 12px 14px; }
  .card.up { border-left-color: var(--up); }
  .card.down { border-left-color: var(--down); }
  .card.warn { border-left-color: var(--warn); }
  .card.unknown { border-left-color: var(--unknown); }
  .card .dot { margin-top: 6px; }
  .body { min-width: 0; flex: 1; }
  .name { font-weight: 600; overflow-wrap: anywhere; display: flex; align-items: center; gap: 7px; }
  .name a { text-decoration: none; border-bottom: 1px solid var(--border); }
  .name a:hover { border-bottom-color: currentColor; }
  .detail { font-size: 13px; margin-top: 2px; overflow-wrap: anywhere; }
  .down .detail { color: var(--down); }
  .warn .detail { color: var(--warn); }
  .meta { color: var(--muted); font-size: 12px; margin-top: 3px; font-variant-numeric: tabular-nums; }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .acts a { font-size: 12px; color: var(--muted); text-decoration: none;
    border: 1px solid var(--border); border-radius: 5px; padding: 1px 8px; }
  .acts a:hover { color: var(--text); border-color: var(--muted); }
  footer { margin-top: 44px; color: var(--muted); font-size: 12px; }
  .stale { opacity: 0.45; transition: opacity 0.2s; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>__TITLE__</h1>
    <span class="sub" id="updated">loading…</span>
  </header>
  <div class="usage-bars" id="usageBars"></div>
  <div class="totals" id="totals"></div>
  <main id="groups"></main>
  <footer>Auto-refreshing every __REFRESH__s ·
    <a href="/api/status">JSON API</a> ·
    <a href="/claude-rc">Claude sessions</a> ·
    <a href="/tmux">tmux sessions</a> ·
    <a href="#" id="expand">expand all</a>__LOGOUT__</footer>
</div>
<script>
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const qs = encodeURIComponent;

// Which address family this browser reached us on decides which link we lead
// with: opened over a public hostname you want the tunnel URLs, opened over the
// LAN IP you want the LAN ones. The other is always one click away as "alt".
const PUBLIC_VIEW = !/^[\\d.]+$|^\\[|^localhost$|\\.local$/i.test(location.hostname);

function links(s) {
  const lan = s.link, pub = s.remote;
  const primary = (PUBLIC_VIEW && pub) || lan || pub || "";
  const alt = primary === pub ? lan : pub;
  return { primary, alt, altLabel: primary === pub ? "LAN" : "WAN" };
}

// Folded by default: this page is for operating the homelab, not staring at it.
const isOpen = (g) => localStorage.getItem("fold:" + g) === "open";

// Inline so the page keeps working with no outbound access (xterm.js on the
// terminal page is the one exception in this service).
const ICONS = {
  // A shell: what you get is a prompt, so draw a prompt.
  terminal: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="0.75" y="2.25" width="14.5" height="11.5" rx="2"
      fill="none" stroke="currentColor" stroke-width="1.3"/>
    <path d="M4 6.2 L6.4 8 L4 9.8 M8.4 10.4 H11.6" fill="none" stroke="currentColor"
      stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  // The Claude mark: a burst of tapered rays.
  claude: `<svg class="ico claude" viewBox="0 0 16 16" aria-hidden="true">${
    Array.from({ length: 11 }, (_, i) => {
      const a = (i * 360) / 11;
      return `<rect x="7.35" y="0.9" width="1.3" height="7.1" rx="0.65"
        fill="#D97757" transform="rotate(${a} 8 8)"/>`;
    }).join("")}</svg>`,
  // Antigravity: a body breaking upward out of its orbit. Sits next to the
  // Claude mark on the session chips, so it has to read differently at 15px -
  // hence a ring plus an arrow rather than another radial burst.
  antigravity: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <ellipse cx="8" cy="11" rx="5.6" ry="2.4" fill="none" stroke="#4285F4"
      stroke-width="1.3" opacity=".55"/>
    <path d="M8 12.4 V3.2 M5.1 6 L8 3 L10.9 6" fill="none" stroke="#4285F4"
      stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  // Two sheets: the copy affordance on an address you paste elsewhere.
  copy: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="5.4" y="5.4" width="8.1" height="8.1" rx="1.6" fill="none"
      stroke="currentColor" stroke-width="1.3"/>
    <path d="M10.6 5.4V4a1.6 1.6 0 0 0-1.6-1.6H4a1.6 1.6 0 0 0-1.6 1.6v5a1.6 1.6 0 0 0 1.6 1.6h1.4"
      fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  // The Raspberry Pi berry: also used as the "runs on the Pi" badge.
  raspberry: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><g fill="#C51A4A">
    <path d="M7.6 5.1C6.7 3.6 5.1 2.9 3.6 3.2c0 1.6 1.1 3 2.6 3.4z"/>
    <path d="M8.4 5.1C9.3 3.6 10.9 2.9 12.4 3.2c0 1.6-1.1 3-2.6 3.4z"/>
    <circle cx="8" cy="7.1" r="1.7"/><circle cx="5.9" cy="8.6" r="1.7"/>
    <circle cx="10.1" cy="8.6" r="1.7"/><circle cx="6.9" cy="11" r="1.7"/>
    <circle cx="9.1" cy="11" r="1.7"/></g></svg>`,
  // Home Assistant: the blue house.
  "home-assistant": `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M8 1.3 15 7.9v6.1c0 .4-.3.7-.7.7H1.7c-.4 0-.7-.3-.7-.7V7.9z" fill="#18BCF2"/>
    <path d="M8 6.4v6.6M5.3 9.1v3.9M10.7 9.1v3.9" stroke="#fff" stroke-width="1.15"
      stroke-linecap="round"/></svg>`,
  // Jellyfin: the two-tone gradient jelly.
  jellyfin: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <defs><linearGradient id="jf" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#AA5CC3"/><stop offset="1" stop-color="#00A4DC"/>
    </linearGradient></defs>
    <path d="M8 1.4c1.5 0 5.9 7.3 5.2 8.7-.8 1.4-9.6 1.4-10.4 0C2.1 8.7 6.5 1.4 8 1.4z"
      fill="url(#jf)" opacity=".45"/>
    <path d="M8 6.3c.8 0 3.4 4.3 3 5-.4.8-5.6.8-6 0-.4-.7 2.2-5 3-5z" fill="url(#jf)"/></svg>`,
  // Docker: containers stacked on the hull of the whale.
  docker: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><g fill="#2496ED">
    <rect x="3" y="6.5" width="2.2" height="2.2" rx=".3"/>
    <rect x="5.6" y="6.5" width="2.2" height="2.2" rx=".3"/>
    <rect x="8.2" y="6.5" width="2.2" height="2.2" rx=".3"/>
    <rect x="5.6" y="3.9" width="2.2" height="2.2" rx=".3"/>
    <path d="M1 9.4h13.1c0 2.5-2 4.2-5 4.2-3.5 0-6.8-1.2-8.1-4.2z"/></g></svg>`,
  // The *arr suite: same silhouette family, told apart by what they hunt.
  sonarr: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="1.2" y="3.6" width="13.6" height="9" rx="1.6" fill="none" stroke="#35C5F4"
      stroke-width="1.4"/><path d="M5.4 14.4h5.2M6.6 1.6 8 3.4l1.4-1.8" fill="none"
      stroke="#35C5F4" stroke-width="1.4" stroke-linecap="round"/></svg>`,
  radarr: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="1.2" y="5.4" width="13.6" height="8.4" rx="1.4" fill="none" stroke="#FFC230"
      stroke-width="1.4"/><path d="M1.6 3.1 13.4 1.6l.3 2.2L1.9 5.3z" fill="#FFC230"/>
    <path d="M5.4 2.6 6.5 4.6M9 2.2l1.1 2" stroke="#0d1117" stroke-width="1"/></svg>`,
  readarr: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M1.6 2.4h4.2c1.2 0 2.2.7 2.2 1.6v9.6c0-.9-1-1.6-2.2-1.6H1.6z" fill="#C4392E"/>
    <path d="M14.4 2.4h-4.2c-1.2 0-2.2.7-2.2 1.6v9.6c0-.9 1-1.6 2.2-1.6h4.2z" fill="#E8654F"/>
    </svg>`,
  prowlarr: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="6.9" cy="6.9" r="4.7" fill="none" stroke="#E66000" stroke-width="1.5"/>
    <path d="M10.4 10.4 14.2 14.2" stroke="#E66000" stroke-width="1.8" stroke-linecap="round"/>
    </svg>`,
  // Transmission: a torrent client is a download, so draw the download.
  transmission: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="8" cy="8" r="6.7" fill="none" stroke="#D33A2C" stroke-width="1.4"/>
    <path d="M8 4.2v6M5.4 7.6 8 10.3l2.6-2.7" fill="none" stroke="#D33A2C"
      stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  // Karakeep: things you kept, so a bookmark.
  karakeep: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M3.6 1.9h8.8c.5 0 .9.4.9.9v11.3L8 11.2l-5.3 2.9V2.8c0-.5.4-.9.9-.9z"
      fill="#16A394"/></svg>`,
  // Meilisearch: the search box behind Karakeep.
  meilisearch: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <defs><linearGradient id="ms" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#FF5CAA"/><stop offset="1" stop-color="#7700FF"/>
    </linearGradient></defs>
    <circle cx="6.9" cy="6.9" r="4.7" fill="none" stroke="url(#ms)" stroke-width="1.5"/>
    <path d="M10.4 10.4 14.2 14.2" stroke="url(#ms)" stroke-width="1.8" stroke-linecap="round"/>
    </svg>`,
  // Headless Chrome: the four-colour wheel.
  chrome: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="8" cy="8" r="6.8" fill="#4285F4"/>
    <path d="M8 1.2a6.8 6.8 0 0 1 5.9 3.4H8a3.4 3.4 0 0 0-3 1.8L2.2 4.1A6.8 6.8 0 0 1 8 1.2z"
      fill="#EA4335"/>
    <path d="M2.2 4.1 5 6.4a3.4 3.4 0 0 0 .1 3.3l-2.9 5A6.8 6.8 0 0 1 2.2 4.1z" fill="#FBBC05"/>
    <path d="M13.9 4.6A6.8 6.8 0 0 1 8 14.8h-.4l2.9-5A3.4 3.4 0 0 0 8 4.6z" fill="#34A853"/>
    <circle cx="8" cy="8" r="2.9" fill="#fff"/><circle cx="8" cy="8" r="2.2" fill="#4285F4"/>
    </svg>`,
  // Paperclip: the mark is the name.
  paperclip: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M11.6 7.4 6.9 12a2.7 2.7 0 0 1-3.8-3.8l5.6-5.6a1.8 1.8 0 0 1 2.6 2.6L5.7 10.7
      a.9.9 0 0 1-1.3-1.3l4.6-4.6" fill="none" stroke="currentColor" stroke-width="1.3"
      stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  // Hermes: the messenger, so the thing a message flies as.
  hermes: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M14.6 1.6 1.4 6.9l4.4 1.9z" fill="#D4A017"/>
    <path d="M14.6 1.6 5.8 8.8l.6 5.1 2.4-3.4z" fill="#A87C11"/></svg>`,
  // OpenHands: an agent that drives a computer for you.
  openhands: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M8 1.4v2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
    <rect x="2.1" y="3.6" width="11.8" height="9.4" rx="2.6" fill="none" stroke="currentColor"
      stroke-width="1.3"/>
    <circle cx="5.8" cy="8.3" r="1.15" fill="currentColor"/>
    <circle cx="10.2" cy="8.3" r="1.15" fill="currentColor"/></svg>`,
  // A protocol bridge (ACP, MCP): two links of a chain.
  bridge: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M6.6 9.4a2.8 2.8 0 0 1 0-3.9l2-2a2.8 2.8 0 0 1 3.9 3.9l-.9.9" fill="none"
      stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/>
    <path d="M9.4 6.6a2.8 2.8 0 0 1 0 3.9l-2 2a2.8 2.8 0 0 1-3.9-3.9l.9-.9" fill="none"
      stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/></svg>`,
  // A job hunt: the briefcase.
  briefcase: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="1.2" y="4.9" width="13.6" height="8.6" rx="1.4" fill="none" stroke="currentColor"
      stroke-width="1.3"/>
    <path d="M5.7 4.6V3.4c0-.6.5-1 1.1-1h2.4c.6 0 1.1.4 1.1 1v1.2M1.4 8.6h13.2" fill="none"
      stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  // The cockpit itself: a gauge.
  cockpit: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M1.8 12.4a6.9 6.9 0 1 1 12.4 0" fill="none" stroke="currentColor"
      stroke-width="1.4" stroke-linecap="round"/>
    <path d="M8 11.4 11.2 6.2" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round"/>
    <circle cx="8" cy="11.9" r="1.2" fill="currentColor"/></svg>`,
  // SSH: the key.
  ssh: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="5.1" cy="10.9" r="3.1" fill="none" stroke="currentColor" stroke-width="1.35"/>
    <path d="M7.3 8.7 13.6 2.4M11.4 4.6l1.6 1.6M9.8 6.2l1.6 1.6" fill="none"
      stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/></svg>`,
  // Upgrades: what lands on the box.
  upgrade: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M8 10.6V1.9M4.8 5.1 8 1.9l3.2 3.2" fill="none" stroke="currentColor"
      stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M1.9 10.4v2.6c0 .6.5 1.1 1.1 1.1h10c.6 0 1.1-.5 1.1-1.1v-2.6" fill="none"
      stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/></svg>`,
  // A log file on disk.
  logfile: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M3.1 1.6h6L13 5.4v9c0 .6-.5 1-1.1 1H3.1c-.6 0-1.1-.4-1.1-1V2.6c0-.6.5-1 1.1-1z"
      fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
    <path d="M8.9 1.8v3.6h3.7M4.6 8.6h6M4.6 11.1h6M4.6 13h3.6" fill="none"
      stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>`,
};

// Entries are named after what they are, so the icon usually needs no config:
// the name (or an alias of it) is the lookup key, and `icon = ...` overrides.
Object.assign(ICONS, {
  "jellyfin-web": ICONS.jellyfin,
  "karakeep-meilisearch": ICONS.meilisearch,
  "karakeep-chrome": ICONS.chrome,
  "raspberry-pi": ICONS.raspberry,
  "paperclip-ai": ICONS.paperclip,
  "paperclip-mcp": ICONS.paperclip,
  "hermes-ai": ICONS.hermes,
  "openhands-ai": ICONS.openhands,
  "arr-mcp-backend": ICONS.bridge,
  "ai-job-search": ICONS.briefcase,
  "homelab-cockpit": ICONS.cockpit,
  "ai-services-upgrade": ICONS.upgrade,
  "unattended-upgrades": ICONS.upgrade,
});

const icon = (name) => ICONS[name] || "";
const iconOf = (s) => icon(s.icon || String(s.name).trim().toLowerCase().replace(/[ _]+/g, "-"));
// Where it runs, when that is not this box. The service's own icon already says
// "Raspberry Pi" on the Pi entry itself, so it is not badged twice.
const nodeBadge = (s) => s.node === "pi" && s.icon !== "raspberry"
  ? `<span class="node" title="runs on the Raspberry Pi">${icon("raspberry")}</span>` : "";

// A second front-end onto the same workspace - the Antigravity web console
// beside the Claude one. Both sessions drive the same box, so which one you
// want is a preference, not a different service: it belongs on the same chip.
function altSession(s) {
  const list = (s.alt_links && s.alt_links.length)
    ? s.alt_links
    : (s.alt_link ? [{ href: s.alt_link, icon: s.alt_icon, label: s.alt_label }] : []);
  if (!list.length) return "";
  return list.map(a => {
    const label = a.label || a.icon || "alt";
    return `<a class="alt" href="${esc(a.href)}" target="_blank" rel="noopener"
      title="${esc(label)}: ${esc(a.href)}">${icon(a.icon) || esc(label)}</a>`;
  }).join("");
}

// An address you paste into an agent's config, not a page you visit. Copying is
// the only thing you ever do with it, so that is the only button it gets.
const copyBtn = (value, cls) => `<button class="${cls}" data-copy="${esc(value)}"
  title="copy ${esc(value)}">${cls === "alt copy" ? icon("copy") : "copy"}</button>`;

function chip(s) {
  const { primary, alt, altLabel } = links(s);
  // No page behind it, but still worth a chip when it names an endpoint: you
  // come here to read its state and take the address away with you.
  if (!primary && !s.endpoint) return "";
  const cls = "chip" + (s.state === "up" ? "" : " offline");
  const head = `<span class="dot ${esc(s.state)}"></span>${iconOf(s)}${esc(s.name)}${nodeBadge(s)}`;
  return `<span class="${cls}">
    ${primary
      ? `<a href="${esc(primary)}" target="_blank" rel="noopener">${head}</a>`
      : `<span class="plain" title="${esc(s.endpoint)}">${head}</span>`}
    ${s.endpoint ? copyBtn(s.endpoint, "alt copy") : ""}
    ${altSession(s)}
    ${s.has_chip_shell ? `<a class="alt" href="/terminal?service=${qs(s.name)}"
      title="shell: ${esc(s.command)}">${icon("terminal")}</a>` : ""}
    ${alt ? `<a class="alt" href="${esc(alt)}" target="_blank" rel="noopener"
      title="${altLabel}: ${esc(alt)}">${altLabel}</a>` : ""}</span>`;
}

function launcher(l) {
  if (!l.enabled) return "";
  return `<span class="chip term">
    <a href="/terminal?service=${qs(l.name)}">${icon(l.icon)}${esc(l.name)}
      ${l.command ? `<code>${esc(l.command)}</code>` : ""}</a></span>`;
}

function card(s) {
  const { primary, alt, altLabel } = links(s);
  const named = (href, label) =>
    `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(label)}</a>`;
  const altList = (s.alt_links && s.alt_links.length)
    ? s.alt_links
    : (s.alt_link ? [{ href: s.alt_link, icon: s.alt_icon, label: s.alt_label }] : []);
  const consoles = altList.map(a => named(a.href, a.label || a.icon || "alt")).join("");
  const acts = [
    s.has_logs ? `<a href="/logs?service=${qs(s.name)}">logs</a>` : "",
    s.has_terminal ? `<a href="/terminal?service=${qs(s.name)}">shell</a>` : "",
    s.has_host_shell ? `<a href="/terminal?service=${qs(s.name)}&where=host">compose</a>` : "",
    alt ? `<a href="${esc(alt)}" target="_blank" rel="noopener">${altLabel}</a>` : "",
    consoles,
    s.endpoint ? copyBtn(s.endpoint, "copy") : "",
  ].join("");
  return `<div class="card ${esc(s.state)}">
    <span class="dot"></span>
    <div class="body">
      <div class="name">${iconOf(s)}${primary
        ? `<a href="${esc(primary)}" target="_blank" rel="noopener">${esc(s.name)}</a>`
        : esc(s.name)}${nodeBadge(s)}</div>
      <div class="detail">${esc(s.detail)}</div>
      <div class="meta">${[s.meta, s.note].filter(Boolean).map(esc).join(" · ")}</div>
      ${s.endpoint ? `<div class="meta"><code>${esc(s.endpoint)}</code></div>` : ""}
      <div class="acts">${acts}</div>
    </div>
  </div>`;
}

// Members sharing a `chat_group` are different ways into the SAME session -
// a web Remote Control console, a local terminal - not different services, so
// they render as one inert chip (the name itself opens nothing) with one
// small button per way in: every member's RC link first, then every member's
// terminal button, in config order.
function chatChip(members) {
  const SEVERITY = { down: 0, warn: 1, unknown: 2, up: 3 };
  const worst = members.reduce((a, b) =>
    (SEVERITY[b.state] ?? 3) < (SEVERITY[a.state] ?? 3) ? b : a, members[0]).state;
  const rc = members.filter(m => m.remote).map(m =>
    `<a class="alt" href="${esc(m.remote)}" target="_blank" rel="noopener"
      title="${esc(m.icon)} rc: ${esc(m.remote)}">${icon(m.icon)}</a>`).join("");
  const term = members.filter(m => m.has_chip_shell).map(m =>
    `<a class="alt" href="/terminal?service=${qs(m.name)}"
      title="${esc(m.icon)} shell: ${esc(m.command)}">${icon("terminal")}</a>`).join("");
  const cls = "chip" + (worst === "up" ? "" : " offline");
  return `<span class="${cls}">
    <span class="plain" title="pick a way in with the buttons on the right">
      <span class="dot ${esc(worst)}"></span>chat</span>
    ${rc}${term}</span>`;
}

// Pulls chat_group members out of a list, in first-appearance order, so the
// caller can render each group once via chatChip() instead of once per member.
function splitChatGroups(items) {
  const chats = new Map();
  const singles = [];
  for (const s of items) {
    if (s.chat_group) {
      if (!chats.has(s.chat_group)) chats.set(s.chat_group, []);
      chats.get(s.chat_group).push(s);
    } else {
      singles.push(s);
    }
  }
  return { singles, chats: [...chats.values()] };
}

function group(g) {
  // The quick row is the operating surface: it holds the launchers plus
  // whatever is up and has somewhere to click through to. Ordered by what the
  // chip opens - Claude sessions, then local shells, then plain links - so the
  // two kinds of "somewhere to work" lead. Sorting is stable, so config order
  // still decides within each kind.
  const RANK = { claude: 0, terminal: 1 };
  const rank = (item) => RANK[item.icon] ?? 2;
  const eligible = g.services.filter(s => !s.headline)
    .filter(s => s.pinned || (s.state === "up" && (s.link || s.remote || s.endpoint)));
  const { singles, chats } = splitChatGroups(eligible);
  const quick = [
    ...g.launchers.filter(l => l.enabled).map(l => ({ icon: l.icon, html: launcher(l) })),
    ...singles.map(s => ({ icon: s.icon, html: chip(s) })),
    ...chats.map(members => ({ icon: "claude", html: chatChip(members) })),
  ].sort((a, b) => rank(a) - rank(b)).map(item => item.html).join("");
  const counts = ["down", "warn", "unknown", "up"]
    .map(state => [state, g.services.filter(s => s.state === state).length])
    .filter(([, n]) => n > 0)
    .map(([state, n]) => `<span><span class="dot ${state}"></span>${n} ${state}</span>`)
    .join("");
  const details = g.services.length ? `
    <details class="more" data-group="${esc(g.name)}"${isOpen(g.name) ? " open" : ""}>
      <summary>${g.services.length} service${g.services.length > 1 ? "s" : ""} · logs &amp; shells</summary>
      <div class="grid">${g.services.map(card).join("")}</div>
    </details>` : "";
  return `<section class="group">
    <div class="ghead"><h2>${esc(g.name)}</h2><span class="gsum">${counts}</span></div>
    <div class="quick">${quick}</div>
    ${details}
  </section>`;
}

// Plan-usage health bars: how close the Claude and Antigravity accounts
// running this homelab are to their 5-hour and weekly limits. Refreshed on
// its own slow timer server-side (usage.py) - see /api/status's "usage" key.
function usageLevel(pct) {
  if (pct >= 85) return "down";
  if (pct >= 60) return "warn";
  return "up";
}

// A 5-hour window is short enough that "when" only matters as a countdown; a
// weekly one is long enough that a countdown stops being legible ("in 4290
// minutes") and the day it lands on is what you actually want to know. Both
// CLIs' reset strings parse as a Date - agy prints ISO, and claude's already
// human "Aug 25, 6:10am (Europe/Paris)" still parses close enough for this.
function formatReset(reset, period) {
  if (!reset) return "";
  const d = new Date(reset);
  if (isNaN(d)) return reset;  // could not parse - show the CLI's own text verbatim
  if (period === "five_hour") {
    const ms = d - Date.now();
    if (ms <= 0) return "any moment";
    const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000);
    return h > 0 ? `in ${h}h ${m}m` : `in ${m}m`;
  }
  return d.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" });
}

function usageMeter(label, bar, period) {
  if (!bar) {
    return `<span class="meter"><span class="mlabel">${label}</span><span class="mval muted">n/a</span></span>`;
  }
  const pct = Math.min(Math.max(bar.pct, 0), 100);
  const reset = formatReset(bar.reset, period);
  const title = `${label}: ${bar.pct}% of the limit used` + (reset ? ` · resets ${reset}` : "");
  return `<span class="meter" title="${esc(title)}">
    <span class="mlabel">${label}</span>
    <span class="bar-track"><span class="bar-fill ${usageLevel(bar.pct)}" style="width:${pct}%"></span></span>
    <span class="mval">${bar.pct}% used${reset ? ` <span class="reset">· resets ${esc(reset)}</span>` : ""}</span></span>`;
}

function usageCard(name, iconKey, entry) {
  if (!entry) return "";
  if (entry.state !== "ok") {
    return `<span class="usage-card offline" title="${esc(entry.detail || "unavailable")}">
      ${icon(iconKey)}<span class="uname">${esc(name)}</span><span class="mval muted">n/a</span></span>`;
  }
  return `<span class="usage-card">
    ${icon(iconKey)}<span class="uname">${esc(name)}</span>
    ${usageMeter("5h", entry.bars.five_hour, "five_hour")}
    ${usageMeter("wk", entry.bars.weekly, "weekly")}</span>`;
}

function renderUsage(usage) {
  // Both cards render the same metric the same way - "% of the limit used",
  // rising and turning red as a period runs out - so this caption only needs
  // to say it once, not have every meter repeat it.
  document.getElementById("usageBars").innerHTML = usage
    ? `<span class="usage-caption">plan limits · % used</span>`
      + usageCard("Claude", "claude", usage.claude) + usageCard("Antigravity", "antigravity", usage.agy)
    : "";
}

let lastSignature = "";

function render(data) {
  renderUsage(data.usage);
  const t = data.totals;
  // The session that operates the whole homelab belongs with the totals, not
  // filed under a group: it is how you act on whatever they are reporting.
  // "claude rc sessions" is grouped right after the merged chat chip - it
  // manages Claude Remote Control instances, which is one of the chat chip's
  // own buttons - and always says so in full rather than a bare "sessions"
  // that could be about anything on the page.
  const { singles: headSingles, chats: headChats } = splitChatGroups(data.headline || []);
  const tmuxCount = data.tmux ? data.tmux.count : 0;
  const tmuxBadge = tmuxCount > 0 ? ` (${tmuxCount})` : "";
  const lead = headChats.map(chatChip).join("")
    + `<span class="chip term"><a href="/claude-rc" title="start, stop and create
       Claude Remote Control instances">${icon("claude")}claude rc sessions</a></span>`
    + `<span class="chip term"><a href="/tmux" title="manage and open active tmux sessions">${icon("terminal")}tmux sessions${tmuxBadge}</a></span>`
    + headSingles.map(chip).join("");
  document.getElementById("totals").innerHTML = lead + [
    ["up", "up", t.up], ["warn", "degraded", t.warn],
    ["down", "down", t.down], ["unknown", "unknown", t.unknown],
  ].filter(([, , n]) => n > 0).map(([cls, label, n]) =>
    `<span class="pill ${cls}"><span class="dot"></span><b>${n}</b> ${label}</span>`
  ).join("");

  // Only rebuild when something actually changed, so an open fold (or a click
  // you were about to make) is not yanked away on every poll.
  const signature = JSON.stringify(data.groups);
  if (signature !== lastSignature) {
    lastSignature = signature;
    document.getElementById("groups").innerHTML = data.groups.map(group).join("");
    document.querySelectorAll("details.more").forEach(el =>
      el.addEventListener("toggle", () =>
        localStorage.setItem("fold:" + el.dataset.group, el.open ? "open" : "shut")));
  }

  document.getElementById("updated").textContent = "updated " + data.generated_at;
  document.body.classList.remove("stale");
}

// Delegated: every poll that changes something rebuilds the cards wholesale,
// so a listener bound to a button would not survive the next refresh.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  event.preventDefault();
  const value = button.dataset.copy;
  try {
    // Only available over HTTPS or on localhost; the LAN view is plain HTTP,
    // so fall back to the old execCommand path rather than silently doing
    // nothing on exactly the address you reach this page from most often.
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
    } else {
      const scratch = document.createElement("textarea");
      scratch.value = value;
      scratch.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(scratch);
      scratch.select();
      document.execCommand("copy");
      scratch.remove();
    }
    button.classList.add("copied");
    setTimeout(() => button.classList.remove("copied"), 1200);
  } catch (err) {
    button.title = "copy failed - " + value;
  }
});

document.getElementById("expand").addEventListener("click", (event) => {
  event.preventDefault();
  const opening = [...document.querySelectorAll("details.more")].some(el => !el.open);
  document.querySelectorAll("details.more").forEach(el => { el.open = opening; });
  event.target.textContent = opening ? "collapse all" : "expand all";
});

async function poll() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    render(await response.json());
  } catch (err) {
    document.body.classList.add("stale");
    document.getElementById("updated").textContent = "unreachable — retrying…";
  }
}

poll();
setInterval(poll, __REFRESH__ * 1000);
</script>
</body>
</html>
"""


LOG_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ logs · __TITLE__</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --border: #30363d; --text: #e6edf3; --muted: #8b949e;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --panel: #fff; --border: #d0d7de; --text: #1f2328; --muted: #636c76; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5
    ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  .wrap { max-width: 1400px; margin: 0 auto; padding: 24px 20px 48px; }
  header { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; margin-bottom: 6px; }
  h1 { font-size: 20px; margin: 0; }
  a { color: inherit; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .src { color: var(--muted); font-size: 12px; font-family: ui-monospace, SFMono-Regular,
    Menlo, Consolas, monospace; margin-bottom: 14px; overflow-wrap: anywhere; }
  .bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
  .bar a, .bar button { background: var(--panel); border: 1px solid var(--border);
    color: var(--text); border-radius: 6px; padding: 5px 11px; font-size: 13px;
    text-decoration: none; cursor: pointer; }
  .bar a.on { border-color: var(--muted); font-weight: 600; }
  .bar label { color: var(--muted); font-size: 13px; margin-left: 4px; }
  pre { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 14px 16px; margin: 0; max-height: 74vh; overflow: auto; font-size: 12.5px;
    line-height: 1.55; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <a class="back" href="/">&larr; all services</a>
    <h1>__NAME__</h1>
  </header>
  <div class="src">__SOURCE__</div>
  <div class="bar">
    <label>lines</label>
    __LINE_LINKS__
    <button id="reload" type="button">reload</button>
    <label><input type="checkbox" id="follow"> auto-refresh</label>
    <label><input type="checkbox" id="tailtoggle" checked> stick to bottom</label>
  </div>
  <pre id="log">__LOG__</pre>
</div>
<script>
const box = document.getElementById("log");
const stick = document.getElementById("tailtoggle");
function toBottom() { if (stick.checked) box.scrollTop = box.scrollHeight; }
toBottom();

async function reload() {
  const response = await fetch(location.pathname + location.search + "&raw=1",
                               { cache: "no-store" });
  box.textContent = await response.text();
  toBottom();
}
document.getElementById("reload").addEventListener("click", reload);

let timer = null;
document.getElementById("follow").addEventListener("change", (event) => {
  clearInterval(timer);
  if (event.target.checked) timer = setInterval(reload, 5000);
});
</script>
</body>
</html>
"""


TERMINAL_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ shell · __TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.min.css">
<style>
  :root { --bg: #0d1117; --panel: #161b22; --border: #30363d; --text: #e6edf3; --muted: #8b949e; }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5
    ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    display: flex; flex-direction: column; }
  header { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px;
    padding: 14px 20px 10px; }
  h1 { font-size: 18px; margin: 0; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .cmd { color: var(--muted); font-size: 12px; font-family: ui-monospace, SFMono-Regular,
    Menlo, Consolas, monospace; overflow-wrap: anywhere; }
  .state { margin-left: auto; font-size: 12px; color: var(--muted); }
  .state.live { color: #3fb950; }
  .state.gone { color: #f85149; }
  #term { flex: 1; min-height: 0; margin: 0 14px 14px; padding: 10px 12px;
    background: #000; border: 1px solid var(--border); border-radius: 8px; }
  button { background: var(--panel); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 4px 11px; font-size: 13px; cursor: pointer; }
  .warn { padding: 10px 20px; color: var(--muted); font-size: 13px; }
</style>
</head>
<body>
<header>
  <a class="back" href="/">&larr; all services</a>
  <h1>__NAME__</h1>
  <span class="cmd">__COMMAND__</span>
  <span class="state" id="state">connecting…</span>
  <button id="again" type="button" style="display:none">reconnect</button>
</header>
<div id="term"></div>
<script src="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.min.js"></script>
<script>
const service = "__SERVICE__";
const session = "__SESSION__";
const where = "__WHERE__";
const stateEl = document.getElementById("state");
const againEl = document.getElementById("again");

if (typeof Terminal === "undefined") {
  document.getElementById("term").innerHTML =
    '<div class="warn">Could not load xterm.js from the CDN, so the terminal ' +
    'cannot render. This page needs outbound access to cdn.jsdelivr.net.</div>';
  stateEl.textContent = "unavailable";
} else {
  const term = new Terminal({
    fontSize: 13, cursorBlink: true, scrollback: 10000,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
    theme: { background: "#000000", foreground: "#e6edf3" },
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(document.getElementById("term"));
  fit.fit();

  let socket = null;

  function setState(text, cls) {
    stateEl.textContent = text;
    stateEl.className = "state" + (cls ? " " + cls : "");
  }

  function sendResize() {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ resize: [term.cols, term.rows] }));
    }
  }

  addEventListener("resize", () => { fit.fit(); sendResize(); });

  async function connect() {
    againEl.style.display = "none";
    setState("connecting…");
    let ticket;
    try {
      const q = new URLSearchParams();
      if (service) q.set("service", service);
      if (session) q.set("session", session);
      if (where) q.set("where", where);
      const response = await fetch(
        "/api/terminal-ticket?" + q.toString(),
        { cache: "no-store" });
      if (!response.ok) throw new Error(await response.text());
      ticket = (await response.json()).ticket;
    } catch (err) {
      setState("no ticket: " + err.message, "gone");
      againEl.style.display = "";
      return;
    }

    const scheme = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(scheme + "://" + location.host +
                           "/ws/terminal?ticket=" + encodeURIComponent(ticket));
    socket.binaryType = "arraybuffer";

    socket.onopen = () => { setState("connected", "live"); sendResize(); term.focus(); };
    socket.onmessage = (event) => term.write(new Uint8Array(event.data));
    socket.onclose = () => {
      setState("disconnected", "gone");
      againEl.style.display = "";
    };
    socket.onerror = () => setState("connection error", "gone");
  }

  term.onData((data) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(new TextEncoder().encode(data));
    }
  });

  // Closing the tab leaves the persistent tmux session running in the background.
  addEventListener("beforeunload", (event) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  againEl.addEventListener("click", connect);
  connect();
}
</script>
</body>
</html>
"""


TMUX_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>tmux sessions · __TITLE__</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --raise: #1c2430; --border: #30363d; --text: #e6edf3;
    --muted: #8b949e; --up: #3fb950; --down: #f85149; --warn: #d29922; --unknown: #6e7681;
    --accent: #58a6ff;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --panel: #fff; --raise: #eef2f6; --border: #d0d7de;
            --text: #1f2328; --muted: #636c76; --accent: #0969da; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5
    ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  a { color: inherit; }
  .wrap { max-width: 960px; margin: 0 auto; padding: 24px 18px 64px; }
  header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 16px; }
  h1 { font-size: 22px; margin: 0; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--muted); margin: 30px 0 10px; font-weight: 600; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .lede { color: var(--muted); font-size: 13px; margin: 10px 0 0; max-width: 70ch; }
  .dot { width: 9px; height: 9px; border-radius: 50%; flex: none; background: var(--unknown); }
  .dot.up { background: var(--up); } .dot.down { background: var(--down); }
  .dot.warn { background: var(--warn); }
  .card { background: var(--panel); border: 1px solid var(--border); border-left-width: 3px;
    border-radius: 8px; padding: 13px 15px; margin-top: 10px; }
  .card.up { border-left-color: var(--up); } .card.down { border-left-color: var(--down); }
  .card.warn { border-left-color: var(--warn); }
  .top { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
  .who { font-weight: 600; font-size: 15px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  .badge { font-size: 11px; padding: 2px 7px; border-radius: 999px; background: var(--raise);
    border: 1px solid var(--border); color: var(--muted); }
  .badge.live { color: var(--up); border-color: rgba(63, 185, 80, 0.4); }
  .facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 2px 16px; margin-top: 8px; font-size: 12px; color: var(--muted); }
  .facts b { color: var(--text); font-weight: 500; }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  button, .btn { background: var(--panel); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 4px 11px; font-size: 12px; cursor: pointer;
    text-decoration: none; display: inline-flex; align-items: center; gap: 5px; }
  button:hover, .btn:hover { border-color: var(--muted); background: var(--raise); }
  button:disabled { opacity: 0.45; cursor: default; }
  button.danger:hover { border-color: var(--down); color: var(--down); }
  .empty { color: var(--muted); font-size: 13px; padding: 16px; background: var(--panel);
    border: 1px dashed var(--border); border-radius: 8px; margin-top: 10px; }
  .quick-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
  .quick-chip { display: inline-flex; align-items: center; gap: 6px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 6px; padding: 6px 11px; font-size: 13px;
    text-decoration: none; }
  .quick-chip:hover { background: var(--raise); border-color: var(--muted); }
  form { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 15px; margin-top: 10px; }
  .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
  label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
  input { width: 100%; background: var(--bg); color: var(--text); font: inherit;
    font-size: 14px; border: 1px solid var(--border); border-radius: 6px; padding: 6px 9px; }
  input:focus { outline: none; border-color: var(--accent); }
  pre { background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
    padding: 10px 12px; font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    white-space: pre-wrap; overflow-wrap: anywhere; margin: 10px 0 0; max-height: 320px;
    overflow: auto; }
  pre:empty { display: none; }
  footer { margin-top: 40px; color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>tmux sessions</h1>
    <a class="back" href="/">&larr; __TITLE__</a>
  </header>
  <p class="lede">All cockpit terminal sessions run inside named <code>tmux</code> sessions
  (prefixed with <code>__PREFIX__</code>). Work remains running in the background across
  page closes, reloads, or disconnects.</p>

  <h2>Active Sessions</h2>
  <div id="list">loading…</div>
  <pre id="out"></pre>

  <h2>Launch Service in tmux</h2>
  <div class="quick-grid" id="quickLaunch"></div>

  <h2>New tmux session</h2>
  <form id="newSession" autocomplete="off">
    <div class="row">
      <div>
        <label for="name">Session name</label>
        <input id="name" name="name" placeholder="workspace" spellcheck="false" required>
      </div>
      <div>
        <label for="cwd">Working directory (optional)</label>
        <input id="cwd" name="cwd" placeholder="__REPO_ROOT__" spellcheck="false">
      </div>
      <div>
        <label for="command">Initial command (optional)</label>
        <input id="command" name="command" placeholder="htop" spellcheck="false">
      </div>
    </div>
    <div class="acts" style="margin-top:12px">
      <button type="submit" id="createBtn">Create &amp; open</button>
    </div>
  </form>

  <footer>Manage sessions with the native <code>tmux</code> CLI on the host anytime:
    <code>tmux ls</code> · <code>tmux attach -t &lt;name&gt;</code></footer>
</div>
<script>
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const qs = encodeURIComponent;
const out = document.getElementById("out");

const post = (path, body) => fetch(path, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
}).then(r => r.json());

function sessionCard(s) {
  const attachedCls = s.attached ? "up" : "warn";
  const attachedBadge = s.attached
    ? `<span class="badge live">attached (${s.attached_count})</span>`
    : `<span class="badge">detached (background)</span>`;
  const typeBadge = s.is_cockpit
    ? `<span class="badge">cockpit</span>`
    : `<span class="badge">tmux</span>`;

  return `<div class="card ${attachedCls}">
    <div class="top">
      <span class="dot ${attachedCls}"></span>
      <span class="who">${esc(s.name)}</span>
      ${attachedBadge}
      ${typeBadge}
    </div>
    <div class="facts">
      <span>created <b>${esc(s.created_human)}</b></span>
      <span>windows <b>${esc(s.windows)}</b></span>
      <span>size <b>${esc(s.size)}</b></span>
      ${s.service_name ? `<span>service <b>${esc(s.service_name)}</b></span>` : ""}
    </div>
    <div class="acts">
      <a class="btn" href="/terminal?session=${qs(s.name)}">open terminal</a>
      <button class="danger" data-kill="${esc(s.name)}">kill session</button>
    </div>
  </div>`;
}

async function load() {
  try {
    const res = await fetch("/api/tmux", { cache: "no-store" });
    const data = await res.json();
    const listEl = document.getElementById("list");
    if (!data.sessions || data.sessions.length === 0) {
      listEl.innerHTML = '<div class="empty">No active tmux sessions right now. Launch one below or from the dashboard.</div>';
    } else {
      listEl.innerHTML = data.sessions.map(sessionCard).join("");
    }
  } catch (err) {
    document.getElementById("list").innerHTML = '<div class="empty">Failed to load tmux sessions.</div>';
  }
}

async function loadLaunchers() {
  try {
    const res = await fetch("/api/status", { cache: "no-store" });
    const data = await res.json();
    const chips = [];
    (data.groups || []).forEach(g => {
      (g.launchers || []).forEach(l => {
        chips.push(`<a class="quick-chip" href="/terminal?service=${qs(l.name)}">
          ${esc(l.name)}</a>`);
      });
      (g.services || []).forEach(s => {
        chips.push(`<a class="quick-chip" href="/terminal?service=${qs(s.name)}">
          ${esc(s.name)}</a>`);
      });
    });
    document.getElementById("quickLaunch").innerHTML = chips.join("");
  } catch (err) {}
}

document.getElementById("list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-kill]");
  if (!button) return;
  const name = button.dataset.kill;
  if (!confirm(`Terminate tmux session "${name}" and all processes in it?`)) return;
  button.disabled = true;
  out.textContent = `Terminating ${name}…`;
  const result = await post("/api/tmux/kill", { session: name });
  out.textContent = result.message || (result.ok ? "Session killed." : "Failed to kill session.");
  await load();
});

document.getElementById("newSession").addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = document.getElementById("name").value.trim();
  const cwd = document.getElementById("cwd").value.trim();
  const command = document.getElementById("command").value.trim();
  if (!name) return;
  const btn = document.getElementById("createBtn");
  btn.disabled = true;
  out.textContent = `Creating session ${name}…`;
  const result = await post("/api/tmux/create", { name, cwd, command });
  if (result.ok && result.session) {
    location.href = "/terminal?session=" + qs(result.session);
  } else {
    out.textContent = result.message || "Failed to create session.";
    btn.disabled = false;
    await load();
  }
});

load();
loadLaunchers();
setInterval(load, 5000);
</script>
</body>
</html>
"""


RC_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude sessions · __TITLE__</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --raise: #1c2430; --border: #30363d; --text: #e6edf3;
    --muted: #8b949e; --up: #3fb950; --down: #f85149; --warn: #d29922; --unknown: #6e7681;
    --accent: #58a6ff;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --panel: #fff; --raise: #eef2f6; --border: #d0d7de;
            --text: #1f2328; --muted: #636c76; --accent: #0969da; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5
    ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  a { color: inherit; }
  .wrap { max-width: 900px; margin: 0 auto; padding: 24px 18px 64px; }
  header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 16px; }
  h1 { font-size: 22px; margin: 0; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--muted); margin: 30px 0 10px; font-weight: 600; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .lede { color: var(--muted); font-size: 13px; margin: 10px 0 0; max-width: 66ch; }
  .dot { width: 9px; height: 9px; border-radius: 50%; flex: none; background: var(--unknown); }
  .dot.up { background: var(--up); } .dot.down { background: var(--down); }
  .dot.warn { background: var(--warn); }
  .card { background: var(--panel); border: 1px solid var(--border); border-left-width: 3px;
    border-radius: 8px; padding: 13px 15px; margin-top: 10px; }
  .card.up { border-left-color: var(--up); } .card.down { border-left-color: var(--down); }
  .card.warn { border-left-color: var(--warn); }
  .card.unknown { border-left-color: var(--unknown); }
  .top { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
  .who { font-weight: 600; font-size: 15px; }
  .unit { color: var(--muted); font-size: 12px; font-family: ui-monospace, SFMono-Regular,
    Menlo, Consolas, monospace; }
  .facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 2px 16px; margin-top: 8px; font-size: 12px; color: var(--muted); }
  .facts b { color: var(--text); font-weight: 500; overflow-wrap: anywhere; }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  button, .btn { background: var(--panel); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 4px 11px; font-size: 12px; cursor: pointer;
    text-decoration: none; display: inline-flex; align-items: center; gap: 5px; }
  button:hover, .btn:hover { border-color: var(--muted); background: var(--raise); }
  button:disabled { opacity: 0.45; cursor: default; }
  button.danger:hover { border-color: var(--down); color: var(--down); }
  .warnrow { color: var(--warn); font-size: 12px; margin-top: 8px; }
  form { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 15px; }
  .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 12px; }
  label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
  input, select { width: 100%; background: var(--bg); color: var(--text); font: inherit;
    font-size: 14px; border: 1px solid var(--border); border-radius: 6px; padding: 6px 9px; }
  input:focus, select:focus { outline: none; border-color: var(--accent); }
  .hint { font-size: 12px; margin-top: 6px; min-height: 18px; color: var(--muted); }
  .hint.bad { color: var(--down); } .hint.good { color: var(--up); }
  pre { background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
    padding: 10px 12px; font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    white-space: pre-wrap; overflow-wrap: anywhere; margin: 10px 0 0; max-height: 320px;
    overflow: auto; }
  pre:empty { display: none; }
  footer { margin-top: 40px; color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Claude sessions</h1>
    <a class="back" href="/">&larr; __TITLE__</a>
  </header>
  <p class="lede">One <code>claude remote-control</code> process serves exactly one
  directory, so every workspace you want always-on is its own instance: its own
  <code>.env.&lt;name&gt;</code> and its own <code>claude-rc-ai-&lt;name&gt;</code> unit.
  Reach any of them from <a href="https://claude.ai/code" target="_blank"
  rel="noopener">claude.ai/code</a> or the Claude mobile app.</p>

  <h2>Instances</h2>
  <div id="list">loading…</div>
  <pre id="out"></pre>

  <h2>New instance</h2>
  <form id="new" autocomplete="off">
    <div class="row">
      <div>
        <label for="name">Name</label>
        <input id="name" name="name" placeholder="notes" spellcheck="false">
      </div>
      <div>
        <label for="workspace">Workspace directory</label>
        <input id="workspace" name="workspace" placeholder="/home/you/my_repos/notes"
          spellcheck="false">
      </div>
    </div>
    <div class="hint" id="check">The directory must already exist on this machine.</div>
    <div class="row">
      <div>
        <label for="spawn">Spawn mode</label>
        <select id="spawn"><option>worktree</option><option>same-dir</option>
          <option>session</option></select>
      </div>
      <div>
        <label for="permission">Permission mode</label>
        <select id="permission">__PERMISSIONS__</select>
      </div>
      <div>
        <label for="capacity">Capacity</label>
        <input id="capacity" type="number" min="1" max="256" value="8">
      </div>
      <div>
        <label for="session">Session name</label>
        <input id="session" placeholder="same as the name" spellcheck="false">
      </div>
    </div>
    <div class="acts"><button id="create" type="submit">Create &amp; start</button></div>
  </form>
  <footer>Instances live in <code>services/AI/claudeRcAI</code>; creating one writes its
  env files, starts the unit and registers it on the cockpit.</footer>
</div>
<script>
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const qs = encodeURIComponent;
const MANAGE = __MANAGE__;
const out = document.getElementById("out");

const post = (path, body) => fetch(path, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
}).then(r => r.json());

function say(result) {
  out.textContent = [result.message, result.output].filter(Boolean).join("\\n\\n");
  out.scrollIntoView({ block: "nearest" });
}

function card(i) {
  const acts = MANAGE ? `
    <button data-verb="restart" data-name="${esc(i.name)}">restart</button>
    <button data-verb="start" data-name="${esc(i.name)}">start</button>
    <button data-verb="stop" data-name="${esc(i.name)}">stop</button>
    ${i.removable ? `<button class="danger" data-verb="delete"
      data-name="${esc(i.name)}">delete</button>` : ""}` : "";
  return `<div class="card ${esc(i.state)}">
    <div class="top"><span class="dot ${esc(i.state)}"></span>
      <span class="who">${esc(i.label)}</span>
      <span class="unit">${esc(i.unit)}</span></div>
    <div class="facts">
      <span>state <b>${esc(i.detail)}</b></span>
      <span>workspace <b>${esc(i.workspace)}</b></span>
      <span>spawn <b>${esc(i.spawn)}</b></span>
      <span>capacity <b>${esc(i.capacity)}</b></span>
      <span>permissions <b>${esc(i.permission)}</b></span>
      <span>env <b>${esc(i.env_file)}</b></span>
    </div>
    ${i.workspace_exists ? "" :
      `<div class="warnrow">workspace is missing on this machine</div>`}
    ${i.needs_sudo ? `<div class="warnrow">system unit and no passwordless sudo:
      use “in a shell”, which can ask for your password.</div>` : ""}
    <div class="acts">
      ${acts}
      <a class="btn" href="/logs?service=${qs("rc:logs:" + i.name)}">logs</a>
      <a class="btn" href="/terminal?service=${qs("rc:restart:" + i.name)}">restart in a shell</a>
      <a class="btn" href="https://claude.ai/code" target="_blank" rel="noopener">open</a>
    </div>
  </div>`;
}

async function load() {
  const data = await (await fetch("/api/claude-rc", { cache: "no-store" })).json();
  document.getElementById("list").innerHTML = data.instances.map(card).join("");
}

document.getElementById("list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-verb]");
  if (!button) return;
  const { verb, name } = button.dataset;
  if (verb === "delete" && !confirm(
      `Stop claude-rc-ai-${name}, remove its unit and delete its env files?`)) return;
  document.querySelectorAll("#list button").forEach(b => { b.disabled = true; });
  out.textContent = `${verb} ${name || "default"}…`;
  say(await post("/api/claude-rc/" + (verb === "delete" ? "delete" : "action"),
                 { name, verb }));
  await load();
  document.querySelectorAll("#list button").forEach(b => { b.disabled = false; });
});

// Path checking as you type: the same check the create call runs, so the form
// never hands you a surprise after the fact.
let timer = null;
const hint = document.getElementById("check");
function verify() {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const workspace = document.getElementById("workspace").value.trim();
    if (!workspace) {
      hint.className = "hint";
      hint.textContent = "The directory must already exist on this machine.";
      return;
    }
    const r = await post("/api/claude-rc/validate",
                         { workspace, spawn: document.getElementById("spawn").value });
    hint.className = "hint " + (r.ok ? "good" : "bad");
    hint.textContent = r.ok ? (r.message || "OK — " + r.path) : r.message;
  }, 250);
}
document.getElementById("workspace").addEventListener("input", verify);
document.getElementById("spawn").addEventListener("change", verify);

document.getElementById("new").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.getElementById("create");
  button.disabled = true;
  out.textContent = "creating…";
  say(await post("/api/claude-rc/create", {
    name: document.getElementById("name").value.trim(),
    workspace: document.getElementById("workspace").value.trim(),
    spawn: document.getElementById("spawn").value,
    permission: document.getElementById("permission").value,
    capacity: document.getElementById("capacity").value,
    session: document.getElementById("session").value.trim(),
  }));
  button.disabled = false;
  await load();
});

load();
setInterval(load, 10000);
</script>
</body>
</html>
"""


LOGIN_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in · __TITLE__</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --border: #30363d; --text: #e6edf3;
    --muted: #8b949e; --down: #f85149; --accent: #58a6ff;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --panel: #fff; --border: #d0d7de; --text: #1f2328;
            --muted: #636c76; --accent: #0969da; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: flex; align-items: center;
    justify-content: center; background: var(--bg); color: var(--text); font: 15px/1.5
    ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  form { background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    padding: 24px; width: 320px; margin: 24px; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .sub { color: var(--muted); font-size: 13px; margin-bottom: 18px; }
  label { display: block; font-size: 12px; color: var(--muted); margin: 12px 0 4px; }
  input[type=text], input[type=password] { width: 100%; background: var(--bg);
    color: var(--text); font: inherit; border: 1px solid var(--border); border-radius: 6px;
    padding: 7px 10px; }
  input:focus { outline: none; border-color: var(--accent); }
  .keep { display: flex; align-items: center; gap: 8px; margin: 16px 0 4px;
    font-size: 13px; color: var(--muted); }
  .keep input { accent-color: var(--accent); width: 15px; height: 15px; }
  button { width: 100%; margin-top: 16px; background: var(--accent); border: none;
    color: #fff; font: inherit; font-weight: 600; border-radius: 6px; padding: 8px;
    cursor: pointer; }
  button:hover { filter: brightness(1.08); }
  .bad { color: var(--down); font-size: 13px; margin-top: 12px; }
  .note { color: var(--muted); font-size: 12px; margin-top: 14px; }
</style>
</head>
<body>
<form method="post" action="/login">
  <h1>__TITLE__</h1>
  <div class="sub">Sign in to reach the console.</div>
  <input type="hidden" name="next" value="__NEXT__">
  <label for="user">User</label>
  <input id="user" name="user" type="text" autocomplete="username" autofocus>
  <label for="password">Password</label>
  <input id="password" name="password" type="password" autocomplete="current-password">
  <div class="keep">
    <input id="remember" name="remember" type="checkbox" value="1" checked>
    <label for="remember" style="margin:0">Keep me signed in for __DAYS__ days</label>
  </div>
  <button type="submit">Sign in</button>
  __ERROR__
  <div class="note">Signing out, or changing the password in <code>.env</code>,
  ends every remembered session.</div>
</form>
</body>
</html>
"""


class StatusHandler(BaseHTTPRequestHandler):
    server_version = "HomelabStatus/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep journald readable
        if os.environ.get("STATUS_ACCESS_LOG"):
            super().log_message(fmt, *args)

    def _send(self, code, body, content_type, extra_headers=()):
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for key, value in extra_headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def _cookies(self):
        jar = {}
        for chunk in self.headers.get("Cookie", "").split(";"):
            key, _, value = chunk.strip().partition("=")
            if key:
                jar[key] = value
        return jar

    def _credentials_match(self, user, password):
        # compare_digest on both halves: a wrong user must cost the same as a
        # wrong password.
        return hmac.compare_digest(user, BASIC_USER) and hmac.compare_digest(
            password, BASIC_PASSWORD
        )

    def _https(self):
        """Whether the browser reached us over TLS (cloudflared says so)."""
        return self.headers.get("X-Forwarded-Proto", "").lower() == "https"

    def _session_cookie(self, token, days):
        bits = ["%s=%s" % (SESSION_COOKIE, token), "Path=/", "HttpOnly", "SameSite=Lax"]
        if days:  # no Max-Age = a session cookie, gone when the browser closes
            bits.append("Max-Age=%d" % (days * 86400))
        if self._https():
            bits.append("Secure")
        return "; ".join(bits)

    @staticmethod
    def _safe_next(raw):
        """Only ever redirect back into this site."""
        target = raw or "/"
        if not target.startswith("/") or target.startswith("//"):
            return "/"
        return target

    def _render_login(self, next_path, error=""):
        page = (
            LOGIN_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__NEXT__", html.escape(self._safe_next(next_path), quote=True))
            .replace("__DAYS__", str(SESSION_DAYS))
            .replace("__ERROR__", '<div class="bad">%s</div>' % html.escape(error)
                     if error else "")
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _do_login(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        form = parse_qs(self.rfile.read(max(0, min(length, 8000))).decode("utf-8", "replace"))
        next_path = self._safe_next((form.get("next") or ["/"])[0])
        user = (form.get("user") or [""])[0]
        password = (form.get("password") or [""])[0]

        if not self._credentials_match(user, password):
            time.sleep(1)  # blunt the obvious brute force
            self._render_login(next_path, "Wrong user or password.")
            return

        # Ticked: a cookie that outlives the browser. Unticked: one that does
        # not - the login still stops being asked for on every page of this
        # visit, which is what basic auth used to do.
        days = SESSION_DAYS if (form.get("remember") or [""])[0] else 0
        self._send(
            303, "", "text/plain; charset=utf-8",
            [("Location", next_path),
             ("Set-Cookie", self._session_cookie(mint_session(days or 1), days))],
        )

    def _logout(self):
        self._send(
            303, "", "text/plain; charset=utf-8",
            [("Location", "/login"),
             ("Set-Cookie", "%s=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
              % SESSION_COOKIE)],
        )

    def _deny(self, path):
        """Send whoever this is to the right kind of "you are not logged in".

        A browser gets the login form, so it can tick "keep me signed in";
        curl, the JSON API and the mobile app keep the basic-auth challenge
        they already speak.
        """
        if "text/html" in self.headers.get("Accept", ""):
            self._send(303, "", "text/plain; charset=utf-8",
                       [("Location", "/login?next=" + quote(path))])
            return
        self._send(
            401,
            "unauthorized\n",
            "text/plain; charset=utf-8",
            [("WWW-Authenticate", 'Basic realm="%s"' % TITLE)],
        )

    def _authorized(self):
        if not BASIC_USER and not BASIC_PASSWORD:
            return True
        if valid_session(self._cookies().get(SESSION_COOKIE, "")):
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        user, _, password = decoded.partition(":")
        return self._credentials_match(user, password)

    def _render_logs(self, params):
        name = (params.get("service") or [""])[0]
        check = find_check(name)
        if check is None:
            self._send(404, "unknown service\n", "text/plain; charset=utf-8")
            return

        try:
            lines = int((params.get("lines") or [str(LOG_LINES)])[0])
        except ValueError:
            lines = LOG_LINES
        lines = max(1, min(lines, LOG_LINES_MAX))

        text, source = fetch_logs(check, lines)

        if params.get("raw"):
            self._send(200, text + "\n", "text/plain; charset=utf-8")
            return

        link_choices = []
        for choice in (50, 200, 1000, LOG_LINES_MAX):
            css = ' class="on"' if choice == lines else ""
            link_choices.append(
                '<a href="/logs?service=%s&lines=%d"%s>%d</a>'
                % (quote(name), choice, css, choice)
            )

        page = (
            LOG_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__NAME__", html.escape(name))
            .replace("__SOURCE__", html.escape(source or "no log source"))
            .replace("__LINE_LINKS__", "".join(link_choices))
            .replace("__LOG__", html.escape(text))
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _render_rc(self):
        options = "".join(
            '<option%s>%s</option>' % (" selected" if mode == "auto" else "", mode)
            for mode in claude_rc.PERMISSION_MODES
        )
        page = (
            RC_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__PERMISSIONS__", options)
            .replace("__MANAGE__", "true" if RC_MANAGE else "false")
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _read_json(self):
        """Body of a management POST, or None when it is not one we accept.

        Two things stand between the page and a cross-site request: the JSON
        content type (a form post cannot send it without CORS) and an Origin
        that has to match the host this request arrived on.
        """
        if "application/json" not in self.headers.get("Content-Type", ""):
            return None
        origin = self.headers.get("Origin", "")
        if origin and urlparse(origin).netloc != self.headers.get("Host", ""):
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > 64_000:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _rc_api(self, path, body):
        if path == "/api/claude-rc/validate":
            result = claude_rc.validate_workspace(
                body.get("workspace", ""), body.get("spawn", "worktree")
            )
            self._send(200, json.dumps(result) + "\n", "application/json; charset=utf-8")
            return

        if not RC_MANAGE:
            self._send(403, "instance management is disabled\n",
                       "text/plain; charset=utf-8")
            return

        name = str(body.get("name", ""))
        if path == "/api/claude-rc/action":
            result = claude_rc.run(str(body.get("verb", "")), name)
            result.setdefault("message", "")
        elif path == "/api/claude-rc/create":
            result = claude_rc.create(
                name,
                body.get("workspace", ""),
                body.get("spawn", "worktree"),
                body.get("capacity", "8"),
                body.get("permission", "auto"),
                str(body.get("session", "")).strip(),
                config_path=CONFIG_PATH,
            )
        elif path == "/api/claude-rc/delete":
            result = claude_rc.delete(name, config_path=CONFIG_PATH)
        else:
            self._send(404, "not found\n", "text/plain; charset=utf-8")
            return
        self._send(200, json.dumps(result) + "\n", "application/json; charset=utf-8")

    def _render_tmux(self):
        page = (
            TMUX_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__PREFIX__", html.escape(tmux_manager.TMUX_PREFIX))
            .replace("__REPO_ROOT__", html.escape(REPO_ROOT))
        )
        self._send(200, page, "text/html; charset=utf-8")

    @staticmethod
    def _where(params):
        """Shell target from the query string, constrained to the two we run."""
        return "host" if (params.get("where") or [""])[0] == "host" else "auto"

    def _render_terminal(self, params):
        service = (params.get("service") or [""])[0]
        session = (params.get("session") or [""])[0]

        if not service and not session:
            self._send(400, "expected a service or session parameter\n", "text/plain; charset=utf-8")
            return

        if not TERMINAL_ENABLED:
            self._send(403, "terminals are disabled\n", "text/plain; charset=utf-8")
            return

        where = self._where(params)
        if session:
            check = None
            target_dir = os.path.expanduser("~")
            _, _, label, _ = terminal.build_command(
                None, target_dir, login_shell(), where, session=session
            )
            display_name = session
        else:
            check = find_check(service)
            if check is None:
                self._send(404, "unknown service\n", "text/plain; charset=utf-8")
                return
            _, _, label, _ = terminal.build_command(
                check, working_dir(check), login_shell(), where
            )
            display_name = service

        page = (
            TERMINAL_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__NAME__", html.escape(display_name))
            .replace("__SERVICE__", html.escape(service))
            .replace("__SESSION__", html.escape(session))
            .replace("__WHERE__", html.escape(where))
            .replace("__COMMAND__", html.escape(label))
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _issue_terminal_ticket(self, params):
        service = (params.get("service") or [""])[0]
        session = (params.get("session") or [""])[0]
        if not TERMINAL_ENABLED:
            self._send(403, "terminals are disabled\n", "text/plain; charset=utf-8")
            return
        if not service and not session:
            self._send(400, "missing service or session parameter\n", "text/plain; charset=utf-8")
            return
        if service and find_check(service) is None:
            self._send(404, "unknown service\n", "text/plain; charset=utf-8")
            return
        token = issue_ticket(service, self._where(params), session=session)
        body = json.dumps({"ticket": token}) + "\n"
        self._send(200, body, "application/json; charset=utf-8")

    def _open_terminal_socket(self, params):
        """Upgrade to WebSocket and hand the connection to the PTY bridge."""
        self.close_connection = True

        if not TERMINAL_ENABLED:
            self._send(403, "terminals are disabled\n", "text/plain; charset=utf-8")
            return

        key = self.headers.get("Sec-WebSocket-Key", "")
        upgrade = self.headers.get("Upgrade", "").lower()
        if upgrade != "websocket" or not key:
            self._send(400, "expected a websocket upgrade\n", "text/plain; charset=utf-8")
            return

        # The ticket is the authentication for this socket, and it names the
        # service or tmux session; nothing the client sends can influence the command itself.
        ticket_token = (params.get("ticket") or [""])[0]
        service, where, session = redeem_ticket(ticket_token)
        if not service and not session:
            self._send(403, "invalid or expired ticket\n", "text/plain; charset=utf-8")
            return

        if session:
            argv, cwd, _, init = terminal.build_command(
                None, os.path.expanduser("~"), login_shell(), where, session=session
            )
        else:
            check = find_check(service)
            if check is None:
                self._send(403, "invalid or expired ticket\n", "text/plain; charset=utf-8")
                return
            argv, cwd, _, init = terminal.build_command(
                check, working_dir(check), login_shell(), where
            )

        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", terminal.accept_key(key))
        self.end_headers()
        self.wfile.flush()

        terminal.run_session(
            self.connection, argv, cwd, idle_timeout=TERMINAL_IDLE, init=init
        )

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/login":
            self._do_login()
            return

        if not self._authorized():
            self._deny(self.path)
            return

        if path.startswith("/api/tmux/"):
            body = self._read_json()
            if body is None:
                self._send(400, "expected a same-origin JSON body\n", "text/plain; charset=utf-8")
                return
            if path == "/api/tmux/kill":
                res = tmux_manager.kill_session(str(body.get("session", "")))
                self._send(200, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path == "/api/tmux/create":
                res = tmux_manager.create_session(
                    str(body.get("name", "")),
                    cwd=str(body.get("cwd", "")).strip() or None,
                    command=str(body.get("command", "")).strip() or None,
                )
                self._send(200, json.dumps(res) + "\n", "application/json; charset=utf-8")
            else:
                self._send(404, "not found\n", "text/plain; charset=utf-8")
            return

        if not path.startswith("/api/claude-rc/"):
            self._send(404, "not found\n", "text/plain; charset=utf-8")
            return

        body = self._read_json()
        if body is None:
            self._send(400, "expected a same-origin JSON body\n",
                       "text/plain; charset=utf-8")
            return
        self._rc_api(path, body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query)

        if path == "/healthz":
            self._send(200, "ok\n", "text/plain; charset=utf-8")
            return

        # The WebSocket carries its own credential: a single-use ticket minted
        # by the authenticated page. Browsers do not reliably replay basic-auth
        # headers on an upgrade request, so the ticket is checked instead.
        if path == "/ws/terminal":
            self._open_terminal_socket(params)
            return

        # The login form is the one page you must be able to reach logged out.
        if path == "/login":
            if not BASIC_USER and not BASIC_PASSWORD:
                self._send(303, "", "text/plain; charset=utf-8", [("Location", "/")])
            elif self._authorized():
                self._send(303, "", "text/plain; charset=utf-8",
                           [("Location", self._safe_next((params.get("next") or ["/"])[0]))])
            else:
                self._render_login((params.get("next") or ["/"])[0])
            return
        if path == "/logout":
            self._logout()
            return

        if not self._authorized():
            self._deny(self.path)
            return

        if path == "/":
            page = (
                PAGE.replace("__TITLE__", TITLE)
                .replace("__REFRESH__", str(REFRESH))
                .replace("__LOGOUT__", ' · <a href="/logout">sign out</a>'
                         if BASIC_USER or BASIC_PASSWORD else "")
            )
            self._send(200, page, "text/html; charset=utf-8")
        elif path == "/api/status":
            body = json.dumps(snapshot(), indent=2) + "\n"
            self._send(200, body, "application/json; charset=utf-8")
        elif path == "/claude-rc":
            self._render_rc()
        elif path == "/api/claude-rc":
            body = json.dumps({"instances": claude_rc.instances(),
                               "manage": RC_MANAGE}, indent=2) + "\n"
            self._send(200, body, "application/json; charset=utf-8")
        elif path == "/tmux":
            self._render_tmux()
        elif path == "/api/tmux":
            sessions = tmux_manager.list_sessions()
            body = json.dumps({
                "sessions": sessions,
                "count": len(sessions),
                "prefix": tmux_manager.TMUX_PREFIX,
            }, indent=2) + "\n"
            self._send(200, body, "application/json; charset=utf-8")
        elif path == "/terminal":
            self._render_terminal(params)
        elif path == "/api/terminal-ticket":
            self._issue_terminal_ticket(params)
        elif path == "/logs":
            self._render_logs(params)
        elif path == "/api/logs":
            params["raw"] = ["1"]
            self._render_logs(params)
        else:
            self._send(404, "not found\n", "text/plain; charset=utf-8")


def main():
    if "--once" in sys.argv:  # smoke test: print one snapshot and exit
        print(json.dumps(snapshot(), indent=2))
        return
    load_checks()  # fail fast on a broken config
    server = ThreadingHTTPServer((HOST, PORT), StatusHandler)
    server.daemon_threads = True
    print("[OK] Homelab cockpit on http://%s:%d" % (HOST, PORT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
