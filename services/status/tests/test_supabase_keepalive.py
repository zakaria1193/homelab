#!/usr/bin/env python3
"""The cockpit's side of the Supabase roster.

These run against a stub keepalive.py rather than the real one, so they assert
what this module does with an answer - and, above all, that a ref the roster
does not contain never reaches a subprocess.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import supabase_keepalive  # noqa: E402

STUB = '''#!/usr/bin/env python3
import json, sys, pathlib
calls = pathlib.Path(__file__).parent / "calls.log"
with calls.open("a") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:2] == ["list"]:
    print(json.dumps({"ok": True, "problems": ["bonjourAsso is INACTIVE"], "projects": [
        {"name": "farah", "ref": "fbnuftdjktyyltwuuhtv", "url": "https://x.supabase.co",
         "table": "schools", "paused": False, "paused_since": "", "last_ok": "", "last_detail": ""}]}))
    sys.exit(0)
sys.exit(0)
'''


class CockpitRosterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        script = self.dir / "keepalive.py"
        script.write_text(STUB)
        self._patch("KEEPALIVE_DIR", str(self.dir))
        self._patch("SCRIPT", str(script))

    def _patch(self, attr, value):
        old = getattr(supabase_keepalive, attr)
        setattr(supabase_keepalive, attr, value)
        self.addCleanup(setattr, supabase_keepalive, attr, old)

    def _calls(self):
        path = self.dir / "calls.log"
        return path.read_text().splitlines() if path.exists() else []

    def test_roster_passes_projects_and_problems_through(self):
        data = supabase_keepalive.roster()
        self.assertTrue(data["ok"])
        self.assertEqual(data["projects"][0]["name"], "farah")
        self.assertEqual(data["problems"], ["bonjourAsso is INACTIVE"])

    def test_toggle_runs_pause_for_a_known_ref(self):
        res = supabase_keepalive.set_paused("fbnuftdjktyyltwuuhtv", True)
        self.assertTrue(res["ok"])
        self.assertIn("pause fbnuftdjktyyltwuuhtv", self._calls())

    def test_toggle_runs_resume_when_unpausing(self):
        supabase_keepalive.set_paused("fbnuftdjktyyltwuuhtv", False)
        self.assertIn("resume fbnuftdjktyyltwuuhtv", self._calls())

    def test_an_unknown_ref_never_reaches_the_subprocess(self):
        res = supabase_keepalive.set_paused("; rm -rf /", True)
        self.assertFalse(res["ok"])
        self.assertNotIn("pause ; rm -rf /", self._calls())
        self.assertEqual([c for c in self._calls() if c.startswith(("pause", "resume"))], [])

    def test_a_missing_keepalive_is_reported_not_raised(self):
        self._patch("SCRIPT", str(self.dir / "gone.py"))
        data = supabase_keepalive.roster()
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
