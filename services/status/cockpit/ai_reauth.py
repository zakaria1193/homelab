"""AI CLI Re-authentication adapter for Homelab Cockpit.

Delegates all CLI auth queries and login state machine operations directly to aicli,
which acts as the single source of truth for AI tooling and future auth updates.
"""

import os
import re
import shlex
import subprocess
import sys
import time

from . import tmux_manager

_AICLI_DIR = os.environ.get("AICLI_DIR") or os.path.expanduser("~/my_repos/aicli")
if _AICLI_DIR not in sys.path and os.path.isdir(_AICLI_DIR):
    sys.path.insert(0, _AICLI_DIR)

import aicli  # noqa: E402

AGY_REAUTH_SESSION = tmux_manager.TMUX_PREFIX + "agy-reauth"


def auth_status():
    """Returns {claude: {authenticated: bool, detail: str}, agy: {authenticated: bool, detail: str}}."""
    config = aicli.load_config()
    return aicli.auth_status(config)


def start_claude_login():
    """Starts login flow for Claude Code via aicli."""
    config = aicli.load_config()
    return aicli.start_login(config, "claude")


def submit_claude_code(code):
    """Submits authorization code for Claude Code via aicli."""
    config = aicli.load_config()
    return aicli.submit_code(config, "claude", code)


def cancel_claude_login():
    """Cancels pending login for Claude Code via aicli."""
    config = aicli.load_config()
    return aicli.cancel_login(config, "claude")


def start_agy_login():
    """Start a fresh dedicated tmux session running `agy` for OAuth sign-in.

    When `agy` lands on the interactive "Select login method" menu, sends Enter
    to pick "1. Google OAuth" so the Google sign-in URL appears automatically.
    """
    if not tmux_manager.is_available():
        return {"ok": False, "error": "tmux is not installed on the host."}
    try:
        config = aicli.load_config()
        agy_bin = aicli.resolve_bin(config, "agy") or "agy"
    except Exception:
        agy_bin = "agy"

    if tmux_manager.has_session(AGY_REAUTH_SESSION):
        tmux_manager.kill_session(AGY_REAUTH_SESSION)

    tmux_manager.ensure_session(
        AGY_REAUTH_SESSION,
        cwd=os.path.expanduser("~"),
        init_command=shlex.quote(agy_bin),
    )

    # Wait briefly for agy's "Select login method" prompt and press Enter to
    # select option 1 ("Google OAuth") so the sign-in URL renders immediately.
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        pane = tmux_manager.capture_pane(AGY_REAUTH_SESSION) or ""
        if extract_agy_login_url(pane):
            break
        if "Select login method" in pane or "Google OAuth" in pane:
            try:
                subprocess.run(
                    ["tmux", "send-keys", "-t", AGY_REAUTH_SESSION, "Enter"],
                    capture_output=True, timeout=5, check=False,
                )
            except (OSError, subprocess.SubprocessError):
                pass
            break
        time.sleep(0.4)

    return {"ok": True, "session": AGY_REAUTH_SESSION}


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_OSC_HYPERLINK_RE = re.compile(r"\x1b\]8;[^\x1b]*\x1b\\")
_AGY_URL_RE = re.compile(r"https://accounts\.google\.com/\S+")
_URL_CONT_LINE_RE = re.compile(r"^[ \t]*([A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+)[ \t]*$")


def extract_agy_login_url(pane_text):
    """Pure: tmux pane text in, the first Google OAuth https:// URL out, or None.

    Strips ANSI/SGR escapes and OSC-8 hyperlink wrappers, and rejoins URLs that
    agy's TUI hard-wraps across consecutive lines with leading indentation.
    Only matches `https://accounts.google.com/...` so unrelated links in
    scrollback are never mistaken for an AGY sign-in URL.
    """
    if not pane_text:
        return None
    clean = _OSC_HYPERLINK_RE.sub("", pane_text)
    clean = _ANSI_RE.sub("", clean)
    lines = clean.splitlines()
    for idx, line in enumerate(lines):
        match = _AGY_URL_RE.search(line)
        if not match:
            continue
        url = match.group(0)
        # Only join continuation lines when the wrapped line is long (>= 60 chars)
        # and the URL reached the end of the line (how agy's TUI wraps long URLs).
        if line[match.end():].strip() == "" and len(line.rstrip()) >= 60:
            prev_len = len(line.rstrip())
            for nxt in lines[idx + 1:]:
                if prev_len < 60 or not nxt.strip():
                    break
                cont = _URL_CONT_LINE_RE.match(nxt)
                if not cont or cont.group(1).endswith("..."):
                    break
                url += cont.group(1)
                prev_len = len(nxt.rstrip())
        return url.rstrip(".,;:)>]}\"'")
    return None
