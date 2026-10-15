import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit.pages.ai_routes import AI_ROUTES_PAGE
from cockpit.pages.main import PAGE


class TestAiRoutesTabIntegration(unittest.TestCase):
    def test_ai_routes_page_content(self):
        self.assertIn("/api/ai-routes", AI_ROUTES_PAGE)
        self.assertIn("classesTable", AI_ROUTES_PAGE)
        self.assertIn("clientsTable", AI_ROUTES_PAGE)
        self.assertIn("saveRoutes", AI_ROUTES_PAGE)
        self.assertIn("addClientRow", AI_ROUTES_PAGE)

    def test_main_page_contains_ai_routes_tab(self):
        self.assertIn('data-tab="ai-routes"', PAGE)
        self.assertIn('id="pane-ai-routes"', PAGE)
        self.assertIn('id="aiRoutesIframe"', PAGE)
        self.assertIn('tabId === "ai-routes"', PAGE)
        self.assertIn('href="/ai-routes"', PAGE)


if __name__ == "__main__":
    unittest.main()
