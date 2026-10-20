#!/usr/bin/env python3
"""Tests for usage._compute() against a fake aicli config.

usage.py only shells out to `aicli usage --json` and keeps the cache; the
actual /usage parsing lives in services/AI/aicliAI/aicli.py and is tested
there. See ticket homelab-0013.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import usage  # noqa: E402

AICLI_ROOT = Path(__file__).resolve().parent.parent.parent / "AI" / "aicliAI"
FAKE_CLI = AICLI_ROOT / "tests" / "fake_cli"


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


if __name__ == "__main__":
    unittest.main()
