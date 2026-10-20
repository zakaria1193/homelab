#!/usr/bin/env python3
"""services/AI/Makefile's test-tokens-notify step, run through `make` itself.

Points ROOT at a throwaway tree with a stub services/status/Makefile (so the
token check itself is fake and never touches the network) and SLACK_NOTIFY at
a stub script that records its arguments. No real upgrade or verify runs.
"""

import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

AI_DIR = Path(__file__).resolve().parent.parent

STUB_STATUS_MAKEFILE_FAIL = """\
.PHONY: test-tokens
test-tokens:
	@echo " [FAIL]  stub_token      [Rejected] stub credential rejected"
	@exit 1
"""

STUB_STATUS_MAKEFILE_OK = """\
.PHONY: test-tokens
test-tokens:
	@echo " [PASS]  stub_token      [Active]   stub credential ok"
"""

STUB_SLACK_NOTIFY = """\
#!/usr/bin/env python3
import pathlib
import sys

calls = pathlib.Path(__file__).parent / "calls.log"
with calls.open("a") as fh:
    fh.write(repr(sys.argv[1:]) + "\\n")
sys.exit(0)
"""


def _write_tree(tmp: Path, status_makefile_body: str) -> tuple[Path, Path]:
    status_dir = tmp / "services" / "status"
    status_dir.mkdir(parents=True)
    (status_dir / "Makefile").write_text(status_makefile_body)

    slack_notify = tmp / "slackbot-notify.sh"
    slack_notify.write_text(STUB_SLACK_NOTIFY)
    slack_notify.chmod(slack_notify.stat().st_mode | stat.S_IEXEC)

    return status_dir, slack_notify


def _run_make(tmp: Path, slack_notify: Path, verify_status: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "make", "--no-print-directory", "-C", str(AI_DIR), "test-tokens-notify",
            f"ROOT={tmp}",
            f"SLACK_NOTIFY={slack_notify}",
            f"VERIFY_STATUS={verify_status}",
        ],
        capture_output=True, text=True,
    )


class TestTokensNotify(unittest.TestCase):
    def test_failing_check_notifies_slack_once_and_exit_follows_verify(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _, slack_notify = _write_tree(tmp, STUB_STATUS_MAKEFILE_FAIL)

            result = _run_make(tmp, slack_notify, verify_status=1)

            calls_log = tmp / "calls.log"
            self.assertTrue(calls_log.exists(), result.stdout + result.stderr)
            calls = calls_log.read_text().splitlines()
            self.assertEqual(len(calls), 1, calls)
            self.assertIn("Token check failed", calls[0])
            self.assertIn("error", calls[0])
            self.assertIn("stub_token", calls[0])

            # The step's own exit follows the VERIFY_STATUS it was given, not
            # the token check's result. (GNU Make itself only ever reports a
            # recipe failure as exit 2, never the recipe's own exit code, so
            # "follows verify" means success/failure, not the exact number.)
            self.assertNotEqual(result.returncode, 0)

    def test_passing_check_does_not_notify_and_exit_follows_verify(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _, slack_notify = _write_tree(tmp, STUB_STATUS_MAKEFILE_OK)

            result = _run_make(tmp, slack_notify, verify_status=0)

            calls_log = tmp / "calls.log"
            self.assertFalse(calls_log.exists(), "slack must not be called when the token check passes")
            self.assertEqual(result.returncode, 0)

    def test_failing_check_but_verify_ok_still_exits_0(self):
        """Owner's answer to Q2: the weekly run's exit code is verify's,
        whatever the token check says."""
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _, slack_notify = _write_tree(tmp, STUB_STATUS_MAKEFILE_FAIL)

            result = _run_make(tmp, slack_notify, verify_status=0)

            calls_log = tmp / "calls.log"
            self.assertTrue(calls_log.exists())
            self.assertEqual(len(calls_log.read_text().splitlines()), 1)
            self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
