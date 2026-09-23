#!/usr/bin/env python3
"""What the weekly ping does, without a network or a real Supabase project.

Every test redirects the module's three files (state, pause list, log) into a
temp directory and replaces `ping` with a recorder, so the assertions are about
the decisions - who gets pinged, what the run reports - and nothing else.
"""

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import keepalive  # noqa: E402

BONJOUR = "bonjourAsso|https://fdxvhxlbqjiqdonadnha.supabase.co|anon-key-1|associations"
FARAH = "farah|https://fbnuftdjktyyltwuuhtv.supabase.co|anon-key-2|schools"
BONJOUR_REF = "fdxvhxlbqjiqdonadnha"
FARAH_REF = "fbnuftdjktyyltwuuhtv"


class KeepaliveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for attr, name in (("STATE_FILE", "state.json"),
                           ("PAUSED_FILE", "paused.json"),
                           ("LOG_FILE", "keepalive.log"),
                           ("ENV_FILE", ".env")):
            self._patch(keepalive, attr, root / name)

        self.pinged = []
        self._patch(keepalive, "ping", lambda p: (self.pinged.append(p.ref), (True, "HTTP 200"))[1])
        self._env("SUPABASE_PROJECTS", f"{BONJOUR};{FARAH}")
        self._env("SUPABASE_ACCESS_TOKEN", "")
        self._env("SUPABASE_KEEPALIVE_TABLE", "")

    def _patch(self, obj, attr, value):
        old = getattr(obj, attr)
        setattr(obj, attr, value)
        self.addCleanup(setattr, obj, attr, old)

    def _env(self, key, value):
        old = os.environ.get(key)
        os.environ[key] = value
        self.addCleanup(lambda: os.environ.__setitem__(key, old) if old is not None
                        else os.environ.pop(key, None))

    def _ping(self, **kw):
        args = argparse.Namespace(if_stale=False, max_age_days=7, notify="never", **kw)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = keepalive.command_ping(args)
        return code, out.getvalue()

    def _pause(self, which):
        with contextlib.redirect_stdout(io.StringIO()):
            return keepalive.command_pause(argparse.Namespace(project=which))

    def _resume(self, which):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return keepalive.command_resume(argparse.Namespace(project=which))

    # ---------------------------------------------------------------- pausing

    def test_pings_everything_by_default(self):
        code, output = self._ping()
        self.assertEqual(code, 0)
        self.assertCountEqual(self.pinged, [BONJOUR_REF, FARAH_REF])
        self.assertIn(keepalive.OK_LINE, output)

    def test_paused_project_is_skipped_but_the_run_still_succeeds(self):
        self.assertEqual(self._pause("bonjourAsso"), 0)
        code, output = self._ping()
        self.assertEqual(code, 0)
        self.assertEqual(self.pinged, [FARAH_REF], "a paused project must not be pinged")
        self.assertIn("[skip] bonjourAsso", output)
        self.assertIn("1 pinged, 1 paused", output)

    def test_pause_accepts_a_ref_as_well_as_a_name(self):
        self.assertEqual(self._pause(BONJOUR_REF), 0)
        self.assertIn(BONJOUR_REF, keepalive.read_paused())

    def test_pause_refuses_a_project_it_does_not_know(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self._pause("not-a-project"), 1)
        self.assertEqual(keepalive.read_paused(), {})

    def test_resume_puts_it_back(self):
        self._pause("bonjourAsso")
        self.assertEqual(self._resume("bonjourAsso"), 0)
        self.assertEqual(keepalive.read_paused(), {})
        self._ping()
        self.assertCountEqual(self.pinged, [BONJOUR_REF, FARAH_REF])

    def test_resume_works_after_the_project_left_the_env(self):
        """Pausing then dropping it from .env must not strand the pause file."""
        self._pause("bonjourAsso")
        self._env("SUPABASE_PROJECTS", FARAH)
        self.assertEqual(self._resume("bonjourAsso"), 0)
        self.assertEqual(keepalive.read_paused(), {})

    def test_resume_of_something_not_paused_fails_cleanly(self):
        self.assertEqual(self._resume("farah"), 1)

    def test_everything_paused_is_a_good_run_not_a_failure(self):
        self._pause("bonjourAsso")
        self._pause("farah")
        code, output = self._ping()
        self.assertEqual(code, 0, "an all-paused run is obedience, not an incident")
        self.assertEqual(self.pinged, [])
        self.assertIn("0 pinged, 2 paused", output)
        self.assertNotIn(keepalive.FAIL_LINE, output)
        self.assertTrue(keepalive.read_state().get("last_ok_run"),
                        "the card must not age out while the job does as it is told")

    def test_no_projects_at_all_is_still_a_failure(self):
        self._env("SUPABASE_PROJECTS", "")
        code, output = self._ping()
        self.assertEqual(code, 2)
        self.assertIn(keepalive.FAIL_LINE, output)

    # ------------------------------------------------------------ the cockpit

    def test_list_json_reports_pause_state_and_leaks_no_keys(self):
        self._pause("bonjourAsso")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            keepalive.command_list(argparse.Namespace(json=True))
        payload = json.loads(out.getvalue())
        by_name = {p["name"]: p for p in payload["projects"]}
        self.assertTrue(by_name["bonjourAsso"]["paused"])
        self.assertFalse(by_name["farah"]["paused"])
        self.assertTrue(by_name["bonjourAsso"]["paused_since"])
        self.assertNotIn("anon-key-1", out.getvalue(), "keys must not cross to the browser")
        self.assertNotIn("key", set(by_name["farah"]))

    def test_failures_still_report(self):
        self._patch(keepalive, "ping", lambda p: (False, "HTTP 503"))
        code, output = self._ping()
        self.assertEqual(code, 1)
        self.assertIn(keepalive.FAIL_LINE, output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
