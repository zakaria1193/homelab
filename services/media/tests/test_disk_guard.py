#!/usr/bin/env python3
"""Disk guard decisions against a fake Transmission - no network, no real disk."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import disk_guard as g  # noqa: E402

GB = g.GB


class FakeTx:
    def __init__(self, torrents):
        self.torrents, self.calls = torrents, []

    def call(self, method, **a):
        self.calls.append((method, a))
        if method == "torrent-get":
            return {"torrents": [{"id": i, "status": s} for i, s in self.torrents.items()]}
        if method == "torrent-stop":
            for i in a["ids"]:
                self.torrents[i] = 0
        elif method == "torrent-start":
            for i in a["ids"]:
                self.torrents[i] = 4
        return {}


class GuardTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        g.STATE, g.LOG = Path(d.name) / "s.json", Path(d.name) / "l.log"
        self.sent = []
        g.notify = lambda *a: self.sent.append(a)

    def test_slack_on_pause_once_and_on_resume(self):
        tx = FakeTx({1: 4})
        g.run(50 * GB, tx)
        g.run(40 * GB, tx)  # already paused: no second alert
        self.assertEqual([m[0] for m in self.sent], ["error"])
        g.run(130 * GB, tx)
        self.assertEqual([m[0] for m in self.sent], ["error", "ok"])

    def test_pauses_active_only_when_under_floor(self):
        tx = FakeTx({1: 4, 2: 0, 3: 6})  # downloading, stopped by hand, seeding
        self.assertEqual(g.run(50 * GB, tx), "paused")
        self.assertIn(("torrent-stop", {"ids": [1, 3]}), tx.calls)

    def test_stays_paused_inside_margin_then_resumes_own_only(self):
        tx = FakeTx({1: 4, 2: 0})
        g.run(50 * GB, tx)
        tx.calls.clear()
        self.assertEqual(g.run(110 * GB, tx), "ok")  # above floor, below floor+margin
        self.assertEqual(tx.calls, [])
        self.assertEqual(g.run(130 * GB, tx), "resumed")
        self.assertEqual(tx.calls, [("torrent-start", {"ids": [1]})])

    def test_healthy_disk_touches_nothing(self):
        tx = FakeTx({1: 4})
        self.assertEqual(g.run(300 * GB, tx), "ok")
        self.assertEqual([c for c in tx.calls if c[0] != "torrent-get"], [])


if __name__ == "__main__":
    unittest.main()
