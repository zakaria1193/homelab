import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit import tokens


class _Resp:
    """Stands in for the urllib response urlopen() hands back."""

    def __init__(self, payload, headers=None):
        self.payload = json.dumps(payload).encode()
        self.headers = headers or {}

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _target(token_id):
    return next(t for t in tokens.TOKEN_DEFS if t["id"] == token_id)


def _one_of_kind(kind):
    return next(t for t in tokens.TOKEN_DEFS if t["kind"] == kind)


class TestTokenKinds(unittest.TestCase):
    """Every kind goes through test_token() with a mocked urlopen; nothing
    reaches the network. Covers a success and a failure per kind."""

    def run_check(self, token_id, urlopen_return=None, urlopen_side_effect=None, env_val="secret"):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(tokens, "CACHE_FILE", Path(tmp) / "c.json"), \
             mock.patch.object(tokens, "_read_env_val", return_value=env_val), \
             mock.patch.object(
                 tokens.urllib.request, "urlopen",
                 return_value=urlopen_return, side_effect=urlopen_side_effect,
             ) as op:
            return tokens.test_token(token_id), op

    # -- missing / offline, shared across kinds -----------------------------

    def test_missing_value_sends_no_request(self):
        token_id = tokens.TOKEN_DEFS[0]["id"]
        res, op = self.run_check(token_id, env_val="")
        self.assertEqual(res["badge"], "Missing")
        self.assertEqual(res["status"], "warn")
        op.assert_not_called()

    def test_offline_is_warn_not_error(self):
        token_id = _one_of_kind("arr")["id"]
        res, _ = self.run_check(token_id, urlopen_side_effect=tokens.urllib.error.URLError("refused"))
        self.assertEqual(res["badge"], "Offline")
        self.assertEqual(res["status"], "warn")
        self.assertFalse(tokens.is_failure(res))

    def test_http_error_is_failure(self):
        token_id = _one_of_kind("arr")["id"]
        err = tokens.urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, None)
        res, _ = self.run_check(token_id, urlopen_side_effect=err)
        self.assertEqual(res["badge"], "HTTP 401")
        self.assertTrue(tokens.is_failure(res))

    # -- cloudflare -----------------------------------------------------

    def test_cloudflare_valid_token_is_active(self):
        res, _ = self.run_check("cf_dns", _Resp({"success": True, "result": {"status": "active"}}))
        self.assertTrue(res["ok"])
        self.assertFalse(tokens.is_failure(res))

    def test_cloudflare_rejected_token_is_failure(self):
        res, _ = self.run_check("cf_dns", _Resp({"success": False, "errors": [{"message": "Invalid"}]}))
        self.assertFalse(res["ok"])
        self.assertTrue(tokens.is_failure(res))

    def test_cloudflare_not_yet_valid_is_failure(self):
        res, _ = self.run_check("cf_dns", _Resp({
            "success": True,
            "result": {"status": "active", "not_before": "2999-01-01T00:00:00Z"},
        }))
        self.assertFalse(res["ok"])
        self.assertEqual(res["badge"], "Not yet valid")
        self.assertTrue(tokens.is_failure(res))

    def test_cloudflare_expired_is_failure(self):
        res, _ = self.run_check("cf_dns", _Resp({
            "success": True,
            "result": {"status": "active", "expires_on": "2000-01-01T00:00:00Z"},
        }))
        self.assertFalse(res["ok"])
        self.assertEqual(res["badge"], "Expired")
        self.assertTrue(tokens.is_failure(res))

    # -- supabase ---------------------------------------------------------

    def test_supabase_success(self):
        res, _ = self.run_check("supabase", _Resp([{"name": "proj"}]))
        self.assertTrue(res["ok"])

    def test_supabase_failure(self):
        res, _ = self.run_check("supabase", _Resp({"message": "Invalid token"}))
        self.assertFalse(res["ok"])
        self.assertTrue(tokens.is_failure(res))

    def test_supabase_mgmt_entry_exists_and_uses_supabase_env(self):
        target = _target("supabase_mgmt")
        self.assertEqual(target["kind"], "supabase")
        self.assertEqual(target["env_path"], "services/supabase/.env")

    # -- slack --------------------------------------------------------------

    def test_slack_bot_success(self):
        res, _ = self.run_check("pjm_slack_bot", _Resp({"ok": True, "user": "pjm", "team": "home"}))
        self.assertTrue(res["ok"])

    def test_slack_bot_failure(self):
        res, _ = self.run_check("pjm_slack_bot", _Resp({"ok": False, "error": "invalid_auth"}))
        self.assertTrue(tokens.is_failure(res))

    def test_slack_app_success(self):
        res, _ = self.run_check("pjm_slack_app", _Resp({"ok": True}))
        self.assertTrue(res["ok"])

    def test_slack_app_failure(self):
        res, _ = self.run_check("pjm_slack_app", _Resp({"ok": False, "error": "invalid_auth"}))
        self.assertTrue(tokens.is_failure(res))

    # -- arr (sonarr/radarr/prowlarr/chaptarr) -------------------------------

    def test_arr_sends_key_in_header_not_query_string(self):
        resp = _Resp({"version": "5.0"})
        res, op = self.run_check("radarr", resp)
        self.assertTrue(res["ok"])
        sent_req = op.call_args[0][0]
        self.assertNotIn("apiKey", sent_req.full_url)
        self.assertEqual(sent_req.headers.get("X-api-key"), "secret")

    def test_arr_rejected(self):
        res, _ = self.run_check("radarr", _Resp({"message": "ApiKey invalid"}))
        self.assertTrue(tokens.is_failure(res))

    # -- jellyfin -------------------------------------------------------

    def test_jellyfin_success(self):
        res, _ = self.run_check("jellyfin", _Resp({"Version": "10.9", "ServerName": "dell"}))
        self.assertTrue(res["ok"])

    def test_jellyfin_failure(self):
        res, _ = self.run_check("jellyfin", _Resp({}))
        self.assertTrue(tokens.is_failure(res))

    # -- ai_endpoint ------------------------------------------------------

    def test_ai_endpoint_reads_base_url_from_env_and_appends_models(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(tokens, "CACHE_FILE", Path(tmp) / "c.json"), \
             mock.patch.object(tokens, "_read_env_val", return_value="http://host.docker.internal:8500/v1"), \
             mock.patch.object(tokens.urllib.request, "urlopen", return_value=_Resp({"data": [{"id": "agy"}]})) as op:
            res = tokens.test_token("karakeep_ai")
        self.assertTrue(res["ok"])
        sent_req = op.call_args[0][0]
        self.assertEqual(sent_req.full_url, "http://127.0.0.1:8500/v1/models")

    def test_ai_endpoint_falls_back_when_base_url_empty(self):
        # The "has a value" check (the OPENAI_BASE_URL variable itself) must stay
        # truthy so the check runs at all, even when the URL resolver then reads
        # an empty string and falls back.
        def fake_read(_path, _var):
            return " "

        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(tokens, "CACHE_FILE", Path(tmp) / "c.json"), \
             mock.patch.object(tokens, "_read_env_val", side_effect=fake_read), \
             mock.patch.object(tokens.urllib.request, "urlopen", return_value=_Resp({"data": []})) as op:
            res = tokens.test_token("karakeep_ai")
        self.assertTrue(res["ok"])
        sent_req = op.call_args[0][0]
        self.assertEqual(sent_req.full_url, "http://127.0.0.1:8500/v1/models")

    def test_ai_endpoint_failure(self):
        res, _ = self.run_check("karakeep_ai", _Resp({"error": "nope"}))
        self.assertTrue(tokens.is_failure(res))

    # -- meili ------------------------------------------------------------

    def test_meili_asks_an_endpoint_that_needs_the_key(self):
        res, op = self.run_check("karakeep_meili", _Resp({"results": [], "total": 0}))
        self.assertTrue(res["ok"])
        self.assertNotIn("/health", op.call_args[0][0].full_url)

    def test_meili_failure(self):
        res, _ = self.run_check("karakeep_meili", _Resp({"message": "invalid key"}))
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "warn")

    # -- hass ---------------------------------------------------------------

    def test_hass_success(self):
        res, _ = self.run_check("hass_token", _Resp({"message": "API running."}))
        self.assertTrue(res["ok"])

    def test_hass_failure(self):
        res, _ = self.run_check("hass_token", _Resp({}))
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "warn")

    # -- github -------------------------------------------------------------

    def test_github_success_reports_scopes(self):
        res, _ = self.run_check("github", _Resp({"login": "zakaria1193"}, headers={"X-OAuth-Scopes": "repo, workflow"}))
        self.assertTrue(res["ok"])
        self.assertIn("zakaria1193", res["message"])
        self.assertIn("repo, workflow", res["message"])

    def test_github_fine_grained_token_has_no_scopes_header(self):
        res, _ = self.run_check("github", _Resp({"login": "zakaria1193"}, headers={}))
        self.assertTrue(res["ok"])
        self.assertIn("Fine-grained token", res["message"])

    def test_github_rejected(self):
        res, _ = self.run_check("github", _Resp({"message": "Bad credentials"}))
        self.assertTrue(tokens.is_failure(res))

    # -- aicli ------------------------------------------------------------

    def test_aicli_success(self):
        res, _ = self.run_check("aicli", _Resp({"object": "list", "data": [{"id": "claude"}]}))
        self.assertTrue(res["ok"])

    def test_aicli_failure(self):
        res, _ = self.run_check("aicli", _Resp({"error": "nope"}))
        self.assertTrue(tokens.is_failure(res))

    # -- hermes_auth ----------------------------------------------------

    def test_hermes_auth_401_without_credentials_is_success(self):
        err = tokens.urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, None)
        res, _ = self.run_check("hermes_dashboard", urlopen_side_effect=err)
        self.assertTrue(res["ok"])
        self.assertEqual(res["badge"], "Enforced")
        self.assertFalse(tokens.is_failure(res))

    def test_hermes_auth_redirect_to_login_is_success(self):
        err = tokens.urllib.error.HTTPError("http://x", 302, "Found", {}, None)
        res, _ = self.run_check("hermes_dashboard", urlopen_side_effect=err)
        self.assertTrue(res["ok"])
        self.assertEqual(res["badge"], "Enforced")

    def test_hermes_auth_200_without_credentials_is_failure(self):
        res, _ = self.run_check("hermes_dashboard", _Resp({}))
        self.assertFalse(res["ok"])
        self.assertTrue(tokens.is_failure(res))

    def test_hermes_auth_offline_is_warn_not_error(self):
        res, _ = self.run_check("hermes_dashboard", urlopen_side_effect=tokens.urllib.error.URLError("refused"))
        self.assertEqual(res["badge"], "Offline")
        self.assertFalse(tokens.is_failure(res))

    def test_hermes_auth_resets_the_global_opener_after_use(self):
        """`no_redirect` swaps in a custom opener via install_opener(); it
        must restore the default afterwards so other kinds are unaffected."""
        err = tokens.urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, None)
        self.run_check("hermes_dashboard", urlopen_side_effect=err)
        self.assertIsNone(tokens.urllib.request._opener)

    def test_no_openai_kind_remains(self):
        self.assertNotIn("openai", tokens.KIND_DEFS)
        self.assertFalse(any(t["kind"] == "openai" for t in tokens.TOKEN_DEFS))

    def test_is_failure_rule(self):
        self.assertTrue(tokens.is_failure({"status": "error"}))
        self.assertFalse(tokens.is_failure({"status": "warn"}))
        self.assertFalse(tokens.is_failure({"status": "active"}))


if __name__ == "__main__":
    unittest.main()
