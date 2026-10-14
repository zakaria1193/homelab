"""Tests for server.py against the fake CLI in tests/fake_cli/. No test runs
the real `claude` or `agy` - see homelab-0013 acceptance criteria 6 and 7."""
import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
FAKE_CLI = ROOT / "tests" / "fake_cli"

sys.path.insert(0, str(ROOT))
import server  # noqa: E402


def make_config(**overrides):
    cfg = {
        "usage_timeout": 5,
        "claude": {
            "bin": str(FAKE_CLI / "fake-claude"),
            "args": [],
            "model_flag": "--model",
            "effort_flag": "--effort",
            "tiers": {"low": "claude-haiku-5-5", "default": "claude-sonnet-5", "deep": "claude-opus-5-5"},
        },
        "agy": {
            "bin": str(FAKE_CLI / "fake-agy"),
            "args": [],
            "model_flag": "--model",
            "effort_flag": "--effort",
            "tiers": {"low": "gemini-3.8-flash-low", "default": "gemini-3.8-flash-high", "deep": "gemini-3.8-flash-high"},
        },
    }
    for tool, patch in overrides.items():
        cfg[tool].update(patch)
    return cfg


class ServerTestCase(unittest.TestCase):
    """Boots a real server.make_server() on an ephemeral loopback port."""

    max_concurrent = 2
    timeout = 5

    def setUp(self):
        self.config = make_config()
        self.srv = server.make_server(
            self.config, "127.0.0.1", 0, self.max_concurrent, self.timeout,
        )
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()
        self._env_cleanup = []

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.thread.join(timeout=2)
        for key in self._env_cleanup:
            os.environ.pop(key, None)

    def set_fake_env(self, **kwargs):
        for key, value in kwargs.items():
            os.environ[key] = str(value)
            self._env_cleanup.append(key)

    def post(self, body, path="/v1/chat/completions"):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def get(self, path):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="GET")
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()


class HealthAndModelsTests(ServerTestCase):
    def test_healthz(self):
        status, body = self.get("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"ok")

    def test_models_lists_eight_ids(self):
        status, body = self.get("/v1/models")
        self.assertEqual(status, 200)
        ids = {m["id"] for m in json.loads(body)["data"]}
        self.assertEqual(
            ids,
            {
                "claude", "agy",
                "claude/low", "claude/default", "claude/deep",
                "agy/low", "agy/default", "agy/deep",
            },
        )

    def test_unknown_path_404(self):
        status, _ = self.get("/nope")
        self.assertEqual(status, 404)


class NonStreamingTests(ServerTestCase):
    def test_single_user_message_runs_claude_and_returns_content(self):
        status, body = self.post({
            "model": "claude", "messages": [{"role": "user", "content": "hello"}],
        })
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["object"], "chat.completion")
        argv = json.loads(data["choices"][0]["message"]["content"])
        self.assertEqual(argv[-2:], ["-p", "hello"])
        self.assertIn("claude-sonnet-5", argv)  # default tier

    def test_tool_tier_model_id_and_reasoning_effort(self):
        status, body = self.post({
            "model": "agy/deep",
            "messages": [{"role": "user", "content": "go"}],
            "reasoning_effort": "high",
        })
        self.assertEqual(status, 200)
        argv = json.loads(json.loads(body)["choices"][0]["message"]["content"])
        self.assertIn("gemini-3.8-flash-high", argv)
        self.assertEqual(argv[-4:], ["--effort", "high", "--print", "go"])

    def test_system_and_user_messages_are_flattened(self):
        status, body = self.post({
            "model": "claude",
            "messages": [
                {"role": "system", "content": "be terse"},
                {"role": "user", "content": "hi"},
            ],
        })
        self.assertEqual(status, 200)
        argv = json.loads(json.loads(body)["choices"][0]["message"]["content"])
        prompt = argv[-1]
        self.assertIn("be terse", prompt)
        self.assertIn("user: hi", prompt)

    def test_sampling_fields_are_accepted_and_ignored(self):
        status, _ = self.post({
            "model": "claude", "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.9, "max_tokens": 50,
        })
        self.assertEqual(status, 200)


class ErrorTests(ServerTestCase):
    def test_invalid_json_body_400(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            data=b"{not json", method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("expected an HTTPError")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_empty_messages_400(self):
        status, body = self.post({"model": "claude", "messages": []})
        self.assertEqual(status, 400)
        self.assertIn("messages", json.loads(body)["error"]["message"])

    def test_unknown_model_400_lists_valid_ids(self):
        status, body = self.post({"model": "bogus", "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(status, 400)
        msg = json.loads(body)["error"]["message"]
        self.assertIn("claude/deep", msg)

    def test_tools_field_400(self):
        status, _ = self.post({
            "model": "claude", "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "function"}],
        })
        self.assertEqual(status, 400)

    def test_oversized_prompt_413(self):
        huge = "x" * (121 * 1024)
        status, _ = self.post({"model": "claude", "messages": [{"role": "user", "content": huge}]})
        self.assertEqual(status, 413)

    def test_nonzero_exit_502_with_stderr_tail(self):
        self.set_fake_env(FAKE_CLI_EXIT_CODE="1", FAKE_CLI_STDERR="boom")
        status, body = self.post({"model": "claude", "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(status, 502)
        self.assertIn("boom", json.loads(body)["error"]["message"])

    def test_timeout_504(self):
        self.set_fake_env(FAKE_CLI_SLEEP="2")
        srv = server.make_server(self.config, "127.0.0.1", 0, 2, timeout=0.3)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                data=json.dumps({"model": "claude", "messages": [{"role": "user", "content": "hi"}]}).encode(),
                method="POST", headers={"Content-Type": "application/json"},
            )
            try:
                urllib.request.urlopen(req, timeout=10)
                self.fail("expected an HTTPError")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 504)
        finally:
            srv.shutdown()
            srv.server_close()
            t.join(timeout=2)


class StreamingTests(ServerTestCase):
    def _sse_lines(self, path, body):
        data = json.dumps(body).encode("utf-8")
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", path, body=data, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        status = resp.status
        raw = resp.read().decode("utf-8")
        conn.close()
        return status, [l for l in raw.split("\n\n") if l]

    def test_claude_stream_concatenates_deltas_and_ends_with_done(self):
        status, lines = self._sse_lines("/v1/chat/completions", {
            "model": "claude", "messages": [{"role": "user", "content": "hi"}], "stream": True,
        })
        self.assertEqual(status, 200)
        self.assertEqual(lines[-1], "data: [DONE]")
        text = "".join(
            json.loads(l[len("data: "):])["choices"][0]["delta"].get("content", "")
            for l in lines[:-1]
        )
        self.assertEqual(text, "Hello world")

    def test_agy_stream_concatenates_deltas(self):
        status, lines = self._sse_lines("/v1/chat/completions", {
            "model": "agy/low", "messages": [{"role": "user", "content": "hi"}], "stream": True,
        })
        self.assertEqual(status, 200)
        text = "".join(
            json.loads(l[len("data: "):])["choices"][0]["delta"].get("content", "")
            for l in lines[:-1]
        )
        self.assertEqual(text, "Hello world")


class UsageLogTests(ServerTestCase):
    """Every request appends one line per model to the usage log, with the
    token counts the CLI reported (pjm's Usage page graphs them)."""

    def setUp(self):
        super().setUp()
        import tempfile
        self.log = Path(tempfile.mkdtemp()) / "state" / "usage.jsonl"
        self.srv.aicli_usage_log = str(self.log)

    def rows(self, n):
        end = time.time() + 5   # a stream's line is written just after [DONE]
        while time.time() < end:
            if self.log.exists() and len(self.log.read_text().splitlines()) >= n:
                break
            time.sleep(0.05)
        return [json.loads(l) for l in self.log.read_text().splitlines()]

    def test_claude_without_streaming_logs_its_model_usage(self):
        status, body = self.post({"model": "claude", "messages": [{"role": "user", "content": "hello"}]})
        self.assertEqual(status, 200)
        argv = json.loads(json.loads(body)["choices"][0]["message"]["content"])
        self.assertEqual(argv[-2:], ["-p", "hello"])
        [row] = self.rows(1)
        self.assertEqual((row["tool"], row["tier"], row["model"], row["stream"]),
                         ("claude", "default", "claude-sonnet-5", False))
        self.assertEqual((row["input"], row["output"], row["cache_write"], row["cache_read"], row["total"]),
                         (3, 7, 20, 100, 130))

    def test_claude_stream_logs_one_line_per_model(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/v1/chat/completions", body=json.dumps({
            "model": "claude/deep", "messages": [{"role": "user", "content": "hi"}], "stream": True}),
            headers={"Content-Type": "application/json"})
        conn.getresponse().read()
        conn.close()
        rows = {r["model"]: r for r in self.rows(2)}
        self.assertEqual(set(rows), {"claude-sonnet-5", "claude-haiku-5-5"})
        self.assertEqual(rows["claude-sonnet-5"]["cache_read"], 50)
        self.assertTrue(rows["claude-sonnet-5"]["stream"])

    def test_agy_stream_logs_its_total(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/v1/chat/completions", body=json.dumps({
            "model": "agy/low", "messages": [{"role": "user", "content": "hi"}], "stream": True}),
            headers={"Content-Type": "application/json"})
        conn.getresponse().read()
        conn.close()
        [row] = self.rows(1)
        self.assertEqual((row["model"], row["total"], row["reported"]), ("gemini-3.8-flash-low", 5, True))

    def test_a_run_without_counts_or_a_failed_one_is_still_counted(self):
        self.post({"model": "agy", "messages": [{"role": "user", "content": "x"}]})
        self.set_fake_env(FAKE_CLI_EXIT_CODE=3)
        status, _ = self.post({"model": "claude", "messages": [{"role": "user", "content": "x"}]})
        self.assertEqual(status, 502)
        rows = self.rows(2)
        self.assertEqual([(r["tool"], r["reported"]) for r in rows], [("agy", False), ("claude", False)])

    def test_an_unwritable_log_does_not_fail_the_request(self):
        self.srv.aicli_usage_log = "/proc/no/such/usage.jsonl"
        status, _ = self.post({"model": "claude", "messages": [{"role": "user", "content": "x"}]})
        self.assertEqual(status, 200)


class ConcurrencyTests(ServerTestCase):
    max_concurrent = 1

    def test_requests_queue_rather_than_run_in_parallel(self):
        self.set_fake_env(FAKE_CLI_SLEEP="0.3")
        results = []

        def _fire():
            results.append(self.post({"model": "claude", "messages": [{"role": "user", "content": "hi"}]}))

        start = time.time()
        threads = [threading.Thread(target=_fire) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        elapsed = time.time() - start
        self.assertTrue(all(status == 200 for status, _ in results))
        self.assertGreaterEqual(elapsed, 0.55)  # sequential, not parallel


class LoopbackGuardTests(unittest.TestCase):
    def test_is_loopback_accepts_127_0_0_1_and_localhost(self):
        self.assertTrue(server._is_loopback("127.0.0.1"))
        self.assertTrue(server._is_loopback("localhost"))
        self.assertTrue(server._is_loopback("::1"))

    def test_is_loopback_rejects_non_loopback_addresses(self):
        self.assertFalse(server._is_loopback("0.0.0.0"))
        self.assertFalse(server._is_loopback("8.8.8.8"))

    def test_make_server_refuses_non_loopback_host(self):
        config = make_config()
        with self.assertRaises(SystemExit):
            server.make_server(config, "0.0.0.0", 0, 2, 5)

    def test_make_server_allows_non_loopback_when_permitted(self):
        config = make_config()
        srv = server.make_server(config, "0.0.0.0", 0, 2, 5, allow_non_loopback=True, api_key="k")
        try:
            self.assertEqual(srv.server_address[0], "0.0.0.0")
        finally:
            srv.server_close()

    def test_make_server_refuses_non_loopback_without_api_key(self):
        config = make_config()
        with self.assertRaises(SystemExit):
            server.make_server(config, "0.0.0.0", 0, 2, 5, allow_non_loopback=True)


class ApiKeyTests(ServerTestCase):
    """A caller that is not on loopback (karakeep through the docker bridge,
    a LAN host) must send the key; loopback callers need none."""

    def setUp(self):
        super().setUp()
        self.srv.aicli_api_key = "s3cret"

    def as_remote(self):
        return mock.patch.object(server, "_is_loopback", return_value=False)

    def request(self, path, key=None, body=None):
        headers = {"Content-Type": "application/json"}
        if key is not None:
            headers["Authorization"] = f"Bearer {key}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, headers=headers,
            method="POST" if body is not None else "GET",
        )
        try:
            return urllib.request.urlopen(req, timeout=10).status
        except urllib.error.HTTPError as e:
            return e.code

    def test_loopback_caller_needs_no_key(self):
        self.assertEqual(self.request("/v1/models"), 200)

    def test_remote_caller_without_key_is_refused(self):
        with self.as_remote():
            self.assertEqual(self.request("/v1/models"), 401)
            self.assertEqual(self.request("/v1/chat/completions", body={"model": "claude"}), 401)

    def test_remote_caller_with_wrong_key_is_refused(self):
        with self.as_remote():
            self.assertEqual(self.request("/v1/models", key="nope"), 401)

    def test_remote_caller_with_key_is_served(self):
        with self.as_remote():
            self.assertEqual(self.request("/v1/models", key="s3cret"), 200)

    def test_remote_healthz_needs_no_key(self):
        with self.as_remote():
            self.assertEqual(self.request("/healthz"), 200)

    def test_remote_caller_refused_when_no_key_configured(self):
        self.srv.aicli_api_key = None
        with self.as_remote():
            self.assertEqual(self.request("/v1/models", key=""), 401)


class SourceSafetyTests(unittest.TestCase):
    """Criterion 7: aicliAI never touches OAuth tokens or opens a network
    connection of its own - every vendor call goes through the CLI
    subprocess, under the user's own login."""

    FORBIDDEN = [
        ".claude/.credentials.json", ".gemini/",
        "urllib", "http.client", "socket.create_connection",
    ]
    # server.py legitimately uses socket.getaddrinfo (to validate AICLI_HOST
    # is loopback) and http.server (to BE the loopback listener), and this
    # test file legitimately drives the service with urllib/http.client as a
    # test client - none of that is a vendor call, so they're exempted here.
    ALLOWED_SELF_USES = {"socket.create_connection"}

    def test_no_source_file_reads_tokens_or_dials_out(self):
        for path in (ROOT / "aicli.py", ROOT / "server.py"):
            text = path.read_text()
            for needle in self.FORBIDDEN:
                if needle in self.ALLOWED_SELF_USES:
                    continue
                if needle in (".claude/.credentials.json", ".gemini/", "socket.create_connection"):
                    self.assertNotIn(needle, text, f"{path} references {needle!r}")
                else:
                    # urllib / http.client: forbidden as an import, not as a
                    # substring of an unrelated word.
                    self.assertNotIn(f"import {needle}", text, f"{path} imports {needle!r}")
                    self.assertNotIn(f"import {needle.split('.')[0]}", text, f"{path} imports {needle!r}")


if __name__ == "__main__":
    unittest.main()
