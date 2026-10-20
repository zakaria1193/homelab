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
import aicli_usage  # noqa: E402

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
        res = aicli_usage.usage_summary(days=7, path=path, now=NOW)
        self.assertTrue(res["ok"])
        self.assertEqual(res["totals"]["requests"], 1)
        self.assertEqual(res["totals"]["tokens"], 15)
        self.assertEqual(res["totals"]["unreported"], 0)
        self.assertEqual(res["by_model"], [
            {"model": "opus", "requests": 1, "tokens": 15, "input": 10,
             "output": 5, "cache_write": 0, "cache_read": 0, "unreported": 0},
        ])
        self.assertEqual(res["by_client"][0]["client"], "pjm")

    def test_aicli_run_line_shape_counts_as_unreported(self):
        path = _write(self.tmp.name, [
            {"at": NOW.isoformat(), "tool": "claude", "model": "opus",
             "client": "shell", "class": None, "tier": "fast", "quota": "ok"},
        ])
        res = aicli_usage.usage_summary(days=7, path=path, now=NOW)
        self.assertEqual(res["totals"]["requests"], 1)
        self.assertEqual(res["totals"]["tokens"], 0)
        self.assertEqual(res["totals"]["unreported"], 1)
        self.assertEqual(res["by_model"][0]["unreported"], 1)

    def test_reported_false_counts_as_unreported_with_zero_tokens(self):
        path = _write(self.tmp.name, [
            {"at": NOW.isoformat(), "tool": "agy", "model": "agy",
             "client": "unknown", "reported": False},
        ])
        res = aicli_usage.usage_summary(days=7, path=path, now=NOW)
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
        res = aicli_usage.usage_summary(days=7, path=path, now=NOW)
        self.assertEqual(len(res["by_client"]), 1)
        self.assertEqual(res["by_client"][0]["client"], "unknown")
        self.assertEqual(res["by_client"][0]["requests"], 3)

    def test_missing_model_falls_back_to_tool_then_unknown(self):
        path = _write(self.tmp.name, [
            {"at": NOW.isoformat(), "tool": "claude", "client": "pjm", "reported": True, "total": 5},
            {"at": NOW.isoformat(), "client": "pjm", "reported": True, "total": 1},
        ])
        res = aicli_usage.usage_summary(days=7, path=path, now=NOW)
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
        res = aicli_usage.usage_summary(days=7, path=path, now=NOW)
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
        res = aicli_usage.usage_summary(days=7, path=path, now=NOW)
        self.assertEqual(res["totals"]["requests"], 1)
        # The line is somewhere inside the 7-day window; the exact day
        # depends on the host's local time zone, but it must be exactly one
        # of the returned days and nowhere else.
        matching = [d for d in res["days"] if d["tokens"] == 4]
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
        res7 = aicli_usage.usage_summary(days=7, path=path, now=NOW)
        self.assertEqual(res7["totals"]["requests"], 1)
        self.assertEqual(len(res7["days"]), 7)

        res30 = aicli_usage.usage_summary(days=30, path=path, now=NOW)
        self.assertEqual(res30["totals"]["requests"], 2)
        self.assertEqual(len(res30["days"]), 30)

    def test_days_other_than_7_or_30_defaults_to_7(self):
        path = _write(self.tmp.name, [])
        res = aicli_usage.usage_summary(days=14, path=path, now=NOW)
        self.assertEqual(len(res["days"]), 7)

    def test_zero_filled_days_oldest_first_ending_today(self):
        path = _write(self.tmp.name, [
            {"at": NOW.isoformat(), "tool": "claude", "model": "opus",
             "client": "pjm", "reported": True, "total": 9},
        ])
        res = aicli_usage.usage_summary(days=7, path=path, now=NOW)
        self.assertEqual(len(res["days"]), 7)
        today = NOW.astimezone().date().isoformat()
        self.assertEqual(res["days"][-1]["day"], today)
        self.assertEqual(res["days"][-1]["tokens"], 9)
        self.assertEqual(sum(d["requests"] for d in res["days"][:-1]), 0)
        # Oldest first: days are strictly increasing.
        self.assertEqual([d["day"] for d in res["days"]],
                         sorted(d["day"] for d in res["days"]))

    def test_missing_file_returns_zeros_ok_true(self):
        path = Path(self.tmp.name) / "does-not-exist.jsonl"
        res = aicli_usage.usage_summary(days=7, path=path, now=NOW)
        self.assertTrue(res["ok"])
        self.assertEqual(res["totals"]["requests"], 0)
        self.assertEqual(len(res["days"]), 7)

    def test_empty_file_returns_zeros(self):
        path = _write(self.tmp.name, [])
        res = aicli_usage.usage_summary(days=7, path=path, now=NOW)
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
        res = aicli_usage.usage_summary(days=7, path=path, now=NOW)
        self.assertFalse(res["ok"])
        self.assertIn("message", res)


if __name__ == "__main__":
    unittest.main()
