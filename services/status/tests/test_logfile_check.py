#!/usr/bin/env python3
"""Tests for check_logfile in status_server.

Verifies that check_logfile accurately reflects the status of the most recent run
when log files contain multiple historical runs with both success and failure entries.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import status_server  # noqa: E402


class LogfileCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log_file = Path(self.tmp.name) / "test.log"

    def _check(self, **overrides):
        check = {
            "name": "test-service",
            "type": "logfile",
            "path": str(self.log_file),
            "ok_pattern": "run completed successfully",
            "fail_pattern": "run FAILED",
            "max_age_hours": 192,
        }
        check.update(overrides)
        return status_server.check_logfile(check)

    def test_single_success_is_up(self):
        self.log_file.write_text("starting job\nrun completed successfully\n")
        res = self._check()
        self.assertEqual(res["state"], status_server.UP)
        self.assertIn("last run", res["detail"])

    def test_single_failure_is_warn(self):
        self.log_file.write_text("starting job\nrun FAILED\n")
        res = self._check()
        self.assertEqual(res["state"], status_server.WARN)
        self.assertIn("last run reported errors", res["detail"])

    def test_failure_followed_by_later_success_is_up(self):
        # Historical failure in the log, but most recent run succeeded.
        content = (
            "[2026-09-22] starting job\n"
            "[2026-09-22] run FAILED\n"
            "[2026-09-23] starting job\n"
            "[2026-09-23] run FAILED\n"
            "[2026-09-27] starting job\n"
            "[2026-09-27] run completed successfully\n"
        )
        self.log_file.write_text(content)
        res = self._check()
        self.assertEqual(res["state"], status_server.UP)
        self.assertIn("last run", res["detail"])

    def test_success_followed_by_later_failure_is_warn(self):
        # Historical success in the log, but most recent run failed.
        content = (
            "[2026-09-22] starting job\n"
            "[2026-09-22] run completed successfully\n"
            "[2026-09-27] starting job\n"
            "[2026-09-27] run FAILED\n"
        )
        self.log_file.write_text(content)
        res = self._check()
        self.assertEqual(res["state"], status_server.WARN)
        self.assertIn("last run reported errors", res["detail"])

    def test_missing_ok_pattern_is_warn(self):
        self.log_file.write_text("arbitrary lines with no ok pattern\n")
        res = self._check()
        self.assertEqual(res["state"], status_server.WARN)
        self.assertIn("did not report success", res["detail"])

    def test_missing_log_file_is_unknown(self):
        res = self._check(path=str(Path(self.tmp.name) / "nonexistent.log"))
        self.assertEqual(res["state"], status_server.UNKNOWN)
        self.assertIn("log file not found", res["detail"])

    def test_no_path_is_unknown(self):
        res = self._check(path="")
        self.assertEqual(res["state"], status_server.UNKNOWN)
        self.assertIn("no path configured", res["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
