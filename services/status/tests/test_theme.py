"""homelab-0005 / homelab-0009: every cockpit page draws its base styles
from one shared theme, is light-only, and has no `prefers-color-scheme`.

A page not yet moved to the templates/static layout still builds its HTML
string in cockpit/pages/<name>.py from cockpit.pages.theme.THEME; a moved
page's shell links /static/theme.css instead, so its check reads the shell
plus the static files it links."""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cockpit.pages.main import PAGE as MAIN_PAGE  # noqa: E402

TEMPLATES_DIR = ROOT / "cockpit" / "templates"
STATIC_DIR = ROOT / "cockpit" / "static"
THEME_CSS = (STATIC_DIR / "theme.css").read_text()

# name -> (shell file in cockpit/templates, page css, page js or None)
MOVED_PAGES = {
    "login": ("login.html", "login.css", None),
    "logs": ("logs.html", "logs.css", "logs.js"),
    "terminal": ("terminal.html", "terminal.css", "terminal.js"),
    "tmux": ("tmux.html", "tmux.css", "tmux.js"),
    "cron": ("cron.html", "cron.css", "cron.js"),
    "claude_rc": ("claude_rc.html", "claude_rc.css", "claude_rc.js"),
    "antigravity_rc": ("antigravity_rc.html", "antigravity_rc.css", "antigravity_rc.js"),
    "projects": ("projects.html", "projects.css", "projects.js"),
    "supabase": ("supabase.html", "supabase.css", "supabase.js"),
    "media": ("media.html", "media.css", "media.js"),
}

# name -> the page's own HTML string, still built from theme.THEME.
INLINE_PAGES = {
    "main": MAIN_PAGE,
}


def _read_static(name):
    path = STATIC_DIR / name
    return path.read_text() if path.exists() else ""


PAGES = dict(INLINE_PAGES)
for _name, (_shell, _css, _js) in MOVED_PAGES.items():
    _parts = [(TEMPLATES_DIR / _shell).read_text(), THEME_CSS, _read_static(_css)]
    if _js:
        _parts.append(_read_static(_js))
    PAGES[_name] = "\n".join(_parts)

# Every static/*.css file except the shared theme itself: a page CSS file
# must draw its buttons, dot and colours from theme.css's tokens, not
# re-declare them.
PAGE_CSS_FILES = sorted(p for p in STATIC_DIR.glob("*.css") if p.name != "theme.css")

# The old GitHub-dark literals a page CSS file must not bring back, listed
# in the homelab-0009 ticket.
FORBIDDEN_COLOURS = [
    "rgba(63,185,80",
    "rgba(248,81,73",
    "#d29922",
    "rgba(88,166,255",
    "#b62324",
    "rgba(255,255,255,0.02)",
]


def _uses_shared_theme(html):
    return "--accent: #155bd0" in html.lower()


def _is_light_only(html):
    lowered = html.lower()
    return "color-scheme: light" in lowered and "prefers-color-scheme" not in lowered


class TestCockpitTheme(unittest.TestCase):
    def test_theme_css_holds_the_tokens(self):
        self.assertIn("--accent: #155bd0", THEME_CSS)
        self.assertIn("color-scheme: light", THEME_CSS)

    def test_moved_pages_link_theme_css(self):
        for name, (shell, _css, _js) in MOVED_PAGES.items():
            with self.subTest(page=name):
                shell_html = (TEMPLATES_DIR / shell).read_text()
                self.assertIn('href="/static/theme.css"', shell_html,
                              f"{name}'s shell does not link /static/theme.css")

    def test_no_static_file_holds_a_placeholder(self):
        # "No static file contains a __X__ placeholder" - every __X__ token
        # only ever lives in the templates/*.html shell.
        for path in [*PAGE_CSS_FILES, STATIC_DIR / "theme.css", STATIC_DIR / "common.js",
                     *(STATIC_DIR / js for _, _, js in MOVED_PAGES.values() if js)]:
            with self.subTest(file=path.name):
                self.assertNotRegex(path.read_text(), r"__[A-Z_]+__")

    def test_no_page_css_redeclares_btn_or_status_dot(self):
        for path in PAGE_CSS_FILES:
            css = path.read_text()
            with self.subTest(file=path.name):
                self.assertNotRegex(css, r"\.btn\s*\{",
                                     f"{path.name} re-declares .btn")
                self.assertNotRegex(css, r"\.status-dot\s*\{",
                                     f"{path.name} re-declares .status-dot")

    def test_no_page_css_has_forbidden_dark_colours(self):
        for path in PAGE_CSS_FILES:
            css = re.sub(r"\s+", "", path.read_text())
            with self.subTest(file=path.name):
                for colour in FORBIDDEN_COLOURS:
                    self.assertNotIn(re.sub(r"\s+", "", colour), css,
                                      f"{path.name} still has {colour!r}")


def _make_theme_test(name, html):
    def test(self):
        self.assertTrue(
            _uses_shared_theme(html),
            f"{name} does not pull its colours from the shared theme",
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
