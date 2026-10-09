import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit.pages.main import PAGE  # noqa: E402


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
