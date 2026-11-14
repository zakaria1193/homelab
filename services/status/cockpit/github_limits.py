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
# The day of the month GitHub's billing cycle starts and the included minutes reset.
# The token cannot read it: see github.com/settings/billing.
BILLING_DAY = min(28, max(1, int(os.environ.get("STATUS_GITHUB_BILLING_DAY") or "1")))
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


class _NoAuthRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req and "Authorization" in new_req.headers:
            del new_req.headers["Authorization"]
        return new_req


_log_opener = urllib.request.build_opener(_NoAuthRedirectHandler)


def _job_has_quota_error(full_name, job_id):
    if not job_id:
        return False
    req = urllib.request.Request(API + f"/repos/{full_name}/actions/jobs/{job_id}/logs", headers={
        "Authorization": "Bearer " + _token(),
        "Accept": "application/vnd.github+json",
        "User-Agent": "homelab-cockpit",
    })
    try:
        with _log_opener.open(req, timeout=TIMEOUT) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            return "Artifact storage quota has been hit" in content or "Artifact storage quota" in content
    except Exception:
        return False


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
    """The billing cycle `when` falls in: (first day, first day of the next cycle)."""
    first = when.replace(day=BILLING_DAY, hour=0, minute=0, second=0, microsecond=0)
    if first > when:
        first = (first - timedelta(days=BILLING_DAY)).replace(day=BILLING_DAY)
    nxt = (first + timedelta(days=31)).replace(day=BILLING_DAY)
    return first, nxt


def _month_runs(full_name, first, end, cache):
    """One row per run in the month. Only a finished run goes in `cache`."""
    created = f"{first:%Y-%m-%d}..{end - timedelta(days=1):%Y-%m-%d}"
    rows = []
    for run in _paged(f"/repos/{full_name}/actions/runs?created={created}", "workflow_runs"):
        key = f"{full_name}/{run['id']}"
        row = cache.get(key)
        is_failure = run.get("conclusion") == "failure"
        if row is not None and "quota_failure" not in row:
            if not is_failure:
                row["quota_failure"] = False

        if row is None or "quota_failure" not in row:
            # filter=all: a re-run is billed again, and `latest` would hide the first try.
            jobs = _paged(f"/repos/{full_name}/actions/runs/{run['id']}/jobs?filter=all", "jobs")
            quota_failure = False
            if is_failure:
                for j in jobs:
                    if j.get("conclusion") == "failure":
                        steps = j.get("steps") or []
                        has_artifact_step = any(
                            s.get("conclusion") == "failure"
                            and any(k in (s.get("name") or "").lower() for k in ("artifact", "upload", "digest"))
                            for s in steps
                        )
                        if has_artifact_step and _job_has_quota_error(full_name, j.get("id")):
                            quota_failure = True
                            break
            row = {
                "workflow": run.get("name") or "(unnamed)",
                "day": (run.get("created_at") or "")[:10],
                "minutes": sum(job_minutes(j) for j in jobs),
                "quota_failure": quota_failure,
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
    quota_failing_repos = set()
    for repo in repos:
        full, name = repo["full_name"], repo["name"]
        try:
            per_repo_rows[name] = _month_runs(full, first, end, runs_cache)
            if any(r.get("quota_failure") for r in per_repo_rows[name]):
                quota_failing_repos.add(name)
            if need_previous:
                rows = _month_runs(full, prev_first, prev_end, {})
                prev_totals[name] = sum(r["minutes"] for r in rows)
            held = _storage(full)
        except GitHubError as err:
            problems.append(f"{name}: {err}")
            continue
        held["quota_failure"] = name in quota_failing_repos
        if held["artifact_bytes"] or held["cache_bytes"] or held["quota_failure"]:
            storage.append({"name": name, **held})

    if quota_failing_repos:
        names = sorted(quota_failing_repos)
        problems.append(
            f"Artifact storage quota exceeded: uploads failing in {', '.join(names)}. "
            "Private packages (GHCR) share the 500 MB quota."
        )

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
            "quota_exceeded": bool(quota_failing_repos),
            "quota_repos": sorted(quota_failing_repos),
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


def _check_and_notify_quota(state, sender=None, channel=None, csv_path=None):
    """Send high-priority Slack alert when storage quota is hit, and clear when resolved."""
    storage = (state.get("snapshot") or {}).get("storage") or {}
    quota_hit = bool(storage.get("quota_exceeded"))
    was_notified = bool(state.get("quota_notified"))

    try:
        from .notify import DEFAULT_CHANNEL, cockpit_url, lookup_webhook, send_slack
    except ImportError:
        return

    target_channel = channel or os.environ.get("STATUS_NOTIFY_CHANNEL", "").strip() or DEFAULT_CHANNEL
    webhook = lookup_webhook(target_channel, csv_path) if csv_path else lookup_webhook(target_channel)
    send_fn = sender or send_slack

    if quota_hit and not was_notified:
        repos = storage.get("quota_repos") or []
        repo_str = ", ".join(repos) if repos else "private repositories"
        title = "GitHub Actions Alert: Storage Quota Exceeded"
        message = (
            f"🚨 *GitHub Artifact Storage Quota Exceeded*\n\n"
            f"CI artifact uploads are failing in: *{repo_str}*.\n\n"
            f"GitHub has locked artifact uploads because the account-wide 500 MB storage allowance was reached. "
            f"Private GitHub Packages (GHCR container images) share this quota.\n\n"
            f"{cockpit_url()}github-limits"
        )
        if webhook and send_fn(title, message, "error", target_channel, webhook):
            state["quota_notified"] = True
    elif not quota_hit and was_notified:
        title = "GitHub Actions: Storage Quota Cleared"
        message = (
            f"✅ *GitHub Artifact Storage Quota Cleared*\n\n"
            f"Artifact storage is back within limits. CI artifact uploads have resumed.\n\n"
            f"{cockpit_url()}github-limits"
        )
        if webhook and send_fn(title, message, "ok", target_channel, webhook):
            state["quota_notified"] = False


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
        _check_and_notify_quota(state)
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
    return age.total_seconds() >= REFRESH or snapshot.get("month") != f"{_month_bounds(datetime.now(timezone.utc))[0]:%Y-%m}"


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
