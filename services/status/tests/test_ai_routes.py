import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit.handler import StatusHandler
from cockpit.pages.main import PAGE

STATIC_DIR = Path(__file__).resolve().parent.parent / "cockpit" / "static"
MAIN_JS = (STATIC_DIR / "main.js").read_text()
AI_ROUTES_PAGE = ((Path(__file__).resolve().parent.parent / "cockpit" / "templates" / "ai_routes.html").read_text()
                  + (STATIC_DIR / "ai_routes.js").read_text())


class TestAiRoutesTabIntegration(unittest.TestCase):
    def test_ai_routes_page_content(self):
        self.assertIn("/api/ai-routes", AI_ROUTES_PAGE)
        self.assertIn("classesTable", AI_ROUTES_PAGE)
        self.assertIn("clientsTable", AI_ROUTES_PAGE)
        self.assertIn("saveRoutes", AI_ROUTES_PAGE)
        self.assertIn("addClientRow", AI_ROUTES_PAGE)
        self.assertIn('id="quotaStrip"', AI_ROUTES_PAGE)
        self.assertIn('href="/ai-usage"', AI_ROUTES_PAGE)

    def test_main_page_contains_ai_routes_tab(self):
        self.assertIn('data-tab="ai-routes"', PAGE)
        self.assertIn('id="pane-ai-routes"', PAGE)
        self.assertIn('id="aiRoutesIframe"', PAGE)
        self.assertIn('tabId === "ai-routes"', MAIN_JS)
        self.assertIn('href="/ai-routes"', PAGE)


class TestAiRoutesPost(unittest.TestCase):
    """POST /api/ai-routes against a temp routes.json, never the live one."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.routes_path = Path(tmp.name) / "routes.json"
        env = mock.patch.dict(os.environ, {"AICLI_ROUTES": str(self.routes_path)})
        env.start()
        self.addCleanup(env.stop)

    def _post(self, body):
        # Mirrors do_POST's own dispatch: the single bad-body check runs
        # before the route handler ever sees the body (handler.py's
        # POST_ROUTES/do_POST), so a None body never reaches _post_ai_routes.
        h = StatusHandler.__new__(StatusHandler)
        sent = []
        h._read_json = lambda: body
        h._send_json = lambda code, obj: sent.append((code, obj))
        if body is None:
            h._send_json(400, {"ok": False, "message": "expected a same-origin JSON body"})
        else:
            h._post_ai_routes(body)
        return sent[0]

    def test_saves_only_the_diff_and_drops_invalid_fields(self):
        """A changed field of a default row writes only that field - never the
        merged row, never aicli.toml - and an unknown class/invalid field is
        dropped rather than widening the write."""
        code, res = self._post({
            "classes": {"maintenance": {"tool": "claude", "tier": "deep"},
                        "made-up": {"tool": "claude"},
                        "standard-dev": {"tool": "gpt", "tier": "huge"}},
            "clients": {"a:b": {"class": "maintenance", "tool": "agy", "tier": "bogus"},
                        "c:d": {"class": "no-such-class"},
                        "pjm:auto-spec@deep-spec": {"model": " claude-opus-5-5 ", "tier": "deep"}},
        })
        self.assertEqual(code, 200)
        saved = json.loads(self.routes_path.read_text())
        # Only the diff from aicli.toml's default ever lands on disk.
        self.assertEqual(saved["classes"]["maintenance"], {"tool": "claude", "tier": "deep"})
        self.assertNotIn("made-up", saved["classes"])
        # Every field of standard-dev's update was invalid, so nothing at all
        # was written for it - not even an empty override.
        self.assertNotIn("standard-dev", saved.get("classes", {}))
        self.assertEqual(saved["clients"]["a:b"], {"class": "maintenance", "tool": "agy"})
        # c:d's only field was an unknown class, so it never became a row.
        self.assertNotIn("c:d", saved.get("clients", {}))
        self.assertEqual(saved["clients"]["pjm:auto-spec@deep-spec"], {"tier": "deep", "model": "claude-opus-5-5"})
        # The response is the merged view (aicli.toml + the diff above), not
        # a copy of what was written to disk.
        self.assertEqual(res["routes"]["classes"]["maintenance"]["tool"], "claude")
        self.assertEqual(res["routes"]["classes"]["maintenance"]["tier"], "deep")
        self.assertEqual(res["routes"]["classes"]["standard-dev"]["tool"], "claude")  # untouched default
        self.assertNotEqual(saved, res["routes"])

    def test_setting_a_field_back_to_default_drops_the_override(self):
        self._post({"classes": {"maintenance": {"tool": "claude", "tier": "deep"}}})
        self.assertIn("maintenance", json.loads(self.routes_path.read_text())["classes"])
        self._post({"classes": {"maintenance": {"tool": "agy", "tier": "low"}}})  # back to toml's default
        saved = json.loads(self.routes_path.read_text())
        self.assertNotIn("maintenance", saved.get("classes", {}))

    def test_optiplex_projects_write_only_the_diff(self):
        _, baseline = self._post({})  # no override yet: the merged list is aicli.toml's own
        default_list = baseline["routes"]["optiplex_projects"]
        code, res = self._post({"optiplex_projects": [" homelab ", "", "pjm"]})
        self.assertEqual(code, 200)
        saved = json.loads(self.routes_path.read_text())
        self.assertEqual(saved["optiplex_projects"], ["homelab", "pjm"])
        # Setting it back to aicli.toml's own list drops the override entirely.
        self._post({"optiplex_projects": list(default_list)})
        saved = json.loads(self.routes_path.read_text())
        self.assertNotIn("optiplex_projects", saved)

    def test_project_registry_disable_keeps_clients_and_names(self):
        self._post({"clients": {"pjm:auto-spec@deep-spec": {"model": "claude-opus-5-5"}},
                    "project_registry": {"pjm": {"enabled": True}, "farah": {"enabled": True}}})
        self._post({"project_registry": {"pjm": {"enabled": False}, "farah": {"enabled": True}}})
        saved = json.loads(self.routes_path.read_text())
        self.assertEqual(saved["optiplex_projects"], ["farah"])
        self.assertEqual(saved["project_registry"]["pjm"], {"enabled": False})
        self.assertEqual(saved["clients"]["pjm:auto-spec@deep-spec"], {"model": "claude-opus-5-5"})
        self._post({"optiplex_projects": ["pjm", "farah"]})
        saved = json.loads(self.routes_path.read_text())
        self.assertEqual(saved["optiplex_projects"], ["farah", "pjm"])

    def test_saves_and_clears_per_class_fallback_and_effort(self):
        code, res = self._post({
            "classes": {
                "standard-dev": {
                    "tool": "claude",
                    "tier": "default",
                    "effort": "high",  # differs from aicli.toml's "medium"
                    "fallback": {"tool": "agy", "model": "gemini-4-argon-high"},
                },
                "deep-spec": {
                    "tool": "claude",
                    "tier": "deep",
                    "fallback": None,  # aicli.toml gives deep-spec a fallback; this clears it
                },
            },
        })
        self.assertEqual(code, 200)
        saved = json.loads(self.routes_path.read_text())
        # Only the changed fields were written - tool/tier matched the
        # default already, so they never appear in the diff.
        self.assertEqual(saved["classes"]["standard-dev"], {
            "effort": "high",
            "fallback": {"tool": "agy", "model": "gemini-4-argon-high", "group": "Gemini 4 Argon"},
        })
        self.assertEqual(saved["classes"]["deep-spec"], {"fallback": None})
        self.assertEqual(res["routes"]["classes"]["standard-dev"]["effort"], "high")
        self.assertIsNone(res["routes"]["classes"]["deep-spec"]["fallback"])

    def test_save_keeps_fields_the_page_does_not_edit(self):
        self.routes_path.write_text(json.dumps({
            "classes": {"standard-dev": {"tool": "claude", "tier": "default", "effort": "medium",
                                         "description": "Standard dev", "frequency": "High"}},
            "clients": {"pjm:auto-execute": {"class": "standard-dev", "description": "impl",
                                             "frequency": "burst", "max_turns": 40},
                        "pjm:auto-spec@deep-spec": {"model": "claude-opus-5-5"}},
            "optiplex_projects": ["pjm"],
            "project_registry": {"pjm": {"enabled": True}},
        }))
        # What the board sends after rewiring one client to another class.
        code, res = self._post({
            "classes": {"standard-dev": {"tool": "claude", "tier": "deep", "effort": "medium"}},
            "clients": {"pjm:auto-execute": {"class": "deep-spec", "description": "impl", "frequency": "burst"},
                        "pjm:auto-spec@deep-spec": {"model": "claude-opus-5-5", "tool": "claude"}},
            "project_registry": {"pjm": {"enabled": True}},
        })
        saved = json.loads(self.routes_path.read_text())
        # Overrides hold only what differs from aicli.toml, so check the merged view.
        merged = res["routes"]["classes"]["standard-dev"]
        self.assertEqual(merged["tier"], "deep")
        self.assertEqual(merged["effort"], "medium")
        self.assertEqual(merged["description"], "Standard dev")
        self.assertEqual(saved["clients"]["pjm:auto-execute"],
                         {"max_turns": 40, "class": "deep-spec", "description": "impl", "frequency": "burst"})
        self.assertEqual(saved["clients"]["pjm:auto-spec@deep-spec"], {"tool": "claude", "model": "claude-opus-5-5"})
        self.assertEqual(saved["project_registry"], {"pjm": {"enabled": True}})
        self.assertEqual(saved["optiplex_projects"], ["pjm"])

    def test_board_view_is_wired_in(self):
        self.assertIn('id="board"', AI_ROUTES_PAGE)
        self.assertIn('/static/ai_routes_board.js', AI_ROUTES_PAGE)
        board_js = (STATIC_DIR / "ai_routes_board.js").read_text()
        self.assertIn("function renderBoard", board_js)
        self.assertIn("function boardConnect", board_js)

    def test_rejected_body_is_400_and_writes_nothing(self):
        code, _ = self._post(None)
        self.assertEqual(code, 400)
        self.assertFalse(self.routes_path.exists())

    def test_reset_class_drops_override_back_to_toml(self):
        self._post({"classes": {"maintenance": {"tool": "claude", "tier": "deep"}}})
        self.assertIn("maintenance", json.loads(self.routes_path.read_text())["classes"])
        code, res = self._post({"reset": {"classes": ["maintenance"]}})
        self.assertEqual(code, 200)
        saved = json.loads(self.routes_path.read_text())
        self.assertNotIn("maintenance", saved.get("classes", {}))
        # Reset to the toml default, not deleted: it is still a known class.
        self.assertEqual(res["routes"]["classes"]["maintenance"]["tool"], "agy")

    def test_remove_client_drops_an_added_row_entirely(self):
        self._post({"clients": {"new-caller:task": {"class": "maintenance"}}})
        self.assertIn("new-caller:task", json.loads(self.routes_path.read_text())["clients"])
        code, res = self._post({"reset": {"clients": ["new-caller:task"]}})
        self.assertEqual(code, 200)
        saved = json.loads(self.routes_path.read_text())
        self.assertNotIn("new-caller:task", saved.get("clients", {}))
        # Not a toml default, so it is gone from the merged view too.
        self.assertNotIn("new-caller:task", res["routes"]["clients"])

    def test_get_reports_overridden_and_default_rows(self):
        self._post({"classes": {"maintenance": {"tool": "claude", "tier": "deep"}},
                    "clients": {"new-caller:task": {"class": "maintenance"}}})
        h = StatusHandler.__new__(StatusHandler)
        sent = []
        h._send_json = lambda code, obj: sent.append((code, obj))
        h._api_ai_routes({})
        code, res = sent[0]
        self.assertEqual(code, 200)
        self.assertIn("maintenance", res["overridden"]["classes"])
        self.assertIn("new-caller:task", res["overridden"]["clients"])
        self.assertIn("maintenance", res["default_classes"])
        self.assertNotIn("new-caller:task", res["default_clients"])

    def test_stale_field_override_is_flagged_and_removable(self):
        """A field override for a class aicli.toml no longer defines (e.g. it
        was renamed/removed in a later aicli.toml) is reported as stale, not
        silently dropped or applied, and "reset" clears it like any other row."""
        self.routes_path.write_text(json.dumps({"classes": {"retired-class": {"tier": "deep"}}}))
        h = StatusHandler.__new__(StatusHandler)
        sent = []
        h._send_json = lambda code, obj: sent.append((code, obj))
        h._api_ai_routes({})
        code, res = sent[0]
        self.assertEqual(code, 200)
        self.assertNotIn("retired-class", res["classes"])  # never surfaces as a runnable class
        self.assertIn("retired-class", res["stale"]["classes"])
        code, res = self._post({"reset": {"classes": ["retired-class"]}})
        self.assertEqual(code, 200)
        self.assertNotIn("retired-class", json.loads(self.routes_path.read_text()).get("classes", {}))


if __name__ == "__main__":
    unittest.main()
