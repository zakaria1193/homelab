"""Add up the aicli proxy's usage log for the cockpit's AI Routes panel.

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
            "cache_write": 0, "cache_read": 0, "unreported": 0}


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


def _add(dest, row, tokens, unreported):
    dest["requests"] += 1
    dest["tokens"] += tokens
    if unreported:
        dest["unreported"] += 1
        return
    for key in COUNT_KEYS:
        value = row.get(key)
        if isinstance(value, (int, float)):
            dest[key] += int(value)


def _finalize(rows_by_key, key_name):
    out = [{key_name: name, **counts} for name, counts in rows_by_key.items()]
    out.sort(key=lambda r: (-r["tokens"], -r["requests"]))
    return out


def usage_summary(days=7, path=None, now=None):
    """{"ok": True, "days": [...], "by_model": [...], "by_client": [...],
    "totals": {...}} for the last `days` (7 or 30) calendar days, local time,
    ending today. {"ok": False, "message": ...} when the log can't be read."""
    if days not in (7, 30):
        days = 7
    path = path or USAGE_LOG_PATH

    rows, error = _cached_rows(path)
    if error is not None:
        return {"ok": False, "message": f"aicli usage log not readable: {error}"}
    rows = rows or []

    now = now.astimezone() if now else datetime.now().astimezone()
    today = now.date()
    start = today - timedelta(days=days - 1)
    day_order = [start + timedelta(days=i) for i in range(days)]
    day_counts = {d.isoformat(): {"requests": 0, "tokens": 0} for d in day_order}

    by_model = {}
    by_client = {}
    totals = _empty_counts()

    for at, row in rows:
        day = at.date()
        if day < start or day > today:
            continue
        tokens = _row_tokens(row)
        unreported = _is_unreported(row)
        if unreported:
            tokens = 0

        model = row.get("model") or row.get("tool") or "unknown"
        model = str(model) if str(model).strip() else "unknown"
        client = row.get("client")
        client = str(client).strip() if isinstance(client, str) and str(client).strip() else "unknown"

        _add(by_model.setdefault(model, _empty_counts()), row, tokens, unreported)
        _add(by_client.setdefault(client, _empty_counts()), row, tokens, unreported)
        _add(totals, row, tokens, unreported)

        bucket = day_counts[day.isoformat()]
        bucket["requests"] += 1
        bucket["tokens"] += tokens

    return {
        "ok": True,
        "days": [{"day": d.isoformat(), **day_counts[d.isoformat()]} for d in day_order],
        "by_model": _finalize(by_model, "model"),
        "by_client": _finalize(by_client, "client"),
        "totals": totals,
    }
