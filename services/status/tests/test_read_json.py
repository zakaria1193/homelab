#!/usr/bin/env python3
"""StatusHandler._read_json: the only thing between a cross-site page and the
management POSTs (terminals, cron, sessions). Same origin means same host AND
port, and the body must really be declared JSON."""

import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cockpit.handler import StatusHandler  # noqa: E402

BODY = json.dumps({"a": 1}).encode()


def read(headers):
    h = StatusHandler.__new__(StatusHandler)
    h.headers = {"Content-Length": str(len(BODY)), **headers}
    h.rfile = io.BytesIO(BODY)
    return h._read_json()


class ReadJsonTest(unittest.TestCase):
    def test_same_origin_lan(self):
        self.assertEqual(read({"Content-Type": "application/json", "Host": "192.168.1.10:8300",
                               "Origin": "http://192.168.1.10:8300"}), {"a": 1})

    def test_same_origin_through_tunnel(self):
        self.assertEqual(read({"Content-Type": "application/json; charset=utf-8",
                               "Host": "homelab.zakariafadli.com",
                               "Origin": "https://homelab.zakariafadli.com"}), {"a": 1})

    def test_default_port_on_host_header_still_matches(self):
        self.assertEqual(read({"Content-Type": "application/json",
                               "Host": "homelab.zakariafadli.com:443",
                               "Origin": "https://homelab.zakariafadli.com"}), {"a": 1})

    def test_no_origin_is_accepted(self):
        self.assertEqual(read({"Content-Type": "application/json", "Host": "x:8300"}), {"a": 1})

    def test_other_port_on_same_host_is_refused(self):
        self.assertIsNone(read({"Content-Type": "application/json", "Host": "192.168.1.10:8300",
                                "Origin": "http://192.168.1.10:8096"}))

    def test_other_host_is_refused(self):
        self.assertIsNone(read({"Content-Type": "application/json", "Host": "192.168.1.10:8300",
                                "Origin": "http://evil.example"}))

    def test_json_hidden_in_a_simple_content_type_is_refused(self):
        # `text/plain; application/json` needs no CORS preflight
        self.assertIsNone(read({"Content-Type": "text/plain; application/json",
                                "Host": "192.168.1.10:8300"}))


if __name__ == "__main__":
    unittest.main()
