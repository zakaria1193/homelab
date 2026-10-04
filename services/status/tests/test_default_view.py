import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit.pages.main import PAGE  # noqa: E402
from ideas_page import IDEAS_PAGE  # noqa: E402


class TestDefaultView(unittest.TestCase):
    def test_cockpit_opens_on_ideas(self):
        self.assertIn('switchTab("ideas");', PAGE)
        self.assertNotIn("initialTab", PAGE)

    def test_ideas_tab_is_first(self):
        tabs = PAGE.split('<nav class="cockpit-tabs"')[1].split("</nav>")[0]
        self.assertLess(tabs.index('data-tab="ideas"'), tabs.index('data-tab="ai-sessions"'))
        self.assertIn('class="cockpit-tab-btn active" data-tab="ideas"', tabs)

    def test_every_tab_is_full_width(self):
        self.assertIn(".wrap { max-width: 100%;", PAGE)
        self.assertNotIn("full-width-tab", PAGE)

    def test_ideas_never_merges_boards(self):
        self.assertNotIn("All Projects", IDEAS_PAGE)
        self.assertNotIn('currentFileFilter !== "all"', IDEAS_PAGE)

    def test_ideas_opens_on_homelab_board(self):
        self.assertIn("/^homelab$/i", IDEAS_PAGE)


if __name__ == "__main__":
    unittest.main()
