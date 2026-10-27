import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cockpit.pages.main import PAGE as SHELL  # noqa: E402

STATIC_DIR = ROOT / "cockpit" / "static"
PAGE = "\n".join([
    SHELL,
    (STATIC_DIR / "main.css").read_text(),
    (STATIC_DIR / "main.js").read_text(),
])


class TestDefaultView(unittest.TestCase):
    def test_cockpit_opens_on_ai_sessions(self):
        self.assertIn('switchTab("ai-sessions");', PAGE)
        self.assertNotIn("initialTab", PAGE)

    def test_ai_sessions_tab_is_first(self):
        tabs = PAGE.split('<nav class="cockpit-tabs"')[1].split("</nav>")[0]
        first = tabs.index("<button")
        self.assertEqual(first, tabs.index('<button type="button" class="cockpit-tab-btn active" data-tab="ai-sessions">'))

    def test_every_tab_is_full_width(self):
        self.assertIn(".wrap { max-width: 100%;", PAGE)
        self.assertNotIn("full-width-tab", PAGE)

    def test_ideas_board_is_gone(self):
        # pjm replaced the Ideas board; the cockpit no longer links to it.
        self.assertNotIn("/idea", PAGE)


if __name__ == "__main__":
    unittest.main()
