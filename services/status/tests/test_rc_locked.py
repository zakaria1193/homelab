#!/usr/bin/env python3
"""A workspace marked `rc_locked` never gets a Remote Control server.

The Home Assistant config is the case that needs it: Home Assistant runs on the
Pi, so a Claude or Antigravity RC server on the Dell checkout makes no sense.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cockpit import config  # noqa: E402
from cockpit.handler import StatusHandler  # noqa: E402
from cockpit.pages.main import PAGE  # noqa: E402
from cockpit.workspaces import merge  # noqa: E402

HA_DIR = "/home/zfadli/my_repos/home-assistant-config"


class TestRcLocked(unittest.TestCase):
    def test_home_assistant_config_is_locked(self):
        self.assertIn("Raspberry Pi", config.rc_locked_reason(HA_DIR))

    def test_other_workspaces_are_not_locked(self):
        self.assertEqual(config.rc_locked_reason(config.REPO_ROOT), "")

    def test_lock_follows_the_config(self):
        with tempfile.TemporaryDirectory() as d:
            conf = os.path.join(d, "services.conf")
            with open(conf, "w") as f:
                f.write("[ws]\ngroup = AI Sessions\ntype = shell\ndir = %s\nrc_locked = elsewhere\n" % d)
            with mock.patch.object(config, "CONFIG_PATH", conf):
                self.assertEqual(config.rc_locked_reason(d + "/"), "elsewhere")

    def test_row_carries_the_lock(self):
        rows = merge([{"name": "ha", "dir": HA_DIR, "rc_locked": "on the Pi"}], [], [], [])
        self.assertEqual(rows[0]["rc_locked"], "on the Pi")

    def test_page_shows_a_lock_not_add_rc(self):
        self.assertIn("if (l.rc_locked)", PAGE)
        self.assertIn("🔒 no RC", PAGE)

    def test_api_refuses_create_and_validate(self):
        for path in ("/api/claude-rc/create", "/api/claude-rc/validate",
                     "/api/antigravity-rc/create", "/api/antigravity-rc/validate"):
            h = StatusHandler.__new__(StatusHandler)
            sent = {}
            h._send = lambda code, body, ctype: sent.update(code=code, body=body)
            with mock.patch("claude_rc.create") as cc, mock.patch("antigravity_rc.create") as ac:
                h._rc_api(path, {"workspace": HA_DIR, "name": "ha"})
                cc.assert_not_called()
                ac.assert_not_called()
            result = json.loads(sent["body"])
            self.assertFalse(result["ok"], path)
            self.assertIn("locked", result["message"], path)


if __name__ == "__main__":
    unittest.main()
