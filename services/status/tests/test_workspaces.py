#!/usr/bin/env python3
"""How the AI Sessions tab joins terminals and Remote Control servers.

A launcher and an RC server that point at the same directory are one
workspace, one row. An RC server nobody launches gets its own row, with
terminals only when some configured entry opens in its directory.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cockpit.workspaces import merge  # noqa: E402


def launcher(name, dir, **extra):
    return dict({"name": name, "dir": dir, "note": "", "command": "claude",
                 "icon": "briefcase", "custom": False}, **extra)


def claude(name, workspace, state="up"):
    return {"name": name, "label": name or "homelab", "unit": "claude-rc-ai" + ("-" + name if name else ""),
            "workspace": workspace, "state": state, "detail": state}


def agy(name, workspace):
    return {"name": name, "instance_name": "homelab", "unit": "antigravity-cli-daemon.service",
            "workspace": workspace, "state": "up", "detail": "active",
            "dashboard_url": "https://antigravity.google.com/"}


class Workspaces(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for d in ("homelab", "notes", "farah", "lonely"):
            (self.root / d).mkdir()
        self.d = {d: str(self.root / d) for d in ("homelab", "notes", "farah", "lonely")}

    def test_launcher_and_rc_in_same_dir_share_a_row(self):
        rows = merge([launcher("homelab", self.d["homelab"])],
                     [claude("", self.d["homelab"])], [agy("", self.d["homelab"])], [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["service"], "homelab")
        self.assertEqual([r["agent"] for r in rows[0]["rc"]], ["claude", "antigravity"])

    def test_join_ignores_trailing_slashes_and_symlinks(self):
        link = self.root / "link"
        link.symlink_to(self.d["homelab"])
        rows = merge([launcher("homelab", str(link))],
                     [claude("", self.d["homelab"] + "/")], [], [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["rc"]), 1)

    def test_launcher_without_rc_keeps_its_row(self):
        rows = merge([launcher("notes", self.d["notes"])], [], [], [])
        self.assertEqual(rows[0]["rc"], [])
        self.assertTrue(rows[0]["terminal"])

    def test_rc_only_workspace_borrows_the_entry_that_opens_there(self):
        checks = [{"name": "claude-rc-farah", "dir": self.d["farah"], "note": "always-on farah"}]
        rows = merge([], [claude("farah", self.d["farah"])], [], checks)
        self.assertEqual(rows[0]["name"], "farah")
        self.assertEqual(rows[0]["service"], "claude-rc-farah")
        self.assertEqual(rows[0]["note"], "always-on farah")
        self.assertTrue(rows[0]["terminal"])

    def test_rc_only_workspace_with_no_entry_has_no_terminals(self):
        rows = merge([], [claude("lonely", self.d["lonely"])], [], [])
        self.assertEqual(rows[0]["service"], "")
        self.assertFalse(rows[0]["terminal"])

    def test_launchers_first_then_rc_only_rows(self):
        rows = merge([launcher("notes", self.d["notes"]), launcher("homelab", self.d["homelab"])],
                     [claude("", self.d["homelab"]), claude("farah", self.d["farah"])], [], [])
        self.assertEqual([r["name"] for r in rows], ["notes", "homelab", "farah"])

    def test_terminals_off_means_no_terminal_buttons_anywhere(self):
        checks = [{"name": "claude-rc-farah", "dir": self.d["farah"], "note": ""}]
        rows = merge([launcher("notes", self.d["notes"])],
                     [claude("farah", self.d["farah"])], [], checks, terminal_enabled=False)
        self.assertFalse(any(r["terminal"] for r in rows))

    def test_rc_links_point_at_logs_and_console(self):
        rows = merge([], [claude("farah", self.d["farah"])], [agy("x", self.d["farah"])], [])
        cl, ag = rows[0]["rc"]
        self.assertEqual(cl["logs"], "/logs?service=rc:logs:farah")
        self.assertEqual(cl["web"], "https://claude.ai/code")
        self.assertEqual(ag["logs"], "/logs?service=antigravity-rc-x")


if __name__ == "__main__":
    unittest.main()
