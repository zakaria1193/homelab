"""The cached status payload behind /api/status and `--once`."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import tmux_manager

from .config import CACHE_TTL, DOWN, REFRESH, SHELL, TERMINAL_ENABLED, TITLE, UNKNOWN, UP, WARN, load_checks
from .probes import run_check


# --------------------------------------------------------------------------- #
# Cached snapshot
# --------------------------------------------------------------------------- #
_cache = {"at": 0.0, "payload": None}
_cache_lock = threading.Lock()


def invalidate():
    """Make the next poll re-probe instead of serving the cached payload."""
    with _cache_lock:
        _cache["at"] = 0.0


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
                        "claude_command": check.get("claude_command", ""),
                        "agy_command": check.get("agy_command", ""),
                        # A launcher is a terminal unless it says otherwise.
                        "icon": check["icon"] or "terminal",
                        "dir": check["dir"],
                        "custom": check.get("custom", False),
                        "enabled": TERMINAL_ENABLED,
                    }
                )
            else:
                group["services"].append(by_name[check["name"]])

        tmux_sessions = tmux_manager.list_sessions()
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
                "count": len(tmux_sessions),
                "sessions": tmux_sessions,
                "last_active": tmux_sessions[0] if tmux_sessions else None,
            },
        }
        _cache["at"] = time.time()
        _cache["payload"] = payload
        return payload
