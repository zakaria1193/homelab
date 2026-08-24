#!/usr/bin/env python3
"""Homelab status dashboard.

Serves an always-on HTML page (plus a JSON API) showing the live state of every
homelab service. Deliberately depends on the Python standard library only, so it
stays reproducible on a fresh machine with no package installs.

Checks are declared in services.conf; see that file for the supported keys.
"""

import base64
import configparser
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

import terminal

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
TITLE = os.environ.get("STATUS_TITLE", "Homelab Status")
LINK_HOST = os.environ.get("STATUS_LINK_HOST", "")
CACHE_TTL = float(os.environ.get("STATUS_CACHE_TTL", "10"))
REFRESH = int(os.environ.get("STATUS_REFRESH", "15"))
TIMEOUT = float(os.environ.get("STATUS_TIMEOUT", "4"))
BASIC_USER = os.environ.get("STATUS_USER", "")
BASIC_PASSWORD = os.environ.get("STATUS_PASSWORD", "")
LOG_LINES = int(os.environ.get("STATUS_LOG_LINES", "200"))
LOG_LINES_MAX = int(os.environ.get("STATUS_LOG_LINES_MAX", "2000"))
LOG_TIMEOUT = float(os.environ.get("STATUS_LOG_TIMEOUT", "15"))
# Browser shells are remote code execution: set STATUS_TERMINAL=0 to disable.
TERMINAL_ENABLED = os.environ.get("STATUS_TERMINAL", "1") not in ("0", "false", "no")
TERMINAL_IDLE = float(os.environ.get("STATUS_TERMINAL_IDLE", "900"))
TERMINAL_SHELL = os.environ.get("STATUS_TERMINAL_SHELL", "")

UP, DOWN, WARN, UNKNOWN = "up", "down", "warn", "unknown"


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def resolve_path(value):
    """Expand ~ and resolve repo-relative paths from services.conf."""
    if not value:
        return ""
    expanded = os.path.expanduser(value)
    if os.path.isabs(expanded):
        return expanded
    return os.path.join(REPO_ROOT, expanded)


def load_checks():
    parser = configparser.ConfigParser()
    if not parser.read(CONFIG_PATH):
        sys.exit("[ERROR] config file not found: %s" % CONFIG_PATH)
    if LINK_HOST:
        parser["DEFAULT"]["host"] = LINK_HOST

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
                "note": section.get("note", ""),
                "dir": resolve_path(section.get("dir", "")),
                "path": resolve_path(section.get("path", "")),
                "logs": section.get("logs", ""),
                "ok_pattern": section.get("ok_pattern", ""),
                "fail_pattern": section.get("fail_pattern", ""),
                "max_age_hours": section.getfloat("max_age_hours", fallback=0.0),
            }
        )
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
    request = Request(url, headers={"User-Agent": "homelab-status/1.0"})
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


def find_check(name):
    """Look a service up by exact configured name (never by client-supplied path)."""
    return next((c for c in load_checks() if c["name"] == name), None)


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
            "note": check["note"],
            "has_logs": bool(log_source(check)[0]),
            "has_terminal": TERMINAL_ENABLED,
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
        with ThreadPoolExecutor(max_workers=max(len(checks), 1)) as pool:
            results = list(pool.map(run_check, checks))

        groups = []
        for result in results:
            group = next((g for g in groups if g["name"] == result["group"]), None)
            if group is None:
                group = {"name": result["group"], "services": []}
                groups.append(group)
            group["services"].append(result)

        payload = {
            "title": TITLE,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "refresh": REFRESH,
            "totals": {
                state: sum(1 for r in results if r["state"] == state)
                for state in (UP, WARN, DOWN, UNKNOWN)
            },
            "count": len(results),
            "groups": groups,
        }
        _cache["at"] = time.time()
        _cache["payload"] = payload
        return payload


# --------------------------------------------------------------------------- #
# Terminal tickets
# --------------------------------------------------------------------------- #
# Browsers do not reliably attach basic-auth headers to WebSocket upgrades, so
# the authenticated page mints a short-lived single-use ticket instead. Each
# ticket is bound to one service, so a client can never choose the command.
TICKET_TTL = 60.0
_tickets = {}
_ticket_lock = threading.Lock()


def issue_ticket(service):
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _ticket_lock:
        for stale, (_, expiry) in list(_tickets.items()):
            if expiry < now:
                del _tickets[stale]
        _tickets[token] = (service, now + TICKET_TTL)
    return token


def redeem_ticket(token):
    """Consume a ticket, returning the service it was issued for."""
    with _ticket_lock:
        entry = _tickets.pop(token, None)
    if entry is None:
        return None
    service, expiry = entry
    return service if expiry >= time.time() else None


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
    --bg: #0d1117; --panel: #161b22; --border: #30363d; --text: #e6edf3;
    --muted: #8b949e; --up: #3fb950; --down: #f85149; --warn: #d29922; --unknown: #6e7681;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --panel: #fff; --border: #d0d7de; --text: #1f2328; --muted: #636c76; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5
    ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 32px 20px 64px; }
  header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px 20px; margin-bottom: 8px; }
  h1 { font-size: 24px; margin: 0; letter-spacing: -0.01em; }
  .sub { color: var(--muted); font-size: 13px; }
  .totals { display: flex; gap: 14px; flex-wrap: wrap; margin: 18px 0 28px; }
  .pill { display: inline-flex; align-items: center; gap: 8px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 999px; padding: 6px 14px; font-size: 13px; }
  .pill b { font-variant-numeric: tabular-nums; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--muted); margin: 28px 0 10px; font-weight: 600; }
  .grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }
  .card { display: flex; align-items: flex-start; gap: 12px; background: var(--panel);
    border: 1px solid var(--border); border-left-width: 3px; border-radius: 8px; padding: 12px 14px; }
  .card.up { border-left-color: var(--up); }
  .card.down { border-left-color: var(--down); }
  .card.warn { border-left-color: var(--warn); }
  .card.unknown { border-left-color: var(--unknown); }
  .dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 6px; flex: none; }
  .up .dot { background: var(--up); }
  .down .dot { background: var(--down); }
  .warn .dot { background: var(--warn); }
  .unknown .dot { background: var(--unknown); }
  .body { min-width: 0; flex: 1; }
  .name { font-weight: 600; overflow-wrap: anywhere; }
  .name a { color: inherit; text-decoration: none; border-bottom: 1px solid var(--border); }
  .name a:hover { border-bottom-color: currentColor; }
  .name .logs { float: right; font-size: 12px; font-weight: 400; color: var(--muted);
    text-decoration: none; border: 1px solid var(--border); border-radius: 5px;
    padding: 0 7px; margin-left: 8px; }
  .name .logs:hover { color: var(--text); border-color: var(--muted); }
  .detail { font-size: 13px; margin-top: 2px; overflow-wrap: anywhere; }
  .down .detail { color: var(--down); }
  .warn .detail { color: var(--warn); }
  .meta { color: var(--muted); font-size: 12px; margin-top: 3px; font-variant-numeric: tabular-nums; }
  footer { margin-top: 40px; color: var(--muted); font-size: 12px; }
  .stale { opacity: 0.45; transition: opacity 0.2s; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>__TITLE__</h1>
    <span class="sub" id="updated">loading…</span>
  </header>
  <div class="totals" id="totals"></div>
  <main id="groups"></main>
  <footer>Auto-refreshing every __REFRESH__s · <a href="/api/status" style="color:inherit">JSON API</a></footer>
</div>
<script>
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function render(data) {
  const t = data.totals;
  document.getElementById("totals").innerHTML = [
    ["up", "up", t.up], ["warn", "degraded", t.warn],
    ["down", "down", t.down], ["unknown", "unknown", t.unknown],
  ].filter(([, , n]) => n > 0).map(([cls, label, n]) =>
    `<span class="pill ${cls}"><span class="dot"></span><b>${n}</b> ${label}</span>`
  ).join("");

  document.getElementById("groups").innerHTML = data.groups.map(group => `
    <h2>${esc(group.name)}</h2>
    <div class="grid">${group.services.map(s => `
      <div class="card ${esc(s.state)}">
        <span class="dot"></span>
        <div class="body">
          <div class="name">${s.link
            ? `<a href="${esc(s.link)}" target="_blank" rel="noopener">${esc(s.name)}</a>`
            : esc(s.name)}${s.has_terminal
            ? `<a class="logs" href="/terminal?service=${encodeURIComponent(s.name)}">shell</a>`
            : ""}${s.has_logs
            ? `<a class="logs" href="/logs?service=${encodeURIComponent(s.name)}">logs</a>`
            : ""}</div>
          <div class="detail">${esc(s.detail)}</div>
          <div class="meta">${[s.meta, s.note].filter(Boolean).map(esc).join(" · ")}</div>
        </div>
      </div>`).join("")}</div>`).join("");

  document.getElementById("updated").textContent = "updated " + data.generated_at;
  document.body.classList.remove("stale");
}

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
      const response = await fetch(
        "/api/terminal-ticket?service=" + encodeURIComponent(service),
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

  againEl.addEventListener("click", connect);
  connect();
}
</script>
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

    def _authorized(self):
        if not BASIC_USER and not BASIC_PASSWORD:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        user, _, password = decoded.partition(":")
        return hmac.compare_digest(user, BASIC_USER) and hmac.compare_digest(
            password, BASIC_PASSWORD
        )

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

    def _render_terminal(self, params):
        name = (params.get("service") or [""])[0]
        check = find_check(name)
        if check is None:
            self._send(404, "unknown service\n", "text/plain; charset=utf-8")
            return
        if not TERMINAL_ENABLED:
            self._send(403, "terminals are disabled\n", "text/plain; charset=utf-8")
            return

        _, _, label, _ = terminal.build_command(
            check, working_dir(check), login_shell()
        )
        page = (
            TERMINAL_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__NAME__", html.escape(name))
            .replace("__SERVICE__", html.escape(name))
            .replace("__COMMAND__", html.escape(label))
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _issue_terminal_ticket(self, params):
        name = (params.get("service") or [""])[0]
        if not TERMINAL_ENABLED:
            self._send(403, "terminals are disabled\n", "text/plain; charset=utf-8")
            return
        if find_check(name) is None:
            self._send(404, "unknown service\n", "text/plain; charset=utf-8")
            return
        body = json.dumps({"ticket": issue_ticket(name)}) + "\n"
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
        # service; nothing the client sends can influence the command itself.
        name = redeem_ticket((params.get("ticket") or [""])[0])
        check = find_check(name) if name else None
        if check is None:
            self._send(403, "invalid or expired ticket\n", "text/plain; charset=utf-8")
            return

        argv, cwd, _, init = terminal.build_command(
            check, working_dir(check), login_shell()
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

        if not self._authorized():
            self._send(
                401,
                "unauthorized\n",
                "text/plain; charset=utf-8",
                [("WWW-Authenticate", 'Basic realm="%s"' % TITLE)],
            )
            return

        if path == "/":
            page = PAGE.replace("__TITLE__", TITLE).replace("__REFRESH__", str(REFRESH))
            self._send(200, page, "text/html; charset=utf-8")
        elif path == "/api/status":
            body = json.dumps(snapshot(), indent=2) + "\n"
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
    print("[OK] Homelab status dashboard on http://%s:%d" % (HOST, PORT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
