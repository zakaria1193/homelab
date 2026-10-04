"""One row per AI workspace: its terminals and its Remote Control servers.

A workspace is a directory you talk to an agent in. The cockpit knows about it
from two sides: `type = shell` launchers in the AI Sessions group (local
`claude` / `agy` / shell terminals) and Remote Control instances (Claude's
`.env.<name>` files, Antigravity's). They are joined on the directory itself -
a launcher whose `dir` is an instance's workspace is the same workspace - so a
new RC instance lands on the right row with no extra config.
"""

import os

# The group whose launchers are the AI workspaces.
AI_SESSIONS_GROUP = "AI Sessions"


def _key(path):
    return os.path.realpath(path) if path else ""


def _claude_rc(inst):
    name = inst.get("name", "")
    return {
        "agent": "claude",
        "label": inst.get("label") or name or "homelab",
        "unit": inst.get("unit", ""),
        "state": inst.get("state", "unknown"),
        "detail": inst.get("detail", ""),
        "web": "https://claude.ai/code",
        "logs": "/logs?service=rc:logs:%s" % name,
        "manage": "/claude-rc",
    }


def _agy_rc(inst):
    name = inst.get("name", "")
    return {
        "agent": "antigravity",
        "label": inst.get("instance_name") or inst.get("label") or name or "homelab",
        "unit": inst.get("unit", ""),
        "state": inst.get("state", "unknown"),
        "detail": inst.get("detail", ""),
        "web": inst.get("dashboard_url") or "https://antigravity.google.com/",
        "logs": "/logs?service=%s" % ("antigravity-rc-" + name if name else "antigravity-rc"),
        "manage": "/antigravity-rc",
    }


def merge(launchers, claude_instances, agy_instances, checks, terminal_enabled=True):
    """Build the workspace rows.

    Launchers come first, in config order. A Remote Control workspace with no
    launcher gets a row of its own after them; its terminal buttons borrow a
    configured entry whose `dir` is that workspace (the instance's own
    `[claude-rc-<name>]` section, usually), and it has none when nothing points
    there.
    """
    rows = []
    by_dir = {}
    for l in launchers:
        row = {
            "name": l["name"],
            "service": l["name"],
            "icon": l.get("icon") or "briefcase",
            "note": l.get("note", ""),
            "dir": l.get("dir", ""),
            "command": l.get("command", ""),
            "claude_command": l.get("claude_command", ""),
            "agy_command": l.get("agy_command", ""),
            "custom": l.get("custom", False),
            "rc_locked": l.get("rc_locked", ""),
            "terminal": terminal_enabled,
            "rc": [],
        }
        rows.append(row)
        by_dir.setdefault(_key(row["dir"]), row)

    # Directory -> a configured entry that opens there, for RC-only rows.
    opens_in = {}
    for c in checks:
        opens_in.setdefault(_key(c.get("dir", "")), c)

    sources = [(i, _claude_rc(i)) for i in claude_instances] + [
        (i, _agy_rc(i)) for i in agy_instances
    ]
    for inst, rc in sources:
        key = _key(inst.get("workspace", ""))
        row = by_dir.get(key)
        if row is None:
            check = opens_in.get(key)
            row = {
                "name": rc["label"],
                "service": check["name"] if check else "",
                "icon": rc["agent"],
                "note": check.get("note", "") if check else "",
                "dir": inst.get("workspace", ""),
                "command": "",
                "claude_command": "",
                "agy_command": "",
                "custom": False,
                "rc_locked": check.get("rc_locked", "") if check else "",
                "terminal": terminal_enabled and bool(check),
                "rc": [],
            }
            rows.append(row)
            by_dir[key] = row
        row["rc"].append(rc)
    return rows
