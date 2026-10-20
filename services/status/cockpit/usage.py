"""Claude / Antigravity plan usage, polled for the cockpit's health bars.

Neither CLI exposes its rate-limit usage as a flag - it is the `/usage` slash
command, meant for an interactive session. aicli (services/AI/aicliAI/aicli.py)
is the one place that runs `<cli> -p "/usage"` and parses it, so this module
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

from .config import REPO_ROOT
# `or` rather than a get() default: an empty value in the .env means "default".
AICLI = os.environ.get("STATUS_AICLI_PATH") or os.path.join(
    REPO_ROOT, "services", "AI", "aicliAI", "aicli.py"
)

TIMEOUT = float(os.environ.get("STATUS_USAGE_TIMEOUT") or "40")
# How long a fetch is trusted before the next request triggers a background
# refresh. Minutes, not seconds - a plan's usage does not move fast enough to
# justify spawning either CLI on every 15-second poll.
REFRESH = float(os.environ.get("STATUS_USAGE_REFRESH") or "300")

UNKNOWN = "unknown"
OK = "ok"


def _unknown(detail):
    result = {"state": UNKNOWN, "detail": detail, "bars": {}}
    return {"claude": dict(result), "agy": dict(result)}


def _compute():
    try:
        result = subprocess.run(
            [sys.executable, AICLI, "usage", "--json"],
            capture_output=True, text=True, timeout=TIMEOUT, check=False,
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
                _cache["data"] = data
                _cache["at"] = time.time()
        finally:
            with _lock:
                _refreshing = False

    threading.Thread(target=worker, daemon=True).start()


def snapshot():
    with _lock:
        data = _cache["data"]
        age = time.time() - _cache["at"]

    if data is None or age >= REFRESH:
        _refresh_async()
    return data
