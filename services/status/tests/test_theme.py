"""homelab-0005: every cockpit page takes its base styles from one shared
theme (`cockpit/pages/theme.py`), is light-only, and has no
`prefers-color-scheme`."""

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
    "supabase": SUPABASE_PAGE,
}


def _uses_shared_theme(html):
    return "--accent: #155bd0" in html.lower()


def _is_light_only(html):
    lowered = html.lower()
    return "color-scheme: light" in lowered and "prefers-color-scheme" not in lowered


class TestCockpitTheme(unittest.TestCase):
    pass


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
    setattr(TestCockpitTheme, f"test_{_name}_uses_shared_theme", _make_theme_test(_name, _html))
    setattr(TestCockpitTheme, f"test_{_name}_is_light_only", _make_light_only_test(_name, _html))


if __name__ == "__main__":
    unittest.main()
