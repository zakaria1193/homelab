#!/usr/bin/env python3
"""homelab-0012: the cockpit's Projects tab is a plain link to pjm's Projects
page, not a pane with an iframe, and a stale `cockpit_active_tab` of
"projects" in localStorage must not land on an empty pane."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit.pages.main import PAGE  # noqa: E402

MAIN_JS = (Path(__file__).resolve().parent.parent / "cockpit" / "static" / "main.js").read_text()


class TestProjectsTab(unittest.TestCase):
    def test_projects_tab_is_a_link_not_a_button(self):
        self.assertIn('<a class="cockpit-tab-btn" id="projectsTabLink"', PAGE)
        self.assertNotIn('data-tab="projects"', PAGE)

    def test_projects_tab_opens_in_a_new_tab(self):
        tab = PAGE.split('id="projectsTabLink"')[1].split(">")[0]
        self.assertIn('target="_blank"', tab)
        self.assertIn('rel="noopener"', tab)

    def test_projects_pane_and_iframe_are_gone(self):
        self.assertNotIn('id="pane-projects"', PAGE)
        self.assertNotIn("projectsIframe", PAGE)

    def test_projects_tab_falls_back_to_page_host_before_status_loads(self):
        self.assertIn("setProjectsTabLink(`http://${location.hostname}:8400/#/projects`)", MAIN_JS)

    def test_projects_tab_is_updated_from_the_pjm_status_entry(self):
        self.assertIn('s.name === "pjm"', MAIN_JS)
        self.assertIn('"/#/projects"', MAIN_JS)

    def test_cockpit_still_always_opens_on_ai_sessions(self):
        # The pane is gone, so a stored "projects" tab must not uncover an
        # empty one - this already holds because the cockpit ignores the
        # stored tab entirely and always opens on AI Sessions.
        self.assertIn('switchTab("ai-sessions");', MAIN_JS)


if __name__ == "__main__":
    unittest.main()
