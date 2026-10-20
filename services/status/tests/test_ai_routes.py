import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit.handler import StatusHandler
from cockpit.pages.ai_routes import AI_ROUTES_PAGE
from cockpit.pages.main import PAGE


class TestAiRoutesTabIntegration(unittest.TestCase):
    def test_ai_routes_page_content(self):
        self.assertIn("/api/ai-routes", AI_ROUTES_PAGE)
        self.assertIn("classesTable", AI_ROUTES_PAGE)
        self.assertIn("clientsTable", AI_ROUTES_PAGE)
        self.assertIn("saveRoutes", AI_ROUTES_PAGE)
        self.assertIn("addClientRow", AI_ROUTES_PAGE)
        self.assertIn("/api/aicli-usage", AI_ROUTES_PAGE)
        self.assertIn('id="usagePanel"', AI_ROUTES_PAGE)
        self.assertIn('id="usageChart"', AI_ROUTES_PAGE)
        self.assertIn('id="usageByModelTbody"', AI_ROUTES_PAGE)
        self.assertIn('id="usageByClientTbody"', AI_ROUTES_PAGE)
        self.assertIn("setUsageWindow", AI_ROUTES_PAGE)

    def test_main_page_contains_ai_routes_tab(self):
        self.assertIn('data-tab="ai-routes"', PAGE)
        self.assertIn('id="pane-ai-routes"', PAGE)
        self.assertIn('id="aiRoutesIframe"', PAGE)
        self.assertIn('tabId === "ai-routes"', PAGE)
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

    def test_saves_valid_changes_and_drops_invalid_ones(self):
        code, res = self._post({
            "classes": {"maintenance": {"tool": "claude", "tier": "deep"},
                        "made-up": {"tool": "claude"},
                        "standard-dev": {"tool": "gpt", "tier": "huge"}},
            "clients": {"a:b": {"class": "maintenance", "tool": "agy", "tier": "bogus"},
                        "c:d": {"class": "no-such-class"}},
            "optiplex_projects": [" homelab ", "", "pjm"],
        })
        self.assertEqual(code, 200)
        saved = json.loads(self.routes_path.read_text())
        self.assertEqual(saved, res["routes"])
        self.assertEqual(saved["classes"]["maintenance"]["tool"], "claude")
        self.assertEqual(saved["classes"]["maintenance"]["tier"], "deep")
        self.assertNotIn("made-up", saved["classes"])
        self.assertEqual(saved["classes"]["standard-dev"]["tool"], "claude")
        self.assertEqual(saved["clients"]["a:b"], {"class": "maintenance", "tool": "agy"})
        self.assertEqual(saved["clients"]["c:d"], {})
        self.assertEqual(saved["optiplex_projects"], ["homelab", "pjm"])

    def test_rejected_body_is_400_and_writes_nothing(self):
        code, res = self._post(None)
        self.assertEqual(code, 400)
        self.assertFalse(self.routes_path.exists())


if __name__ == "__main__":
    unittest.main()
