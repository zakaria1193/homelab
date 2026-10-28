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


if __name__ == "__main__":
    unittest.main()
