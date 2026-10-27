"""homelab-0009: handler.py routes through GET_ROUTES/POST_ROUTES and
_send_json instead of a long if/elif chain, and /static/<name> is served
publicly, before the cockpit's own auth check."""

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from http.server import ThreadingHTTPServer  # noqa: E402

from cockpit import handler as handler_module  # noqa: E402
from cockpit.handler import StatusHandler  # noqa: E402


def _request(port, method, path, body=None, headers=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        hdrs = dict(headers or {})
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
            hdrs.setdefault("Origin", "http://127.0.0.1:%d" % port)
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        payload = resp.read()
        return resp.status, resp.getheader("Content-Type", ""), payload
    finally:
        conn.close()


class TestRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), StatusHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_every_get_page_and_api_answers_as_today(self):
        cases = [
            ("/", 200, "text/html"),
            ("/api/status", 200, "application/json"),
            ("/api/usage", 200, "application/json"),
            ("/claude-rc", 200, "text/html"),
            ("/api/claude-rc", 200, "application/json"),
            ("/antigravity-rc", 200, "text/html"),
            ("/api/antigravity-rc", 200, "application/json"),
            ("/media", 200, "text/html"),
            ("/api/media", 200, "application/json"),
            ("/supabase", 200, "text/html"),
            ("/api/supabase", 200, "application/json"),
            ("/tmux", 200, "text/html"),
            ("/api/tmux", 200, "application/json"),
            ("/cron", 200, "text/html"),
            ("/api/cron", 200, "application/json"),
            ("/tokens", 200, "text/html"),
            ("/api/tokens", 200, "application/json"),
            ("/ai-routes", 200, "text/html"),
            ("/api/ai-routes", 200, "application/json"),
            ("/ai-usage", 200, "text/html"),
            ("/api/ai-usage?range=48h", 200, "application/json"),
            ("/healthz", 200, "text/plain"),
            ("/logs?service=%s" % quote("homelab cockpit"), 200, "text/html"),
            ("/api/logs?service=%s" % quote("homelab cockpit"), 200, "text/plain"),
        ]
        for path, status, content_type in cases:
            with self.subTest(path=path):
                code, ctype, _ = _request(self.port, "GET", path)
                self.assertEqual(code, status, path)
                self.assertIn(content_type, ctype, path)

    def test_projects_redirects_to_pjm(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", "/projects")
            resp = conn.getresponse()
            resp.read()
            self.assertEqual(resp.status, 302)
            self.assertTrue(resp.getheader("Location", "").endswith("/#/projects"))
        finally:
            conn.close()

    def test_terminal_without_params_is_400(self):
        code, _, _ = _request(self.port, "GET", "/terminal")
        self.assertEqual(code, 400)

    def test_unknown_get_path_is_404(self):
        code, _, _ = _request(self.port, "GET", "/nope-at-all")
        self.assertEqual(code, 404)

    def test_post_bad_body_answers_400_json(self):
        paths = [
            "/api/tmux/kill", "/api/tmux/rename", "/api/tmux/create",
            "/api/cron/add", "/api/cron/toggle", "/api/cron/delete", "/api/cron/run",
            "/api/ai-sessions/add", "/api/ai-sessions/delete",
            "/api/service/toggle-enable",
            "/api/media/hopping", "/api/media/maintained", "/api/supabase/toggle",
            "/api/ai-routes", "/api/tokens/test",
            "/api/claude-rc/validate", "/api/claude-rc/create",
            "/api/claude-rc/action", "/api/claude-rc/delete",
            "/api/antigravity-rc/validate", "/api/antigravity-rc/create",
            "/api/antigravity-rc/action", "/api/antigravity-rc/delete",
        ]
        for path in paths:
            with self.subTest(path=path):
                code, ctype, payload = _request(
                    self.port, "POST", path, body=b"not json",
                    headers={"Content-Type": "application/json"},
                )
                self.assertEqual(code, 400, path)
                self.assertIn("application/json", ctype, path)
                self.assertFalse(json.loads(payload)["ok"], path)

    def test_unknown_post_path_is_404_json(self):
        code, ctype, payload = _request(self.port, "POST", "/api/not-a-route", body={})
        self.assertEqual(code, 404)
        self.assertIn("application/json", ctype)
        self.assertFalse(json.loads(payload)["ok"])

    def test_static_serves_css_and_js(self):
        static_dir = Path(handler_module.STATIC_DIR)
        static_dir.mkdir(parents=True, exist_ok=True)
        css = static_dir / "zz-test-routes.css"
        js = static_dir / "zz-test-routes.js"
        css.write_text("body{color:red}")
        js.write_text("console.log(1);")
        try:
            code, ctype, body = _request(self.port, "GET", "/static/zz-test-routes.css")
            self.assertEqual(code, 200)
            self.assertIn("text/css", ctype)
            self.assertEqual(body, b"body{color:red}")

            code, ctype, body = _request(self.port, "GET", "/static/zz-test-routes.js")
            self.assertEqual(code, 200)
            self.assertIn("text/javascript", ctype)
            self.assertEqual(body, b"console.log(1);")
        finally:
            css.unlink(missing_ok=True)
            js.unlink(missing_ok=True)

    def test_static_traversal_and_extension_cases_are_404(self):
        for path in (
            "/static/../handler.py",
            "/static/%2e%2e/handler.py",
            "/static/sub/x.js",
            "/static/theme.py",
            "/static/does-not-exist.css",
        ):
            with self.subTest(path=path):
                code, _, _ = _request(self.port, "GET", path)
                self.assertEqual(code, 404, path)

    def test_static_is_public_before_auth(self):
        static_dir = Path(handler_module.STATIC_DIR)
        static_dir.mkdir(parents=True, exist_ok=True)
        css = static_dir / "zz-test-public.css"
        css.write_text("body{}")
        try:
            with mock.patch.object(handler_module, "BASIC_USER", "admin"), \
                 mock.patch.object(handler_module, "BASIC_PASSWORD", "secret"):
                code, ctype, _ = _request(self.port, "GET", "/static/zz-test-public.css")
                self.assertEqual(code, 200)
                self.assertIn("text/css", ctype)

                code, _, _ = _request(self.port, "GET", "/", headers={"Accept": "text/html"})
                self.assertEqual(code, 303)

                code, _, _ = _request(self.port, "GET", "/api/status")
                self.assertEqual(code, 401)
        finally:
            css.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
