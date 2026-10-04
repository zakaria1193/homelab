"""Cockpit settings (all from the environment) and services.conf parsing."""

import configparser
import os
import sys

# services/status: the directory holding services.conf and the Makefile.
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
# Cloudflare Access (Zero Trust) settings:
CF_ACCESS_ENABLED = os.environ.get("STATUS_CF_ACCESS_ENABLED", "1") not in ("0", "false", "no")
CF_ACCESS_AUD = os.environ.get("STATUS_CF_ACCESS_AUD", "").strip()
CF_ACCESS_TEAM_DOMAIN = os.environ.get("STATUS_CF_ACCESS_TEAM_DOMAIN", "").strip()
CF_ACCESS_ALLOWED_EMAILS = [
    e.strip().lower()
    for e in os.environ.get("STATUS_CF_ACCESS_ALLOWED_EMAILS", "").split(",")
    if e.strip()
]
REQUIRE_CF_ACCESS = os.environ.get("STATUS_REQUIRE_CF_ACCESS", "0") in ("1", "true", "yes")

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
                "note": section.get("note", ""),
                "command": section.get("command", ""),
                "claude_command": section.get("claude_command", ""),
                "agy_command": section.get("agy_command", ""),
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
                "custom": section.getboolean("custom", fallback=False),
                # Why no Remote Control server may run in this `dir` (e.g. the
                # code really runs on the Pi). Empty means RC is allowed.
                "rc_locked": section.get("rc_locked", "").strip(),
            }
        )
        if pi_host and pi_host in " ".join(
            (checks[-1]["link"], checks[-1]["remote"], checks[-1]["url"], checks[-1]["host"])
        ):
            checks[-1]["node"] = "pi"
    return checks


def rc_locked_reason(workspace):
    """The `rc_locked` reason of an entry whose `dir` is this workspace, or ""."""
    path = os.path.realpath(os.path.expanduser((workspace or "").strip()))
    for check in load_checks():
        if check["rc_locked"] and check["dir"] and os.path.realpath(check["dir"]) == path:
            return check["rc_locked"]
    return ""
