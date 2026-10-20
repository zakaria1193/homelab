#!/usr/bin/env python3
"""The cockpit's side of the autopilot's hopping-show list.

These run against a stub autopilot.py rather than the real one, so they assert
what this module does with an answer, and that a title the page should never
send does not reach a subprocess.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit import media_autopilot  # noqa: E402

STUB = '''#!/usr/bin/env python3
import json, sys, pathlib
here = pathlib.Path(__file__).parent
with (here / "calls.log").open("a") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\\n")
args = sys.argv[1:]
if args == ["hopping", "list"]:
    print(json.dumps({"hopping": ["Grand Designs", "Modern Family"]}))
elif args == ["maintained", "list"]:
    print(json.dumps({"maintained": ["Adele One Night Only (2011)"]}))
elif args == ["movies"]:
    print(json.dumps({"movies": ["Adele One Night Only (2011)", "Elysium (2013)"]}))
elif args == ["shows"]:
    if (here / "sonarr-down").exists():
        print("sonarr unreachable", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"shows": ["Adults", "Grand Designs", "Modern Family"]}))
elif args[:2] in (["hopping", "add"], ["hopping", "remove"], ["maintained", "add"], ["maintained", "remove"]):
    print(args[1] + "ed " + args[2] if args[1] == "add" else "removed " + args[2])
else:
    sys.exit(2)
'''


class MediaTabTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        (self.dir / "autopilot.py").write_text(STUB)
        for name, value in (("AUTOPILOT_DIR", str(self.dir)), ("SCRIPT", str(self.dir / "autopilot.py"))):
            old = getattr(media_autopilot, name)
            setattr(media_autopilot, name, value)
            self.addCleanup(setattr, media_autopilot, name, old)

    def calls(self):
        log = self.dir / "calls.log"
        return log.read_text().splitlines() if log.exists() else []

    def test_roster_lists_hopping_shows_and_suggestions(self):
        r = media_autopilot.roster()
        self.assertTrue(r["ok"])
        self.assertEqual(r["hopping"], ["Grand Designs", "Modern Family"])
        self.assertEqual(r["shows"], ["Adults", "Grand Designs", "Modern Family"])

    def test_roster_carries_the_maintained_movies_and_suggestions(self):
        r = media_autopilot.roster()
        self.assertEqual(r["maintained"], ["Adele One Night Only (2011)"])
        self.assertEqual(r["movies"], ["Adele One Night Only (2011)", "Elysium (2013)"])

    def test_maintained_edits_go_to_the_maintained_list_only(self):
        self.assertTrue(media_autopilot.edit("Elysium (2013)", True, kind="maintained")["ok"])
        self.assertEqual(self.calls(), ["maintained add Elysium (2013)"])

    def test_unknown_list_never_runs_anything(self):
        self.assertFalse(media_autopilot.edit("x", True, kind="rm -rf")["ok"])
        self.assertEqual(self.calls(), [])

    def test_roster_survives_sonarr_being_down(self):
        (self.dir / "sonarr-down").write_text("")
        r = media_autopilot.roster()
        self.assertTrue(r["ok"])
        self.assertEqual(r["hopping"], ["Grand Designs", "Modern Family"])
        self.assertEqual(r["shows"], [])

    def test_add_and_remove_pass_the_title_as_one_argument(self):
        self.assertTrue(media_autopilot.edit("  Little House on the Prairie ", True)["ok"])
        self.assertTrue(media_autopilot.edit("Modern Family", False)["ok"])
        self.assertEqual(self.calls(), ["hopping add Little House on the Prairie",
                                        "hopping remove Modern Family"])

    def test_empty_or_multiline_titles_never_run_anything(self):
        for bad in ("", "   ", "a\nb", "x" * 201):
            self.assertFalse(media_autopilot.edit(bad, True)["ok"])
        self.assertEqual(self.calls(), [])

    def test_missing_script_is_reported_not_raised(self):
        (self.dir / "autopilot.py").unlink()
        self.assertFalse(media_autopilot.roster()["ok"])
        self.assertFalse(media_autopilot.edit("Adults", True)["ok"])

    def test_page_posts_to_the_api_it_serves(self):
        self.assertIn("'/api/media/' + kind", media_autopilot.MEDIA_PAGE)
        self.assertIn("/api/media'", media_autopilot.MEDIA_PAGE)


if __name__ == "__main__":
    unittest.main()
