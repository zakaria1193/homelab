"""Claude / Antigravity plan usage, polled for the cockpit's health bars.

Neither CLI exposes its rate-limit usage as a flag - it is the `/usage` slash
command, meant for an interactive session. aicli (github.com/zakaria1193/aicli,
checked out next to this repo) is the one place that runs `<cli> -p "/usage"` and parses it, so this module
just shells out to `aicli usage --json`. That still starts a whole CLI (a
couple of seconds) to print a few lines of text, which is too slow and too
unrelated to the service probes in status_server.py to run on every page poll,
so it keeps its own long-lived cache here, refreshed in the background well
below the page's own refresh rate.
"""

import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
# `or` rather than a get() default: an empty value in the .env means "default".
AICLI_DIR = os.environ.get("AICLI_DIR") or os.path.join(os.path.dirname(REPO_ROOT), "aicli")
AICLI = os.environ.get("STATUS_AICLI_PATH") or os.path.join(AICLI_DIR, "aicli.py")
# homelab's own aicli config, unless the caller already picked one.
AICLI_CONFIG = os.path.join(REPO_ROOT, "services", "AI", "aicliAI", "aicli.toml")
QUOTA_CACHE_FILE = os.path.expanduser(
    os.environ.get("AICLI_QUOTA_CACHE") or "~/.local/state/aicli/quota.json"
)

TIMEOUT = float(os.environ.get("STATUS_USAGE_TIMEOUT") or "40")
# How long a healthy fetch is trusted before the next request triggers a
# background refresh.
REFRESH = float(os.environ.get("STATUS_USAGE_REFRESH") or "180")
# If a fetch failed / returned unknown, retry much sooner than 3 minutes.
ERROR_REFRESH = 15.0

UNKNOWN = "unknown"
OK = "ok"


def _unknown(detail):
    result = {"state": UNKNOWN, "detail": detail, "bars": {}}
    return {"claude": dict(result), "agy": dict(result)}


def _seed_from_aicli_cache():
    """Seed initial state from aicli's quota.json on cold start so the very
    first page load after a server restart doesn't show empty bars while the
    background CLI probe is still running."""
    try:
        with open(QUOTA_CACHE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return None
        out = {}
        for tool in ("claude", "agy"):
            hit = raw.get(tool)
            if isinstance(hit, dict) and isinstance(hit.get("result"), dict):
                out[tool] = hit["result"]
        if len(out) == 2:
            return out
    except (OSError, ValueError):
        pass
    return None


def _compute():
    try:
        result = subprocess.run(
            [sys.executable, AICLI, "usage", "--json"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            timeout=TIMEOUT, check=False,
            env={"AICLI_CONFIG": AICLI_CONFIG, **os.environ},
        )
    except (subprocess.TimeoutExpired, OSError):
        return _unknown("aicli usage timed out")
    if result.returncode != 0:
        return _unknown("aicli usage failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return _unknown("aicli usage returned invalid JSON")


_cache = {"at": 0.0, "data": None}
_lock = threading.Lock()
_refreshing = False


def _is_degraded(data):
    if not isinstance(data, dict):
        return True
    for tool in ("claude", "agy"):
        if (data.get(tool) or {}).get("state") != OK:
            return True
    return False


def _refresh_async():
    """Kick a background fetch unless one is already in flight.

    Called on a stale-but-present cache: whoever asked gets the old numbers
    immediately rather than waiting out another `claude`/`agy` startup, and
    the next poll after this one sees the refreshed data.
    """
    global _refreshing
    with _lock:
        if _refreshing:
            return
        _refreshing = True

    def worker():
        global _refreshing
        try:
            data = _compute()
            with _lock:
                # Only overwrite good data if the new probe succeeded or we had no good data
                if not _is_degraded(data) or _cache["data"] is None or _is_degraded(_cache["data"]):
                    _cache["data"] = data
                    _cache["at"] = time.time()
        finally:
            with _lock:
                _refreshing = False

    threading.Thread(target=worker, daemon=True).start()


def snapshot(force=False):
    with _lock:
        if _cache["data"] is None:
            seeded = _seed_from_aicli_cache()
            if seeded is not None:
                _cache["data"] = seeded
                _cache["at"] = time.time() - REFRESH  # mark stale so we still refresh immediately
        data = _cache["data"]
        age = time.time() - _cache["at"]
        ttl = ERROR_REFRESH if _is_degraded(data) else REFRESH

    if force or data is None or age >= ttl:
        _refresh_async()
    return data
