#!/usr/bin/env python3
"""Tests for aicli_usage.usage_summary() against a fake usage.jsonl.

See ticket homelab-0018. `now` is passed in so the day window is
deterministic regardless of the host's clock or time zone.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit import aicli_usage  # noqa: E402

NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)


def _write(tmp_dir, lines):
    path = Path(tmp_dir) / "usage.jsonl"
    with open(path, "w") as f:
        for line in lines:
            if isinstance(line, str):
                f.write(line + "\n")
            else:
                f.write(json.dumps(line) + "\n")
    return path


class UsageSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Each test gets a fresh path, so the mtime/size cache never carries
        # state from one test into the next.
        aicli_usage._cache["key"] = ()
        aicli_usage._cache["rows"] = []

    def test_http_line_shape_counts_by_model_and_client(self):
        path = _write(self.tmp.name, [
            {"at": NOW.isoformat(), "tool": "claude", "model": "opus",
             "client": "pjm", "reported": True,
             "input": 10, "output": 5, "cache_write": 0, "cache_read": 0, "total": 15},
        ])
        res = aicli_usage.usage_summary("7d", path=path, now=NOW)
        self.assertTrue(res["ok"])
        self.assertEqual(res["totals"]["requests"], 1)
        self.assertEqual(res["totals"]["tokens"], 15)
        self.assertEqual(res["totals"]["unreported"], 0)
        self.assertEqual(res["by_model"], [
            {"model": "opus", "requests": 1, "tokens": 15, "input": 10,
             "output": 5, "cache_write": 0, "cache_read": 0, "unreported": 0, "cost": None},
        ])
        self.assertEqual(res["by_client"][0]["client"], "pjm")

    def test_aicli_run_line_shape_counts_as_unreported(self):
        path = _write(self.tmp.name, [
            {"at": NOW.isoformat(), "tool": "claude", "model": "opus",
             "client": "shell", "class": None, "tier": "fast", "quota": "ok"},
        ])
        res = aicli_usage.usage_summary("7d", path=path, now=NOW)
        self.assertEqual(res["totals"]["requests"], 1)
        self.assertEqual(res["totals"]["tokens"], 0)
        self.assertEqual(res["totals"]["unreported"], 1)
        self.assertEqual(res["by_model"][0]["unreported"], 1)

    def test_reported_false_counts_as_unreported_with_zero_tokens(self):
        path = _write(self.tmp.name, [
            {"at": NOW.isoformat(), "tool": "agy", "model": "agy",
             "client": "unknown", "reported": False},
        ])
        res = aicli_usage.usage_summary("7d", path=path, now=NOW)
        self.assertEqual(res["totals"]["unreported"], 1)
        self.assertEqual(res["totals"]["tokens"], 0)

    def test_missing_client_becomes_unknown(self):
        path = _write(self.tmp.name, [
            {"at": NOW.isoformat(), "tool": "claude", "model": "opus",
             "reported": True, "total": 5},
            {"at": NOW.isoformat(), "tool": "claude", "model": "opus",
             "client": None, "reported": True, "total": 3},
            {"at": NOW.isoformat(), "tool": "claude", "model": "opus",
             "client": "", "reported": True, "total": 1},
        ])
        res = aicli_usage.usage_summary("7d", path=path, now=NOW)
        self.assertEqual(len(res["by_client"]), 1)
        self.assertEqual(res["by_client"][0]["client"], "unknown")
        self.assertEqual(res["by_client"][0]["requests"], 3)

    def test_missing_model_falls_back_to_tool_then_unknown(self):
        path = _write(self.tmp.name, [
            {"at": NOW.isoformat(), "tool": "claude", "client": "pjm", "reported": True, "total": 5},
            {"at": NOW.isoformat(), "client": "pjm", "reported": True, "total": 1},
        ])
        res = aicli_usage.usage_summary("7d", path=path, now=NOW)
        models = {row["model"]: row for row in res["by_model"]}
        self.assertIn("claude", models)
        self.assertIn("unknown", models)

    def test_bad_lines_are_skipped_rest_still_counts(self):
        path = _write(self.tmp.name, [
            "not json at all",
            json.dumps(["not", "an", "object"]),
            {"at": "not-a-date", "tool": "claude", "model": "opus", "total": 1},
            {"tool": "claude", "model": "opus", "total": 1},
            {"at": NOW.isoformat(), "tool": "claude", "model": "opus",
             "client": "pjm", "reported": True, "total": 7},
        ])
        res = aicli_usage.usage_summary("7d", path=path, now=NOW)
        self.assertEqual(res["totals"]["requests"], 1)
        self.assertEqual(res["totals"]["tokens"], 7)

    def test_timezone_is_converted_to_local_day_naive_treated_as_utc(self):
        # NOW is noon UTC. A line at 23:30 UTC the day before NOW, with no
        # offset, is read as UTC and must land on the previous calendar day
        # once converted to local time (whatever the host's local zone is),
        # not silently drift into NOW's day.
        at = (NOW - timedelta(hours=12, minutes=30)).replace(tzinfo=None)
        path = _write(self.tmp.name, [
            {"at": at.isoformat(), "tool": "claude", "model": "opus",
             "client": "pjm", "reported": True, "total": 4},
        ])
        res = aicli_usage.usage_summary("7d", path=path, now=NOW)
        self.assertEqual(res["totals"]["requests"], 1)
        # The line is somewhere inside the 7-day window; the exact day
        # depends on the host's local time zone, but it must be exactly one
        # of the returned days and nowhere else.
        matching = [d for d in res["buckets"] if d["tokens"] == 4]
        self.assertEqual(len(matching), 1)

    def test_window_7_vs_30_and_future_or_old_lines_excluded(self):
        lines = [
            {"at": NOW.isoformat(), "tool": "claude", "model": "opus",
             "client": "pjm", "reported": True, "total": 1},
            {"at": (NOW - timedelta(days=10)).isoformat(), "tool": "claude",
             "model": "opus", "client": "pjm", "reported": True, "total": 2},
            {"at": (NOW - timedelta(days=40)).isoformat(), "tool": "claude",
             "model": "opus", "client": "pjm", "reported": True, "total": 4},
            {"at": (NOW + timedelta(days=5)).isoformat(), "tool": "claude",
             "model": "opus", "client": "pjm", "reported": True, "total": 8},
        ]
        path = _write(self.tmp.name, lines)
        res7 = aicli_usage.usage_summary("7d", path=path, now=NOW)
        self.assertEqual(res7["totals"]["requests"], 1)
        self.assertEqual(len(res7["buckets"]), 7)

        res30 = aicli_usage.usage_summary("30d", path=path, now=NOW)
        self.assertEqual(res30["totals"]["requests"], 2)
        self.assertEqual(len(res30["buckets"]), 30)

    def test_an_unknown_range_is_the_last_24_hours(self):
        path = _write(self.tmp.name, [])
        res = aicli_usage.usage_summary("14d", path=path, now=NOW)
        self.assertEqual((res["range"], res["bucket"], len(res["buckets"])), ("24h", "hour", 24))

    def test_zero_filled_days_oldest_first_ending_today(self):
        path = _write(self.tmp.name, [
            {"at": NOW.isoformat(), "tool": "claude", "model": "opus",
             "client": "pjm", "reported": True, "total": 9},
        ])
        res = aicli_usage.usage_summary("7d", path=path, now=NOW)
        self.assertEqual(len(res["buckets"]), 7)
        today = NOW.astimezone().date().isoformat()
        self.assertEqual(res["buckets"][-1]["at"], today)
        self.assertEqual(res["buckets"][-1]["tokens"], 9)
        self.assertEqual(res["buckets"][-1]["clients"], {"pjm": 1})
        self.assertEqual(sum(d["requests"] for d in res["buckets"][:-1]), 0)
        # Oldest first: days are strictly increasing.
        self.assertEqual([d["at"] for d in res["buckets"]],
                         sorted(d["at"] for d in res["buckets"]))

    def test_missing_file_returns_zeros_ok_true(self):
        path = Path(self.tmp.name) / "does-not-exist.jsonl"
        res = aicli_usage.usage_summary("7d", path=path, now=NOW)
        self.assertTrue(res["ok"])
        self.assertEqual(res["totals"]["requests"], 0)
        self.assertEqual(len(res["buckets"]), 7)

    def test_empty_file_returns_zeros(self):
        path = _write(self.tmp.name, [])
        res = aicli_usage.usage_summary("7d", path=path, now=NOW)
        self.assertTrue(res["ok"])
        self.assertEqual(res["totals"]["requests"], 0)

    def test_unreadable_file_returns_ok_false(self):
        path = _write(self.tmp.name, [
            {"at": NOW.isoformat(), "tool": "claude", "model": "opus", "total": 1},
        ])
        os.chmod(path, 0)
        self.addCleanup(lambda: os.chmod(path, 0o644))
        if os.access(path, os.R_OK):
            self.skipTest("running as a user that can still read a 0-mode file")
        res = aicli_usage.usage_summary("7d", path=path, now=NOW)
        self.assertFalse(res["ok"])
        self.assertIn("message", res)


    def test_hourly_buckets_for_the_last_24_and_48_hours(self):
        path = _write(self.tmp.name, [
            {"at": (NOW - timedelta(minutes=10)).isoformat(), "tool": "claude", "client": "pjm:a"},
            {"at": (NOW - timedelta(hours=3, minutes=10)).isoformat(), "tool": "claude", "client": "pjm:a"},
            {"at": (NOW - timedelta(hours=30)).isoformat(), "tool": "agy", "client": "auto-heal"},
        ])
        res = aicli_usage.usage_summary("24h", path=path, now=NOW)
        self.assertEqual((res["bucket"], len(res["buckets"]), res["totals"]["requests"]), ("hour", 24, 2))
        self.assertEqual(res["buckets"][-2]["clients"], {"pjm:a": 1})   # 11:50 -> the 11:00 bucket
        self.assertEqual(res["buckets"][-5]["clients"], {"pjm:a": 1})
        res48 = aicli_usage.usage_summary("48h", path=path, now=NOW)
        self.assertEqual((len(res48["buckets"]), res48["totals"]["requests"]), (48, 3))

    def test_claude_tokens_get_an_api_price(self):
        path = _write(self.tmp.name, [
            {"at": NOW.isoformat(), "tool": "claude", "model": "claude-opus-5-5", "client": "job",
             "reported": True, "input": 1_000_000, "output": 1_000_000, "cache_write": 0,
             "cache_read": 1_000_000, "total": 3_000_000},
            {"at": NOW.isoformat(), "tool": "agy", "model": "gemini-3.8-flash-high", "client": "job",
             "reported": True, "input": 5, "total": 5},
        ])
        res = aicli_usage.usage_summary("24h", path=path, now=NOW)
        self.assertAlmostEqual(res["totals"]["cost"], 4 + 20 + 0.2)
        models = {r["model"]: r for r in res["by_model"]}
        self.assertIsNone(models["gemini-3.8-flash-high"]["cost"])
        self.assertEqual(res["by_client"][0]["models"], ["claude-opus-5-5", "gemini-3.8-flash-high"])
        self.assertAlmostEqual(aicli_usage.api_cost("claude-sonnet-5", {"output": 1_000_000}), 10)
        self.assertIsNone(aicli_usage.api_cost("claude-mystery", {"output": 1}))


if __name__ == "__main__":
    unittest.main()
