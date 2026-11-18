"""Read-only Cloudflare D1 HTTP API client for the /communities page's
member count, event count and last-ingest time (homelab-0024, plan item 1).

Only `SELECT` queries, scoped by `community_id`, ever leave this module.
Unlike `cockpit/github_limits.py`'s paginated, many-call collection, one D1
query is a single cheap round trip, so this keeps a plain cache-with-TTL
instead of a background-refresh thread: a page load calls Cloudflare at most
once per `CACHE_TTL` seconds per community. A missing `CF_ACCOUNT_ID`/
`CF_D1_READ_TOKEN`, a failed call or a timeout never raises past `counts()`;
callers always get a dict with an "error" key and `None` counts instead."""

import json
import os
import threading
import time
import urllib.error
import urllib.request

DATABASE_ID = "84b3b47f-eb95-49ac-9c23-8318f759bb3d"
API = "https://api.cloudflare.com/client/v4"
TIMEOUT = float(os.environ.get("STATUS_D1_TIMEOUT") or "10")
CACHE_TTL = float(os.environ.get("STATUS_D1_CACHE_TTL") or "300")

_lock = threading.Lock()
_cache = {}  # community_id -> (monotonic time fetched, data)


def _account():
    return os.environ.get("CF_ACCOUNT_ID", "").strip()


def _token():
    return os.environ.get("CF_D1_READ_TOKEN", "").strip()


def _query(sql, params):
    url = "%s/accounts/%s/d1/database/%s/query" % (API, _account(), DATABASE_ID)
    body = json.dumps({"sql": sql, "params": params}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + _token(),
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.load(resp)
    if not data.get("success"):
        messages = [e.get("message", "") for e in (data.get("errors") or [])]
        raise RuntimeError("; ".join(m for m in messages if m) or "D1 query failed")
    return data["result"][0]["results"]


def _fetch_counts(community_id, query_fn):
    members = query_fn("SELECT COUNT(*) AS n FROM community_profiles WHERE community_id = ?", [community_id])
    events = query_fn(
        "SELECT COUNT(*) AS n, MAX(last_seen_at) AS last_ingest FROM events WHERE community_id = ?",
        [community_id],
    )
    return {
        "members": members[0]["n"] if members else 0,
        "events": events[0]["n"] if events else 0,
        "last_ingest": events[0]["last_ingest"] if events else None,
        "error": "",
    }


def counts(community_id, query_fn=None, now=None):
    """Member count, event count and last-ingest time for one community id.
    `query_fn` and `now` are only for tests (a fake API and a fake clock)."""
    if not _account() or not _token():
        return {"members": None, "events": None, "last_ingest": None,
                "error": "CF_ACCOUNT_ID/CF_D1_READ_TOKEN not set"}

    now = time.monotonic() if now is None else now
    with _lock:
        cached = _cache.get(community_id)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    try:
        data = _fetch_counts(community_id, query_fn or _query)
    except (RuntimeError, urllib.error.URLError, ValueError, KeyError, IndexError, TimeoutError) as exc:
        data = {"members": None, "events": None, "last_ingest": None, "error": str(exc) or "D1 query failed"}

    with _lock:
        _cache[community_id] = (now, data)
    return data
