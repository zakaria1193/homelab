#!/usr/bin/env python3
"""Tests for kandev_mcp.py against a fake Kandev (health, login, tokens, MCP).

The unit check is stubbed as "active": these tests cover the token handling
and the MCP handshake, which is where "is it really up" gets decided.
"""

import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kandev_mcp  # noqa: E402

PASSWORD = "right-password"


class FakeKandev(BaseHTTPRequestHandler):
    valid_tokens = set()
    minted = 0
    sse = False  # answer MCP calls as an SSE event instead of plain JSON

    def log_message(self, *_args):
        pass

    def _send(self, code, body, headers=None):
        raw = json.dumps(body).encode()
        ctype = "application/json"
        if self.sse and self.path == "/mcp":
            raw, ctype = b"event: message\ndata: " + raw + b"\n\n", "text/event-stream"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._send(200 if self.path == "/health" else 404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        if self.path == "/api/v1/auth/login":
            if body.get("password") != PASSWORD:
                return self._send(401, {"error": "invalid email or password"})
            return self._send(200, {"user": {}}, {"Set-Cookie": "kandev_session_x=s1; Path=/"})
        if self.path == "/api/v1/auth/tokens":
            if "kandev_session_x=s1" not in (self.headers.get("Cookie") or ""):
                return self._send(401, {})
            FakeKandev.minted += 1
            token = "kandev_pat_new%d" % FakeKandev.minted
            FakeKandev.valid_tokens.add(token)
            return self._send(201, {"token": token, "record": {}})
        if self.path == "/mcp":
            auth = self.headers.get("Authorization", "")
            if auth.removeprefix("Bearer ") not in self.valid_tokens:
                return self._send(401, {})
            if body.get("method") == "initialize":
                return self._send(200, {"jsonrpc": "2.0", "id": 1, "result": {}},
                                  {"Mcp-Session-Id": "abc"})
            if body.get("method") == "tools/list":
                assert self.headers.get("Mcp-Session-Id") == "abc"
                tools = [{"name": "list_tasks_kandev"}, {"name": "create_task_kandev"}]
                return self._send(200, {"jsonrpc": "2.0", "id": 2, "result": {"tools": tools}})
            return self._send(202, {})
        return self._send(404, {})


class KandevMcpTest(unittest.TestCase):
    def setUp(self):
        FakeKandev.valid_tokens = {"kandev_pat_good"}
        FakeKandev.minted = 0
        FakeKandev.sse = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeKandev)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.env_file = os.path.join(tmp.name, ".env")
        patches = [
            mock.patch.object(kandev_mcp, "ENV_FILE", self.env_file),
            mock.patch.object(kandev_mcp, "unit_active", return_value=True),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def write_env(self, **extra):
        lines = {"KANDEV_SERVER_PORT": str(self.server.server_port),
                 "KANDEV_ADMIN_EMAIL": "me@example.com",
                 "KANDEV_ADMIN_PASSWORD": PASSWORD, **extra}
        Path(self.env_file).write_text("# kept comment\n" + "".join(
            "%s=%s\n" % kv for kv in lines.items()))

    def test_valid_token_is_used_as_is(self):
        self.write_env(KANDEV_MCP_TOKEN="kandev_pat_good")
        url, token, tools = kandev_mcp.ensure_mcp()
        self.assertEqual(token, "kandev_pat_good")
        self.assertTrue(url.endswith("/mcp"))
        self.assertIn("create_task_kandev", tools)
        self.assertEqual(FakeKandev.minted, 0)

    def test_sse_replies_are_parsed(self):
        FakeKandev.sse = True
        self.write_env(KANDEV_MCP_TOKEN="kandev_pat_good")
        self.assertEqual(len(kandev_mcp.ensure_mcp()[2]), 2)

    def test_missing_token_is_minted_and_saved(self):
        self.write_env()
        _url, token, _tools = kandev_mcp.ensure_mcp()
        self.assertEqual(token, "kandev_pat_new1")
        text = Path(self.env_file).read_text()
        self.assertIn("KANDEV_MCP_TOKEN=kandev_pat_new1", text)
        self.assertIn("# kept comment", text)

    def test_revoked_token_is_replaced_in_place(self):
        self.write_env(KANDEV_MCP_TOKEN="kandev_pat_revoked")
        kandev_mcp.ensure_mcp()
        text = Path(self.env_file).read_text()
        self.assertEqual(text.count("KANDEV_MCP_TOKEN="), 1)
        self.assertIn("KANDEV_MCP_TOKEN=kandev_pat_new1", text)

    def test_wrong_admin_password_explains_what_to_do(self):
        self.write_env(KANDEV_ADMIN_PASSWORD="wrong")
        with self.assertRaises(SystemExit) as ctx:
            kandev_mcp.ensure_mcp()
        self.assertIn("API Tokens", str(ctx.exception.code))

    def test_stopped_unit_is_started(self):
        self.write_env(KANDEV_MCP_TOKEN="kandev_pat_good")
        with mock.patch.object(kandev_mcp, "unit_active", return_value=False), \
                mock.patch.object(kandev_mcp, "start_unit") as start:
            kandev_mcp.ensure_mcp()
        start.assert_called_once()

    def test_claude_registration_skipped_when_unchanged(self):
        home = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(home))
        want = {"type": "http", "url": "http://x/mcp",
                "headers": {"Authorization": "Bearer t"}}
        Path(home, ".claude.json").write_text(json.dumps({"mcpServers": {"kandev": want}}))
        with mock.patch.dict(os.environ, {"HOME": home}), \
                mock.patch.object(kandev_mcp.subprocess, "run") as run:
            kandev_mcp.register_claude("http://x/mcp", "t")
            run.assert_not_called()
            kandev_mcp.register_claude("http://x/mcp", "t2")
        self.assertEqual(run.call_args_list[-1].args[0][:3], ["claude", "mcp", "add-json"])


if __name__ == "__main__":
    unittest.main()
