import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cockpit import build  # noqa: E402
from cockpit.pages.main import PAGE  # noqa: E402


class TestBuild(unittest.TestCase):
    def test_info_is_fixed_at_import(self):
        b = build.info()
        self.assertEqual(b["id"], "%s-%d" % (b["commit"], b["started"]))
        self.assertEqual(build.info(), b)

    def test_import_runs_no_subprocess(self):
        import importlib
        from unittest import mock
        with mock.patch("subprocess.run", side_effect=AssertionError("ran at import")):
            importlib.reload(build)
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="abc1234\n")
            self.assertEqual(build.info()["commit"], "abc1234")
            build.info()
            run.assert_called_once()

    def test_page_has_a_stamp_slot_and_the_stale_hint(self):
        self.assertIn('id="build"', PAGE)
        js = (ROOT / "cockpit" / "static" / "main.js").read_text()
        self.assertIn("renderBuild(data.build)", js)
        self.assertIn("new version available, reload", js)


if __name__ == "__main__":
    unittest.main()
