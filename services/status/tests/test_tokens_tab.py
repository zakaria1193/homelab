import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit import tokens
from cockpit.pages.tokens import TOKENS_PAGE
from cockpit.pages.main import PAGE

MAIN_JS = (Path(__file__).resolve().parent.parent / "cockpit" / "static" / "main.js").read_text()


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
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(tokens, "CACHE_FILE", Path(tmp) / "empty.json"):
                items = tokens.roster()
                for item in items:
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
        self.assertIn('tabId === "tokens"', MAIN_JS)

    def test_test_token_unknown(self):
        res = tokens.test_token("non_existent_token_id_123")
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("status"), "error")

    def test_missing_variable_is_recorded_and_saved(self):
        token_id = tokens.TOKEN_DEFS[0]["id"]
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.json"
            with mock.patch.object(tokens, "CACHE_FILE", cache), \
                 mock.patch.object(tokens, "_read_env_val", return_value=""):
                res = tokens.test_token(token_id)
                self.assertEqual(res["id"], token_id)
                self.assertEqual(res["badge"], "Missing")
                self.assertEqual(json.loads(cache.read_text())[token_id]["badge"], "Missing")


class _Resp:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestTokenKinds(unittest.TestCase):
    """Each check against a canned answer; nothing leaves the machine."""

    def run_check(self, token_id, payload):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(tokens, "CACHE_FILE", Path(tmp) / "c.json"), \
             mock.patch.object(tokens, "_read_env_val", return_value="secret"), \
             mock.patch.object(tokens.urllib.request, "urlopen", return_value=_Resp(payload)) as op:
            return tokens.test_token(token_id), op

    def test_cloudflare_token_not_yet_valid_is_not_active(self):
        res, _ = self.run_check("cf_dns", {
            "success": True, "messages": [{"message": "This API Token is valid and active"}],
            "result": {"status": "active", "not_before": "2999-01-01T00:00:00Z"},
        })
        self.assertFalse(res["ok"])
        self.assertIn("2999", res["message"])

    def test_cloudflare_expired_token_is_not_active(self):
        res, _ = self.run_check("cf_dns", {
            "success": True, "result": {"status": "active", "expires_on": "2000-01-01T00:00:00Z"},
        })
        self.assertFalse(res["ok"])

    def test_cloudflare_valid_token_is_active(self):
        res, _ = self.run_check("cf_dns", {"success": True, "result": {"status": "active"}})
        self.assertTrue(res["ok"])

    def test_meili_asks_an_endpoint_that_needs_the_key(self):
        meili = next(t for t in tokens.TOKEN_DEFS if t["kind"] == "meili")
        res, op = self.run_check(meili["id"], {"results": [], "total": 0})
        self.assertTrue(res["ok"])
        self.assertNotIn("/health", op.call_args[0][0].full_url)


if __name__ == "__main__":
    unittest.main()
