#!/usr/bin/env python3
"""Tests for adding/removing preconfigured AI sessions in services.conf.

Each test runs against a throwaway git repo, never the real services.conf."""

import configparser
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit import actions  # noqa: E402

CONF = """[DEFAULT]
pi = 192.168.1.11

[jellyfin]
group = Media
link = http://localhost:8096
"""


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


class AiSessionsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = tmp.name
        self.conf = os.path.join(self.repo, "services.conf")
        Path(self.conf).write_text(CONF)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "add", "services.conf")
        git(self.repo, "commit", "-qm", "init")
        self.workspace = os.path.join(self.repo, "ws")
        os.mkdir(self.workspace)
        for patch in (mock.patch.object(actions, "CONFIG_PATH", self.conf),
                      mock.patch.object(actions, "REPO_ROOT", self.repo),
                      mock.patch.object(actions, "invalidate", lambda: None)):
            patch.start()
            self.addCleanup(patch.stop)

    def sections(self):
        parser = configparser.ConfigParser()
        parser.read(self.conf)
        return parser.sections()

    def test_add_then_delete(self):
        res = actions.add_ai_session("my-ws", self.workspace, "notes")
        self.assertTrue(res["ok"], res)
        self.assertIn("my-ws", self.sections())
        self.assertTrue(actions.delete_ai_session("my-ws")["ok"])
        self.assertEqual(self.sections(), ["jellyfin"])

    def test_a_percent_sign_does_not_break_the_config(self):
        # services.conf is read with ConfigParser's % interpolation: a bare %
        # would make every later read of the file raise.
        res = actions.add_ai_session("pct", self.workspace, "100% done")
        self.assertTrue(res["ok"], res)
        parser = configparser.ConfigParser()
        parser.read(self.conf)
        self.assertEqual(parser.get("pct", "note"), "100% done")

    def test_a_newline_cannot_inject_a_section(self):
        res = actions.add_ai_session("x", self.workspace, "hi\n[evil]\ncommand = rm -rf ~")
        self.assertFalse(res["ok"])
        self.assertEqual(self.sections(), ["jellyfin"])

    def test_only_page_added_sessions_can_be_deleted(self):
        res = actions.delete_ai_session("jellyfin")
        self.assertFalse(res["ok"])
        self.assertIn("jellyfin", self.sections())

    def test_commit_takes_services_conf_only(self):
        other = os.path.join(self.repo, "other.txt")
        Path(other).write_text("staged by someone else\n")
        git(self.repo, "add", "other.txt")
        actions.add_ai_session("my-ws", self.workspace)
        self.assertEqual(git(self.repo, "show", "--name-only", "--format=", "HEAD").split(), ["services.conf"])
        self.assertIn("A  other.txt", git(self.repo, "status", "--short"))


if __name__ == "__main__":
    unittest.main()
