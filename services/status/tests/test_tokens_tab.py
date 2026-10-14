import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit import tokens
from cockpit.pages.tokens import TOKENS_PAGE
from cockpit.pages.main import PAGE


class TestTokensTabIntegration(unittest.TestCase):
    def test_tokens_roster(self):
        items = tokens.roster()
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)
        for item in items:
            self.assertIn("id", item)
            self.assertIn("name", item)
            self.assertIn("variable", item)
            self.assertIn("status", item)
            self.assertIn("masked", item)

    def test_tokens_roster_defaults_to_untested(self):
        items = tokens.roster()
        for item in items:
            # If not tested yet in test session, status should be untested
            if item["id"] not in tokens._TEST_CACHE:
                self.assertEqual(item["status"], "untested")

    def test_tokens_page_contains_table(self):
        self.assertIn("token-table", TOKENS_PAGE)
        self.assertIn("/api/tokens", TOKENS_PAGE)
        self.assertIn("/api/tokens/test", TOKENS_PAGE)
        self.assertIn("btnTestAll", TOKENS_PAGE)

    def test_main_page_contains_tokens_tab(self):
        self.assertIn('data-tab="tokens"', PAGE)
        self.assertIn('id="pane-tokens"', PAGE)
        self.assertIn('id="tokensIframe"', PAGE)
        self.assertIn('tabId === "tokens"', PAGE)

    def test_test_token_unknown(self):
        res = tokens.test_token("non_existent_token_id_123")
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("status"), "error")


if __name__ == "__main__":
    unittest.main()
