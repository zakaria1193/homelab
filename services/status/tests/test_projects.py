#!/usr/bin/env python3
"""Tests for the /projects list: which entries count as live web projects."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit.config import DOWN, UNKNOWN, UP  # noqa: E402
from cockpit.snapshot import projects  # noqa: E402


def svc(name, state=UP, link="", remote="", detail="active (running)"):
    return {"name": name, "state": state, "link": link, "remote": remote,
            "detail": detail, "note": "extra field that must not leak"}


class ProjectsTest(unittest.TestCase):
    def payload(self, *services):
        return {"groups": [{"name": "G", "services": list(services), "launchers": []}]}

    def test_keeps_only_status_and_links(self):
        rows = projects(self.payload(svc("jellyfin", link="http://h:8096", remote="https://media.x")))
        self.assertEqual(rows, [{"name": "jellyfin", "state": UP,
                                 "link": "http://h:8096", "remote": "https://media.x"}])

    def test_entries_without_a_web_ui_are_left_out(self):
        rows = projects(self.payload(svc("docker"), svc("claude-rc", remote="https://claude.ai/code")))
        self.assertEqual(rows, [])

    def test_down_project_stays_listed(self):
        rows = projects(self.payload(svc("kandev", state=DOWN, link="http://h:3040", detail="failed")))
        self.assertEqual([r["state"] for r in rows], [DOWN])

    def test_not_installed_unit_is_not_live(self):
        rows = projects(self.payload(
            svc("hermes-ai", state=UNKNOWN, link="http://h:8100", detail="unit not installed")))
        self.assertEqual(rows, [])

    def test_config_order_is_kept_across_groups(self):
        payload = {"groups": [
            {"name": "A", "services": [svc("b", link="http://b")], "launchers": []},
            {"name": "B", "services": [svc("a", link="http://a")], "launchers": []},
        ]}
        self.assertEqual([r["name"] for r in projects(payload)], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
