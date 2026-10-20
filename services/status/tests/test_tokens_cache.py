import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit import tokens


class _Resp:
    """Stands in for the urllib response urlopen() hands back."""

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()
        self.headers = {}

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestCachePermissionsAndAtomicity(unittest.TestCase):
    def test_save_leaves_cache_mode_0600(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "nested" / "cache.json"
            with mock.patch.object(tokens, "CACHE_FILE", cache):
                tokens._update_cache({"x": {"id": "x", "status": "active"}})
                self.assertTrue(cache.exists())
                self.assertEqual(cache.stat().st_mode & 0o777, 0o600)

    def test_save_uses_os_replace_not_in_place_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.json"
            with mock.patch.object(tokens, "CACHE_FILE", cache), \
                 mock.patch("os.replace", wraps=__import__("os").replace) as replace:
                tokens._update_cache({"x": {"id": "x", "status": "active"}})
                replace.assert_called_once()

    def test_corrupt_cache_reads_as_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.json"
            cache.write_text("not json{{{")
            with mock.patch.object(tokens, "CACHE_FILE", cache):
                self.assertEqual(tokens._load_cache(), {})
                # the next save rewrites it whole
                tokens._update_cache({"x": {"id": "x", "status": "active"}})
                self.assertEqual(json.loads(cache.read_text()), {"x": {"id": "x", "status": "active"}})

    def test_two_writers_both_keep_their_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.json"
            with mock.patch.object(tokens, "CACHE_FILE", cache):
                tokens._update_cache({"a": {"id": "a", "status": "active"}})
                tokens._update_cache({"b": {"id": "b", "status": "active"}})
                data = json.loads(cache.read_text())
                self.assertIn("a", data)
                self.assertIn("b", data)


class TestTestAllConcurrency(unittest.TestCase):
    def test_two_concurrent_runs_send_each_token_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.json"

            def fake_urlopen(req, timeout=None):
                return _Resp({"success": True, "result": {"status": "active"}, "ok": True,
                               "data": [], "results": [], "message": "x", "login": "x"})

            def fake_read_env_val(_path, var):
                return "http://127.0.0.1:9/v1" if var == "OPENAI_BASE_URL" else "secret"

            with mock.patch.object(tokens, "CACHE_FILE", cache), \
                 mock.patch.object(tokens, "_read_env_val", side_effect=fake_read_env_val), \
                 mock.patch.object(tokens.urllib.request, "urlopen", side_effect=fake_urlopen) as op:
                results_by_thread = []

                def run():
                    results_by_thread.append(tokens.test_all())

                t1 = threading.Thread(target=run)
                t2 = threading.Thread(target=run)
                t1.start()
                t2.start()
                t1.join()
                t2.join()

                self.assertEqual(op.call_count, len(tokens.TOKEN_DEFS))
                for results in results_by_thread:
                    self.assertEqual(len(results), len(tokens.TOKEN_DEFS))


if __name__ == "__main__":
    unittest.main()
