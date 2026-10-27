#!/usr/bin/env python3
"""The cockpit's side of the autopilot's hopping-show and maintained-movie lists.

These run against a stub autopilot.py rather than the real one, so they assert
what this module does with an answer, and that an id or title the page should
never send does not reach a subprocess.
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
    print(json.dumps({"hopping": [
        {"title": "Grand Designs", "tvdbId": 1, "matched": True},
        {"title": "Modern Family", "tvdbId": 2, "matched": False},
    ]}))
elif args == ["maintained", "list"]:
    print(json.dumps({"maintained": [
        {"title": "Adele One Night Only (2011)", "tmdbId": 10, "matched": True},
    ]}))
elif args == ["movies"]:
    print(json.dumps({"movies": [
        {"title": "Adele One Night Only (2011)", "tmdbId": 10},
        {"title": "Elysium (2013)", "tmdbId": 11},
    ]}))
elif args == ["shows"]:
    if (here / "sonarr-down").exists():
        print("sonarr unreachable", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"shows": [
        {"title": "Adults", "tvdbId": 3},
        {"title": "Grand Designs", "tvdbId": 1},
        {"title": "Modern Family", "tvdbId": 2},
    ]}))
elif args[:2] == ["hopping", "add"]:
    print("added " + args[2])
elif args[:2] == ["hopping", "remove"]:
    print("removed " + args[2])
elif args[:2] == ["maintained", "add"]:
    print("added " + args[2])
elif args[:2] == ["maintained", "remove"]:
    print("removed " + args[2])
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

    def test_roster_carries_matched_and_the_show_picker(self):
        r = media_autopilot.roster()
        self.assertTrue(r["ok"])
        self.assertEqual(r["hopping"], [
            {"title": "Grand Designs", "tvdbId": 1, "matched": True},
            {"title": "Modern Family", "tvdbId": 2, "matched": False},
        ])
        self.assertEqual(r["shows"], [
            {"title": "Adults", "tvdbId": 3},
            {"title": "Grand Designs", "tvdbId": 1},
            {"title": "Modern Family", "tvdbId": 2},
        ])
        self.assertEqual(r["shows_message"], "")

    def test_roster_carries_the_maintained_movies_and_the_movie_picker(self):
        r = media_autopilot.roster()
        self.assertEqual(r["maintained"], [
            {"title": "Adele One Night Only (2011)", "tmdbId": 10, "matched": True},
        ])
        self.assertEqual(r["movies"], [
            {"title": "Adele One Night Only (2011)", "tmdbId": 10},
            {"title": "Elysium (2013)", "tmdbId": 11},
        ])
        self.assertEqual(r["movies_message"], "")

    def test_add_sends_the_id_as_one_argument(self):
        self.assertTrue(media_autopilot.edit(11, True, kind="maintained")["ok"])
        self.assertEqual(self.calls(), ["maintained add 11"])

    def test_add_refuses_a_missing_or_non_integer_id_without_running_anything(self):
        for bad in (None, "", "Elysium (2013)", 3.5, True):
            self.assertFalse(media_autopilot.edit(bad, True, kind="maintained")["ok"])
        self.assertEqual(self.calls(), [])

    def test_add_refuses_a_non_positive_id_without_running_anything(self):
        for bad in (0, -1):
            self.assertFalse(media_autopilot.edit(bad, True, kind="hopping")["ok"])
        self.assertEqual(self.calls(), [])

    def test_unknown_list_never_runs_anything(self):
        self.assertFalse(media_autopilot.edit(1, True, kind="rm -rf")["ok"])
        self.assertEqual(self.calls(), [])

    def test_roster_survives_sonarr_being_down(self):
        (self.dir / "sonarr-down").write_text("")
        r = media_autopilot.roster()
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["hopping"]), 2)
        self.assertEqual(r["shows"], [])
        self.assertTrue(r["shows_message"])

    def test_remove_works_by_id(self):
        self.assertTrue(media_autopilot.edit(2, False, kind="hopping")["ok"])
        self.assertEqual(self.calls(), ["hopping remove 2"])

    def test_remove_works_by_title_for_a_title_only_entry(self):
        self.assertTrue(media_autopilot.edit("Little House on the Prairie", False, kind="hopping")["ok"])
        self.assertEqual(self.calls(), ["hopping remove Little House on the Prairie"])

    def test_remove_refuses_an_empty_or_multiline_title_without_running_anything(self):
        for bad in ("", "   ", "a\nb", "x" * 201):
            self.assertFalse(media_autopilot.edit(bad, False, kind="hopping")["ok"])
        self.assertEqual(self.calls(), [])

    def test_missing_script_is_reported_not_raised(self):
        (self.dir / "autopilot.py").unlink()
        self.assertFalse(media_autopilot.roster()["ok"])
        self.assertFalse(media_autopilot.edit(1, True)["ok"])

    def test_page_posts_to_the_api_it_serves(self):
        static_dir = Path(__file__).resolve().parent.parent / "cockpit" / "static"
        media_js = (static_dir / "media.js").read_text()
        self.assertIn("'/api/media/' + kind", media_js)
        self.assertIn("/api/media'", media_js)


if __name__ == "__main__":
    unittest.main()
