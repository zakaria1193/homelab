"""homelab-0005: every cockpit page takes its base styles from one shared
theme (`cockpit/pages/theme.py`), is light-only, and has no
`prefers-color-scheme`. Pages not yet restyled are listed in
`NOT_YET_MIGRATED` below as expected failures; drop a page from that set in
the same commit that restyles it."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cockpit.pages.antigravity_rc import AGY_RC_PAGE  # noqa: E402
from cockpit.pages.claude_rc import RC_PAGE  # noqa: E402
from cockpit.pages.cron import CRON_PAGE  # noqa: E402
from cockpit.pages.login import LOGIN_PAGE  # noqa: E402
from cockpit.pages.logs import LOG_PAGE  # noqa: E402
from cockpit.pages.main import PAGE as MAIN_PAGE  # noqa: E402
from cockpit.pages.projects import PROJECTS_PAGE  # noqa: E402
from cockpit.pages.terminal import TERMINAL_PAGE  # noqa: E402
from cockpit.pages.tmux import TMUX_PAGE  # noqa: E402
from ideas_page import IDEAS_PAGE  # noqa: E402
from supabase_keepalive import SUPABASE_PAGE  # noqa: E402

PAGES = {
    "main": MAIN_PAGE,
    "login": LOGIN_PAGE,
    "logs": LOG_PAGE,
    "terminal": TERMINAL_PAGE,
    "tmux": TMUX_PAGE,
    "claude_rc": RC_PAGE,
    "antigravity_rc": AGY_RC_PAGE,
    "projects": PROJECTS_PAGE,
    "cron": CRON_PAGE,
    "idea": IDEAS_PAGE,
    "supabase": SUPABASE_PAGE,
}

# Plan items 2-4 of homelab-0005 restyle these page by page. Remove a page
# from this set in the same commit that moves it onto the shared theme.
NOT_YET_MIGRATED = set(PAGES)


def _uses_shared_theme(html):
    return "--accent: #155bd0" in html.lower()


def _is_light_only(html):
    lowered = html.lower()
    return "color-scheme: light" in lowered and "prefers-color-scheme" not in lowered


class TestCockpitTheme(unittest.TestCase):
    def test_migration_set_only_names_known_pages(self):
        self.assertEqual(NOT_YET_MIGRATED - set(PAGES), set())


def _make_theme_test(name, html):
    def test(self):
        self.assertTrue(
            _uses_shared_theme(html),
            f"{name} does not pull its colours from cockpit.pages.theme",
        )

    return test


def _make_light_only_test(name, html):
    def test(self):
        self.assertTrue(
            _is_light_only(html),
            f"{name} is missing 'color-scheme: light' or still has 'prefers-color-scheme'",
        )

    return test


for _name, _html in PAGES.items():
    _theme_test = _make_theme_test(_name, _html)
    _light_test = _make_light_only_test(_name, _html)
    if _name in NOT_YET_MIGRATED:
        _theme_test = unittest.expectedFailure(_theme_test)
        _light_test = unittest.expectedFailure(_light_test)
    setattr(TestCockpitTheme, f"test_{_name}_uses_shared_theme", _theme_test)
    setattr(TestCockpitTheme, f"test_{_name}_is_light_only", _light_test)


if __name__ == "__main__":
    unittest.main()
