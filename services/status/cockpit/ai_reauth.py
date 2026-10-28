"""AI CLI Re-authentication adapter for Homelab Cockpit.

Delegates all CLI auth queries and login state machine operations directly to aicli,
which acts as the single source of truth for AI tooling and future auth updates.
"""

import os
import sys

_AICLI_DIR = os.environ.get("AICLI_DIR") or os.path.expanduser("~/my_repos/aicli")
if _AICLI_DIR not in sys.path and os.path.isdir(_AICLI_DIR):
    sys.path.insert(0, _AICLI_DIR)

import aicli  # noqa: E402


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
