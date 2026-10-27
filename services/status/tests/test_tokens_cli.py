import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import test_tokens  # noqa: E402
from cockpit import tokens  # noqa: E402


class TestTokensCLI(unittest.TestCase):
    def _run(self, argv):
        with mock.patch.object(sys, "argv", ["test_tokens.py"] + argv), \
             redirect_stdout(io.StringIO()) as out, \
             redirect_stderr(io.StringIO()):
            try:
                rc = test_tokens.main()
            except SystemExit as exc:
                rc = exc.code
        return rc, out.getvalue()

    def test_unknown_env_exits_2(self):
        rc, out = self._run(["--env", "services/does-not-exist/.env"])
        self.assertEqual(rc, 2)
        self.assertIn("matched no TOKEN_DEFS entry", out)

    def test_bad_argument_exits_2(self):
        rc, _ = self._run(["--not-a-real-flag"])
        self.assertEqual(rc, 2)

    def test_strict_exits_1_on_failure(self):
        target = tokens.TOKEN_DEFS[0]
        fail_res = {"id": target["id"], "ok": False, "status": "error", "badge": "Rejected", "message": "nope"}
        with mock.patch.object(test_tokens, "test_token", return_value=fail_res):
            rc, _ = self._run(["--env", target["env_path"], "--strict"])
        self.assertEqual(rc, 1)

    def test_missing_or_offline_alone_exits_0_under_strict(self):
        target = tokens.TOKEN_DEFS[0]
        warn_res = {"id": target["id"], "ok": False, "status": "warn", "badge": "Missing", "message": "Variable not set"}
        with mock.patch.object(test_tokens, "test_token", return_value=warn_res):
            rc, _ = self._run(["--env", target["env_path"], "--strict"])
        self.assertEqual(rc, 0)

    def test_non_strict_never_fails(self):
        target = tokens.TOKEN_DEFS[0]
        fail_res = {"id": target["id"], "ok": False, "status": "error", "badge": "Rejected", "message": "nope"}
        with mock.patch.object(test_tokens, "test_token", return_value=fail_res):
            rc, _ = self._run(["--env", target["env_path"]])
        self.assertEqual(rc, 0)

    def test_env_selects_only_that_files_entries(self):
        target = tokens.TOKEN_DEFS[0]
        same_file_ids = {t["id"] for t in tokens.TOKEN_DEFS if t["env_path"] == target["env_path"]}
        other_ids = {t["id"] for t in tokens.TOKEN_DEFS if t["env_path"] != target["env_path"]}
        self.assertTrue(other_ids, "fixture assumes more than one env_path exists")

        calls = []

        def fake_test_token(token_id):
            calls.append(token_id)
            return {"id": token_id, "ok": True, "status": "active", "badge": "Active", "message": "ok"}

        with mock.patch.object(test_tokens, "test_token", side_effect=fake_test_token):
            self._run(["--env", target["env_path"]])

        self.assertEqual(set(calls), same_file_ids)
        self.assertFalse(set(calls) & other_ids)

    def test_no_env_checks_every_entry_via_test_all(self):
        all_ids = [t["id"] for t in tokens.TOKEN_DEFS]
        fake_results = [{"id": i, "ok": True, "status": "active", "badge": "Active", "message": "ok"} for i in all_ids]
        with mock.patch.object(test_tokens, "test_all", return_value=fake_results) as fake_all:
            rc, _ = self._run([])
        fake_all.assert_called_once()
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
