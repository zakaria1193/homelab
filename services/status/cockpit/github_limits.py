"""GitHub Actions minutes, storage and API rate limits for the /github-limits page.

GitHub's billing API needs a permission the homelab token does not have, so
this module counts for itself: every job of every run in a private repo, rounded
up per job and weighted by runner OS, the way GitHub bills them. The result is a
close estimate rather than the invoice, and the page says so.

That takes one API call per repo per listing and one per new run, so collecting
runs in a background thread, at most once an hour and only while someone is
looking. A finished run's minutes cannot change, so they are kept on disk and
never asked for twice, and the page does not cost GitHub's rate limit what it is
there to watch. /rate_limit itself is free.
"""

import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
from calendar import monthrange
from datetime import datetime, timedelta, timezone

from .config import REPO_ROOT

API = "https://api.github.com"
ENV_FILE = os.path.join(REPO_ROOT, "services", "github", ".env")

# `or` rather than a get() default: an empty value in the .env means "default".
STATE_FILE = os.path.expanduser(
    os.environ.get("STATUS_GITHUB_LIMITS_STATE") or "~/.local/state/homelab-status/github-limits.json"
)
REFRESH = float(os.environ.get("STATUS_GITHUB_LIMITS_REFRESH") or "3600")
RATE_REFRESH = 60.0
TIMEOUT = 20.0
# GitHub's Free plan. The token cannot read which plan this account is on.
MINUTES_LIMIT = int(os.environ.get("STATUS_GITHUB_MINUTES_LIMIT") or "2000")
ARTIFACT_LIMIT_MB = int(os.environ.get("STATUS_GITHUB_ARTIFACT_LIMIT_MB") or "500")
CACHE_LIMIT_BYTES = 10 * 10**9  # per repo; GitHub evicts the oldest caches above it
# Leave the budget to the things that actually need it.
MIN_RATE_REMAINING = 500
MAX_PAGES = 20

_lock = threading.Lock()
_state = None
_collecting = False
_last_attempt = 0.0
_rate = {"at": 0.0, "resources": [], "fetching": False}


class GitHubError(Exception):
    pass


def _token():
    if env := os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return env
    try:
        with open(ENV_FILE) as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key.removeprefix("export ").strip() == "GH_TOKEN":
                    return value.strip().strip("'\"")
    except OSError:
        pass
    return ""


def _api(path):
    req = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + _token(),
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "homelab-cockpit",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as err:
        raise GitHubError(f"HTTP {err.code} on {path.split('?')[0]}") from err
    except (OSError, ValueError) as err:
        raise GitHubError(f"{path.split('?')[0]}: {err}") from err


def _paged(path, key=None):
    """Every item of a listing. `key` names the list in the answer, if it is wrapped."""
    sep = "&" if "?" in path else "?"
    items = []
    for page in range(1, MAX_PAGES + 1):
        data = _api(f"{path}{sep}per_page=100&page={page}")
        batch = data[key] if key else data
        items.extend(batch)
        if len(batch) < 100:
            break
    return items


def _parse(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def job_minutes(job):
    """What one job costs: whole minutes rounded up, weighted by runner OS."""
    if not job.get("started_at") or not job.get("completed_at"):
        return 0
    labels = " ".join(job.get("labels") or []).lower()
    if "self-hosted" in labels:
        return 0
    weight = 10 if "macos" in labels else 2 if "windows" in labels else 1
    seconds = (_parse(job["completed_at"]) - _parse(job["started_at"])).total_seconds()
    return math.ceil(max(0, seconds) / 60) * weight


def _month_bounds(when):
    first = when.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last = monthrange(first.year, first.month)[1]
    return first, first + timedelta(days=last)


def _month_runs(full_name, first, end, cache):
    """One row per run in the month. Only a finished run goes in `cache`."""
    created = f"{first:%Y-%m-%d}..{end - timedelta(days=1):%Y-%m-%d}"
    rows = []
    for run in _paged(f"/repos/{full_name}/actions/runs?created={created}", "workflow_runs"):
        key = f"{full_name}/{run['id']}"
        row = cache.get(key)
        if row is None:
            # filter=all: a re-run is billed again, and `latest` would hide the first try.
            jobs = _paged(f"/repos/{full_name}/actions/runs/{run['id']}/jobs?filter=all", "jobs")
            row = {
                "workflow": run.get("name") or "(unnamed)",
                "day": (run.get("created_at") or "")[:10],
                "minutes": sum(job_minutes(j) for j in jobs),
            }
            if run.get("status") == "completed":
                cache[key] = row
        rows.append(row)
    return rows


def _storage(full_name):
    artifacts = [a for a in _paged(f"/repos/{full_name}/actions/artifacts", "artifacts")
                 if not a.get("expired")]
    grouped = {}
    for a in artifacts:
        group = grouped.setdefault(a.get("name") or "(unnamed)", {"bytes": 0, "count": 0})
        group["bytes"] += a.get("size_in_bytes") or 0
        group["count"] += 1
    top = sorted(({"name": k, **v} for k, v in grouped.items() if v["bytes"]),
                 key=lambda g: -g["bytes"])[:3]
    cache = _api(f"/repos/{full_name}/actions/cache/usage")
    return {
        "artifact_bytes": sum(a.get("size_in_bytes") or 0 for a in artifacts),
        "cache_bytes": cache.get("active_caches_size_in_bytes") or 0,
        "cache_count": cache.get("active_caches_count") or 0,
        "top_artifacts": top,
    }


def _repo_minutes(name, rows, previous):
    workflows = {}
    for row in rows:
        wf = workflows.setdefault(row["workflow"], {"name": row["workflow"], "minutes": 0, "runs": 0})
        wf["minutes"] += row["minutes"]
        wf["runs"] += 1
    return {
        "name": name,
        "minutes": sum(r["minutes"] for r in rows),
        "previous": previous,
        "runs": len(rows),
        "workflows": sorted(workflows.values(), key=lambda w: -w["minutes"]),
    }


def _minutes_summary(now, per_repo_rows, closed):
    first, end = _month_bounds(now)
    used = sum(r["minutes"] for rows in per_repo_rows.values() for r in rows)
    prev_totals = closed.get("repos") or {}
    repos = [_repo_minutes(name, rows, prev_totals.get(name, 0))
             for name, rows in per_repo_rows.items()]
    # A repo with nothing this month can still be last month's biggest.
    repos = [r for r in repos if r["minutes"] or r["previous"]]
    repos.sort(key=lambda r: (-r["minutes"], -r["previous"], r["name"]))

    by_day = {}
    for rows in per_repo_rows.values():
        for r in rows:
            by_day[r["day"]] = by_day.get(r["day"], 0) + r["minutes"]
    days = [{"day": f"{first + timedelta(days=i):%Y-%m-%d}",
             "minutes": by_day.get(f"{first + timedelta(days=i):%Y-%m-%d}", 0)}
            for i in range((end - first).days)]

    # A pace from the first few hours of a month says nothing.
    elapsed = (now - first).total_seconds() / (end - first).total_seconds()
    enough = (now - first) >= timedelta(days=1)
    return {
        "used": used,
        "limit": MINUTES_LIMIT,
        "projected": round(used / elapsed) if enough else None,
        "previous": closed.get("total"),
        "previous_month": closed.get("month"),
        "days": days,
        "repos": repos,
    }


def collect(now=None, state=None):
    """One full sweep: returns the new state, including the page's snapshot."""
    now = now or datetime.now(timezone.utc)
    state = state or {}
    first, end = _month_bounds(now)
    prev_end = first
    prev_first, _ = _month_bounds(first - timedelta(days=1))
    month, prev_month = f"{first:%Y-%m}", f"{prev_first:%Y-%m}"

    runs_cache = state.get("runs") if state.get("runs_month") == month else {}
    runs_cache = dict(runs_cache or {})
    closed = state.get("closed") or {}
    need_previous = closed.get("month") != prev_month

    repos = [r for r in _paged("/user/repos?affiliation=owner") if r.get("private")]
    problems = []
    per_repo_rows, prev_totals, storage = {}, {}, []
    for repo in repos:
        full, name = repo["full_name"], repo["name"]
        try:
            per_repo_rows[name] = _month_runs(full, first, end, runs_cache)
            if need_previous:
                rows = _month_runs(full, prev_first, prev_end, {})
                prev_totals[name] = sum(r["minutes"] for r in rows)
            held = _storage(full)
        except GitHubError as err:
            problems.append(f"{name}: {err}")
            continue
        if held["artifact_bytes"] or held["cache_bytes"]:
            storage.append({"name": name, **held})

    if need_previous and not problems:
        closed = {"month": prev_month, "total": sum(prev_totals.values()),
                  "repos": {k: v for k, v in prev_totals.items() if v}}
    # A failed sweep must not pass off a partial month as the whole of it.
    shown_closed = closed if closed.get("month") == prev_month else {}

    storage.sort(key=lambda s: -(s["artifact_bytes"] + s["cache_bytes"]))
    snapshot = {
        "ok": True,
        "message": "",
        "updated_at": now.isoformat(),
        "month": month,
        "repos_checked": len(repos),
        "minutes": _minutes_summary(now, per_repo_rows, shown_closed),
        "storage": {
            "artifact_bytes": sum(s["artifact_bytes"] for s in storage),
            "artifact_limit_bytes": ARTIFACT_LIMIT_MB * 10**6,
            "cache_bytes": sum(s["cache_bytes"] for s in storage),
            "cache_limit_bytes": CACHE_LIMIT_BYTES,
            "repos": storage,
        },
        "problems": problems,
    }
    return {"snapshot": snapshot, "runs": runs_cache, "runs_month": month, "closed": closed}


def _load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, STATE_FILE)
    except OSError:
        pass  # the page still works, the next restart just counts again


def _fetch_rate():
    """Every limit the token has touched, busiest first. /rate_limit costs nothing."""
    data = _api("/rate_limit")["resources"]
    rows = [{"name": k, "used": v.get("used", 0), "limit": v.get("limit", 0),
             "remaining": v.get("remaining", 0), "reset": v.get("reset", 0)}
            for k, v in data.items()]
    # The two every caller draws on stay visible even when idle.
    rows = [r for r in rows if r["used"] or r["name"] in ("core", "graphql")]
    return sorted(rows, key=lambda r: (-r["used"] / (r["limit"] or 1), r["name"]))


def _sweep():
    global _state, _collecting
    try:
        with _lock:
            state = dict(_state or {})
        message = ""
        try:
            core = next((r for r in _fetch_rate() if r["name"] == "core"), None)
            if core and core["remaining"] < MIN_RATE_REMAINING:
                message = f"Skipped: only {core['remaining']} API calls left this hour"
            else:
                state = collect(state=state)
        except GitHubError as err:
            message = str(err)
        if message:
            # Keep the last good numbers and say why they are not newer.
            snapshot = dict(state.get("snapshot") or {"ok": False})
            snapshot["message"] = message
            state["snapshot"] = snapshot
        with _lock:
            _state = state
        _save_state(state)
    finally:
        with _lock:
            _collecting = False


def _refresh_rate():
    try:
        resources = _fetch_rate()
    except GitHubError:
        resources = None
    with _lock:
        if resources is not None:
            _rate["resources"] = resources
        _rate["fetching"] = False


def _is_stale(snapshot):
    try:
        age = datetime.now(timezone.utc) - _parse(snapshot["updated_at"])
    except (KeyError, TypeError, ValueError):
        return True
    # A new month starts from nothing, whatever the age of the last sweep.
    return age.total_seconds() >= REFRESH or snapshot.get("month") != f"{datetime.now(timezone.utc):%Y-%m}"


def _kick():
    """Start whichever background fetches are due. Called with the lock held."""
    global _collecting, _last_attempt
    now = time.monotonic()
    if not _rate["fetching"] and now - _rate["at"] >= RATE_REFRESH:
        _rate["fetching"] = True
        _rate["at"] = now
        threading.Thread(target=_refresh_rate, daemon=True).start()
    snapshot = (_state or {}).get("snapshot") or {}
    # _last_attempt: a sweep that keeps failing must not retry on every poll.
    retry_due = not _last_attempt or now - _last_attempt >= min(REFRESH, 300)
    if not _collecting and _is_stale(snapshot) and retry_due:
        _collecting = True
        _last_attempt = now
        threading.Thread(target=_sweep, daemon=True).start()


def snapshot():
    """What /api/github-limits answers. Never waits on GitHub."""
    global _state
    if not _token():
        return {"ok": False, "refreshing": False, "rate": [],
                "message": "No GH_TOKEN: set it in services/github/.env"}
    with _lock:
        if _state is None:
            _state = _load_state()
        _kick()
        data = dict(_state.get("snapshot") or {"ok": False, "message": ""})
        data["refreshing"] = _collecting
        data["rate"] = list(_rate["resources"])
    return data
