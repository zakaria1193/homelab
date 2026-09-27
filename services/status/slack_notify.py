"""Post board events to Slack (stdlib only).

Channel per board: its frontmatter `slack_channel:` (id or #name). Boards
without one fall back to SLACK_IDEAS_CHANNEL for the ideas boards (top-level
notes and rejected.md) and to SLACK_CHANNEL_ID for everything else. The bot
token (chat:write + chat:write.public) comes from ~/.config/homelab/slack.env.
"""

import json
import os
import re
import urllib.request

SLACK_ENV = os.path.expanduser(os.environ.get("SLACK_ENV_FILE", "~/.config/homelab/slack.env"))
API = "https://slack.com/api/chat.postMessage"


def load_env():
    """KEY=value pairs from slack.env, overridden by the process environment."""
    env = {}
    try:
        with open(SLACK_ENV, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
                if m:
                    env[m.group(1)] = m.group(2).strip("'\"")
    except OSError:
        pass
    for k in ("SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID", "SLACK_IDEAS_CHANNEL"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def channel_for(board_file, board_channel=""):
    """Where a board's events go."""
    if board_channel:
        return board_channel
    env = load_env()
    is_ideas = "/" not in board_file or board_file.startswith("rejected/")
    if is_ideas and env.get("SLACK_IDEAS_CHANNEL"):
        return env["SLACK_IDEAS_CHANNEL"]
    return env.get("SLACK_CHANNEL_ID", "")


def post(channel, text):
    """Send a message; returns {"ok": bool, "error": str}."""
    env = load_env()
    token = env.get("SLACK_BOT_TOKEN")
    if not token:
        return {"ok": False, "error": f"SLACK_BOT_TOKEN missing from {SLACK_ENV}"}
    if not channel:
        return {"ok": False, "error": "no channel configured"}
    body = json.dumps({"channel": channel, "text": text, "unfurl_links": False}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json; charset=utf-8",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
    except Exception as e:  # network errors must never break the board
        return {"ok": False, "error": str(e)}
    return {"ok": bool(data.get("ok")), "error": data.get("error", "")}
