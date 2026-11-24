#!/usr/bin/env python3
"""Tests for cockpit.ai_reauth and its HTTP endpoints."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cockpit import ai_reauth  # noqa: E402


class AiReauthTests(unittest.TestCase):
    def test_auth_status_structure(self):
        st = ai_reauth.auth_status()
        self.assertIn("claude", st)
        self.assertIn("agy", st)
        self.assertIsInstance(st["claude"]["authenticated"], bool)
        self.assertIsInstance(st["agy"]["authenticated"], bool)

    def test_cancel_login_when_none_active(self):
        res = ai_reauth.cancel_claude_login()
        self.assertTrue(res.get("ok"))

    def test_submit_code_fails_cleanly_when_no_active_login(self):
        res = ai_reauth.submit_claude_code("test-code-123")
        self.assertFalse(res.get("ok"))
        self.assertIn("no active claude login", res.get("error", "").lower())

    @patch("subprocess.run")
    def test_claude_authenticated_detection(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"loggedIn": true, "authMethod": "claude.ai"}'
        )
        st = ai_reauth.auth_status()
        self.assertTrue(st["claude"]["authenticated"])
        self.assertIn("Authenticated", st["claude"]["detail"])


class ExtractAgyLoginUrlTests(unittest.TestCase):
    def test_none_or_empty_pane_text(self):
        self.assertIsNone(ai_reauth.extract_agy_login_url(None))
        self.assertIsNone(ai_reauth.extract_agy_login_url(""))

    def test_no_url_in_pane(self):
        self.assertIsNone(ai_reauth.extract_agy_login_url("just some text\nno link here\n"))

    def test_plain_url(self):
        text = "Open this to sign in:\nhttps://accounts.google.com/o/oauth2/auth?x=1\nWaiting...\n"
        self.assertEqual(
            ai_reauth.extract_agy_login_url(text),
            "https://accounts.google.com/o/oauth2/auth?x=1",
        )

    def test_url_wrapped_over_lines_joined_with_dash_j(self):
        # tmux's `-J` already joins a soft-wrapped line before this function
        # sees it, so the input here is the already-joined single line.
        text = "Sign in: https://accounts.google.com/o/oauth2/auth?x=1&y=2&z=3 then wait"
        self.assertEqual(
            ai_reauth.extract_agy_login_url(text),
            "https://accounts.google.com/o/oauth2/auth?x=1&y=2&z=3",
        )

    def test_ansi_coloured_pane_text(self):
        text = "\x1b[32mOpen:\x1b[0m \x1b[4mhttps://accounts.google.com/auth?x=1\x1b[0m\n"
        self.assertEqual(
            ai_reauth.extract_agy_login_url(text),
            "https://accounts.google.com/auth?x=1",
        )

    def test_osc8_hyperlink_wrapper_is_stripped(self):
        url = "https://accounts.google.com/auth?x=1"
        text = "Open: \x1b]8;;%s\x1b\\%s\x1b]8;;\x1b\\\n" % (url, url)
        self.assertEqual(ai_reauth.extract_agy_login_url(text), url)

    def test_trailing_punctuation_is_trimmed(self):
        text = "sign in here: https://accounts.google.com/auth?x=1)."
        self.assertEqual(
            ai_reauth.extract_agy_login_url(text),
            "https://accounts.google.com/auth?x=1",
        )

    def test_non_google_urls_are_ignored(self):
        text = "Previous chat mentioned https://pjm.zakariafadli.com/#/t/lacommu-0046\n"
        self.assertIsNone(ai_reauth.extract_agy_login_url(text))

    def test_google_oauth_url_picked_over_earlier_non_google_url(self):
        text = (
            "see https://pjm.zakariafadli.com/#/t/lacommu-0046\n"
            "Visit https://accounts.google.com/o/oauth2/auth?x=1 to log in\n"
        )
        self.assertEqual(
            ai_reauth.extract_agy_login_url(text),
            "https://accounts.google.com/o/oauth2/auth?x=1",
        )

    def test_hard_wrapped_multiline_tui_url_is_joined(self):
        text = (
            " Your browser should open automatically. If not:\n\n"
            " https://accounts.google.com/o/oauth2/auth?access_type=offline&client_id=1071006060591-tmhssin2h21lcre23\n"
            " 5vtolojh4g403ep.apps.googleusercontent.com&code_challenge=QcKRl4tjbL1vC8OTqUfvpafxyVLJT7tdsJIb1UMYS0U&c\n"
            " ode_challenge_method=S256&state=xyz\n\n"
            " If you aren't automatically redirected, paste the authorization code below:\n"
        )
        self.assertEqual(
            ai_reauth.extract_agy_login_url(text),
            "https://accounts.google.com/o/oauth2/auth?access_type=offline&client_id=1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com&code_challenge=QcKRl4tjbL1vC8OTqUfvpafxyVLJT7tdsJIb1UMYS0U&code_challenge_method=S256&state=xyz",
        )


if __name__ == "__main__":
    unittest.main()
