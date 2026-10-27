#!/usr/bin/env python3
"""Tests for usage._compute() against a fake aicli config.

usage.py only shells out to `aicli usage --json` and keeps the cache; the
actual /usage parsing lives in aicli's own repo (usage.AICLI_DIR) and is
tested there. See ticket homelab-0013.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit import usage  # noqa: E402

FAKE_CLI = Path(usage.AICLI_DIR) / "tests" / "fake_cli"


def _write_config(tmp_dir):
    # usage._compute() only needs each tool's `bin` - no model names here, so
    # this test config stays clear of criterion 1 ("aicli.toml is the only
    # place that names a model").
    cfg = f"""usage_timeout = 5

[claude]
bin = "{FAKE_CLI / 'fake-claude'}"

[agy]
bin = "{FAKE_CLI / 'fake-agy'}"
"""
    path = Path(tmp_dir) / "aicli.toml"
    path.write_text(cfg)
    return path


@unittest.skipUnless(os.path.isfile(usage.AICLI), f"aicli not checked out at {usage.AICLI_DIR}")
class ComputeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        config_path = _write_config(self.tmp.name)
        os.environ["AICLI_CONFIG"] = str(config_path)
        self.addCleanup(lambda: os.environ.pop("AICLI_CONFIG", None))

    def test_compute_matches_aicli_usage_shape(self):
        data = usage._compute()
        self.assertEqual(
            data["claude"],
            {
                "state": "ok", "detail": "",
                "bars": {
                    "five_hour": {"pct": 76, "reset": "Aug 25, 1:09am (Europe/Paris)"},
                    "weekly": {"pct": 6, "reset": "Aug 31, 6:59pm (Europe/Paris)"},
                },
            },
        )
        self.assertEqual(data["agy"]["state"], "ok")

    def test_compute_reports_unknown_when_config_missing(self):
        os.environ["AICLI_CONFIG"] = "/nonexistent/aicli.toml"
        data = usage._compute()
        self.assertEqual(data["claude"]["state"], usage.UNKNOWN)
        self.assertEqual(data["agy"]["state"], usage.UNKNOWN)
        self.assertEqual(data["claude"]["detail"], "aicli usage failed")


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "state", "quota-history.jsonl")

    @staticmethod
    def reading(week, agy_ok=True):
        return {
            "claude": {"state": "ok", "bars": {"weekly": {"pct": week, "reset": "x"}}},
            "agy": {"state": "ok" if agy_ok else "unknown", "bars": {},
                    "groups": {"Gemini Models": {"weekly": {"pct": 30}}}} ,
        }

    def test_keeps_each_meter_and_adds_up_rises_across_a_reset(self):
        for i, week in enumerate((90, 100, 0, 12)):
            usage.record(self.reading(week, agy_ok=i != 1), path=self.path, now=1000 + 180 * i)
        usage.record({"claude": {"state": "unknown", "bars": {}}}, path=self.path, now=2000)
        samples = usage.history(0, path=self.path)
        self.assertEqual([s["meters"]["claude/weekly"] for s in samples], [90, 100, 0, 12])
        self.assertNotIn("agy/Gemini Models/weekly", samples[1]["meters"])
        self.assertEqual(samples[0]["meters"]["agy/Gemini Models/weekly"], 30)
        self.assertEqual(usage.growth(samples, "claude/weekly"), 22)
        self.assertIsNone(usage.growth(samples, "claude/five_hour"))
        self.assertEqual(len(usage.history(1000 + 180 * 2, path=self.path)), 2)

    def test_old_readings_are_dropped_once_the_file_grows(self):
        old_trim = usage.HISTORY_TRIM_AT
        usage.HISTORY_TRIM_AT = 5
        self.addCleanup(lambda: setattr(usage, "HISTORY_TRIM_AT", old_trim))
        for i in range(6):
            usage.record(self.reading(1), path=self.path, now=i * usage.HISTORY_KEEP / 2)
        with open(self.path) as f:
            self.assertLessEqual(len(f.read().splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
