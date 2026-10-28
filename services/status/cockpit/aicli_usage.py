"""Add up the aicli usage log for the cockpit's AI usage page.

Two writers append one JSON line per request (and per model, for a run that
used more than one) to the same file: the HTTP service
(aicli repo: server.py, `usage_rows`/`record_usage`) and `aicli run`
(aicli.py, `cmd_run`). The HTTP lines carry token counts
and `reported: true`; `aicli run` lines carry neither, since it `exec`s the
real CLI and never sees the result - those still count as a request, with
zero tokens, counted under `unreported`. See ticket homelab-0018.
"""

import json
import os
from datetime import datetime, timedelta, timezone

USAGE_LOG_PATH = (
    os.environ.get("STATUS_AICLI_USAGE_LOG")
    or os.environ.get("AICLI_USAGE_LOG")
    or os.path.expanduser("~/.local/state/aicli/usage.jsonl")
)

COUNT_KEYS = ("input", "output", "cache_write", "cache_read")

# Keyed on (path, mtime, size): a page poll that finds the file unchanged
# skips re-reading and re-parsing it.
_cache = {"key": (), "rows": []}


def _empty_counts():
    return {"requests": 0, "tokens": 0, "input": 0, "output": 0,
            "cache_write": 0, "cache_read": 0, "unreported": 0, "cost": None}


def _row_tokens(row):
    total = row.get("total")
    if isinstance(total, (int, float)):
        return int(total)
    return sum(int(row[k]) for k in COUNT_KEYS if isinstance(row.get(k), (int, float)))


def _is_unreported(row):
    """`aicli run` lines have no `reported` key and no counts at all; the
    HTTP service always writes `reported` (true or false)."""
    if "reported" in row:
        return row.get("reported") is False
    return not any(isinstance(row.get(k), (int, float)) for k in COUNT_KEYS + ("total",))


def _parse_at(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at.astimezone()


def _parse_rows(path):
    rows = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            at = _parse_at(row.get("at"))
            if at is None:
                continue
            rows.append((at, row))
    return rows


def _cached_rows(path):
    """(rows, error). `error` is set only for a real read failure (e.g. a
    permissions problem) - a missing file is just an empty log."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return [], None
    except OSError as e:
        return None, str(e)

    key = (path, st.st_mtime, st.st_size)
    if _cache["key"] != key:
        try:
            rows = _parse_rows(path)
        except OSError as e:
            return None, str(e)
        _cache["key"] = key
        _cache["rows"] = rows
    return _cache["rows"], None


# Claude's plan meters are not public but track what the same tokens would
# cost on the API, so tokens are weighed by list price to rank what drains the
# plan. USD per million tokens (input, output, cache read); a cache write is
# 1.25x input. First match wins. Only Claude models are priced: agy's Gemini
# models bill a separate meter.
PRICES = (
    ("opus-5-5", 4.0, 20.0, 0.20),
    ("opus", 5.0, 25.0, 0.50),
    ("sonnet-4", 3.0, 15.0, 0.30),
    ("sonnet", 2.0, 10.0, 0.20),
    ("haiku-5", 0.10, 0.50, 0.01),
    ("haiku", 1.0, 5.0, 0.10),
)


def api_cost(model, row):
    """API-price equivalent of a row's tokens in USD, or None for a model with
    no price (not Claude, or a Claude model this table does not know)."""
    model = str(model or "").lower()
    if "claude" not in model:
        return None
    for key, inp, out, read in PRICES:
        if key in model:
            n = lambda k: int(row.get(k)) if isinstance(row.get(k), (int, float)) else 0
            return (n("input") * inp + n("output") * out + n("cache_write") * inp * 1.25
                    + n("cache_read") * read) / 1e6
    return None


RANGES = {"24h": ("hour", 24), "48h": ("hour", 48), "7d": ("day", 7), "30d": ("day", 30)}


def window(name, now=None):
    """(name, bucket, start, keys) for a range: 24h/48h in whole local hours,
    7d/30d in local days ending today. Anything else is 24h."""
    name = name if name in RANGES else "24h"
    bucket, n = RANGES[name]
    now = now.astimezone() if now else datetime.now().astimezone()
    if bucket == "hour":
        first = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=n - 1)
        keys = [_bucket_key(first + timedelta(hours=i), bucket) for i in range(n)]
        return name, bucket, first, keys
    today = now.date()
    days = [today - timedelta(days=n - 1 - i) for i in range(n)]
    start = datetime(days[0].year, days[0].month, days[0].day).astimezone()
    return name, bucket, start, [d.isoformat() for d in days]


def _bucket_key(at, bucket):
    at = at.astimezone()
    if bucket == "hour":
        return at.replace(minute=0, second=0, microsecond=0).isoformat(timespec="minutes")
    return at.date().isoformat()


def _add(dest, row, tokens, unreported, cost):
    dest["requests"] += 1
    dest["tokens"] += tokens
    if cost is not None:
        dest["cost"] = (dest.get("cost") or 0.0) + cost
    if unreported:
        dest["unreported"] += 1
        return
    for key in COUNT_KEYS:
        value = row.get(key)
        if isinstance(value, (int, float)):
            dest[key] += int(value)


def _finalize(rows_by_key, key_name):
    out = [{key_name: name, **counts} for name, counts in rows_by_key.items()]
    out.sort(key=lambda r: (-(r.get("cost") or 0), -r["tokens"], -r["requests"]))
    return out


def usage_summary(range_name="24h", path=None, now=None, model=None, client=None):
    """{"ok": True, "range", "bucket", "start", "buckets": [...], "by_model",
    "by_client", "totals"} over the last 24 or 48 hours (hourly buckets) or 7
    or 30 days (daily), local time. Each bucket counts requests per client:
    `aicli run` never sees token counts, so requests are the one measure every
    line has. `model` and `client` keep only matching lines; `models` and
    `clients` list every name in the window, whatever the filter, so a page can
    fill its pickers. {"ok": False, "message": ...} when the log can't be read."""
    path = path or USAGE_LOG_PATH
    rows, error = _cached_rows(path)
    if error is not None:
        return {"ok": False, "message": f"aicli usage log not readable: {error}"}
    rows = rows or []

    now = now.astimezone() if now else datetime.now().astimezone()
    name, bucket, start, keys = window(range_name, now)
    want_model, want_client = (model or "").strip(), (client or "").strip()
    buckets = {k: {"requests": 0, "tokens": 0, "clients": {}} for k in keys}

    by_model = {}
    by_client = {}
    totals = _empty_counts()
    models, clients = set(), set()

    for at, row in rows:
        if at < start or at > now:
            continue
        key = _bucket_key(at, bucket)
        if key not in buckets:
            continue
        tokens = _row_tokens(row)
        unreported = _is_unreported(row)
        if unreported:
            tokens = 0

        model = row.get("model") or row.get("tool") or "unknown"
        model = str(model) if str(model).strip() else "unknown"
        client = row.get("client")
        client = str(client).strip() if isinstance(client, str) and str(client).strip() else "unknown"
        models.add(model)
        clients.add(client)
        if (want_model and model != want_model) or (want_client and client != want_client):
            continue
        cost = None if unreported else api_cost(model, row)

        _add(by_model.setdefault(model, _empty_counts()), row, tokens, unreported, cost)
        c = by_client.setdefault(client, {**_empty_counts(), "models": []})
        _add(c, row, tokens, unreported, cost)
        if model not in c["models"]:
            c["models"].append(model)
        _add(totals, row, tokens, unreported, cost)

        b = buckets[key]
        b["requests"] += 1
        b["tokens"] += tokens
        b["clients"][client] = b["clients"].get(client, 0) + 1

    return {
        "ok": True,
        "range": name,
        "bucket": bucket,
        "start": start.isoformat(timespec="seconds"),
        "buckets": [{"at": k, **buckets[k]} for k in keys],
        "by_model": _finalize(by_model, "model"),
        "by_client": _finalize(by_client, "client"),
        "totals": totals,
        "models": sorted(models),
        "clients": sorted(clients),
        "model": want_model,
        "client": want_client,
    }
