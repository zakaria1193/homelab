"""Claude / Antigravity plan usage, polled for the cockpit's health bars.

Neither CLI exposes its rate-limit usage as a flag - it is the `/usage` slash
command, meant for an interactive session. The only non-interactive way to it
is `<cli> -p "/usage"`, which starts the whole CLI (a couple of seconds) just
to print a few lines of text. That is too slow and too unrelated to the
service probes in status_server.py to run on every page poll, so it gets its
own long-lived cache here, refreshed in the background well below the page's
own refresh rate.
"""

import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

TIMEOUT = float(os.environ.get("STATUS_USAGE_TIMEOUT") or "30")
# How long a fetch is trusted before the next request triggers a background
# refresh. Minutes, not seconds - a plan's usage does not move fast enough to
# justify spawning either CLI on every 15-second poll.
REFRESH = float(os.environ.get("STATUS_USAGE_REFRESH") or "300")

UNKNOWN = "unknown"
OK = "ok"


def _run(cmd):
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


# "Current session: 76% used · resets Aug 25, 1:09am (Europe/Paris)"
_CLAUDE_SESSION_RE = re.compile(
    r"(?im)^Current session:\s*(\d+)%\s*used.*?resets\s+(.+?)\s*$"
)
# "Current week (all models): 6% used · resets Aug 31, 6:59pm (Europe/Paris)"
_CLAUDE_WEEK_RE = re.compile(
    r"(?im)^Current week[^:\n]*:\s*(\d+)%\s*used.*?resets\s+(.+?)\s*$"
)


def _claude_usage():
    if not shutil.which("claude"):
        return {"state": UNKNOWN, "detail": "claude CLI not found", "bars": {}}

    result = _run(["claude", "-p", "/usage"])
    if result is None:
        return {"state": UNKNOWN, "detail": "claude -p /usage timed out", "bars": {}}
    if result.returncode != 0:
        return {"state": UNKNOWN, "detail": "claude -p /usage failed", "bars": {}}

    text = result.stdout
    bars = {}
    session = _CLAUDE_SESSION_RE.search(text)
    if session:
        bars["five_hour"] = {"pct": int(session.group(1)), "reset": session.group(2)}
    week = _CLAUDE_WEEK_RE.search(text)
    if week:
        bars["weekly"] = {"pct": int(week.group(1)), "reset": week.group(2)}

    if not bars:
        return {"state": UNKNOWN, "detail": "could not parse /usage output", "bars": {}}
    return {"state": OK, "detail": "", "bars": bars}


# `agy -p "/usage"` prints one tab-separated line per (model group, period):
#   Gemini Models\tWeekly Limit Remaining\t0%\t2026-08-24T21:11:51Z
#   Gemini Models\tFive Hour Limit Remaining\tdisabled\t
# A plan can carry more than one model group (Gemini, "Claude and GPT models"),
# so the bar for each period takes whichever group is closer to its limit -
# that is the one a "health bar" exists to warn about. A period reported
# "disabled" for every group present has nothing to bar and is left out.
_AGY_PERIODS = {"Weekly": "weekly", "Five Hour": "five_hour"}


def _agy_usage():
    if not shutil.which("agy"):
        return {"state": UNKNOWN, "detail": "agy CLI not found", "bars": {}}

    result = _run(["agy", "-p", "/usage"])
    if result is None:
        return {"state": UNKNOWN, "detail": "agy -p /usage timed out", "bars": {}}
    if result.returncode != 0:
        return {"state": UNKNOWN, "detail": "agy -p /usage failed", "bars": {}}

    worst = {}
    for line in result.stdout.splitlines():
        cols = [c.strip() for c in line.split("\t")]
        if len(cols) < 3:
            continue
        group, label, value = cols[0], cols[1], cols[2]
        reset = cols[3] if len(cols) > 3 else ""
        period = next(
            (key for prefix, key in _AGY_PERIODS.items() if label.startswith(prefix)),
            None,
        )
        if period is None or not value.endswith("%"):
            continue  # "disabled" - no limit to bar for this group/period
        try:
            remaining = int(value.rstrip("%"))
        except ValueError:
            continue
        used = 100 - remaining
        current = worst.get(period)
        if current is None or used > current["pct"]:
            worst[period] = {"pct": used, "reset": reset, "group": group}

    if not worst:
        return {"state": UNKNOWN, "detail": "no active limits reported", "bars": {}}
    return {"state": OK, "detail": "", "bars": worst}


def _compute():
    with ThreadPoolExecutor(max_workers=2) as pool:
        claude_result, agy_result = pool.map(
            lambda fn: fn(), (_claude_usage, _agy_usage)
        )
    return {"claude": claude_result, "agy": agy_result}


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

    if data is None:
        # Nothing cached yet: the first request pays for one real fetch
        # rather than showing empty bars on a freshly started cockpit.
        data = _compute()
        with _lock:
            _cache["data"] = data
            _cache["at"] = time.time()
        return data

    if age >= REFRESH:
        _refresh_async()
    return data
