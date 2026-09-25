#!/usr/bin/env python3
"""How the cockpit names Claude Remote Control instances.

The unnamed instance - plain `.env`, unit `claude-rc-ai` - is the homelab
repo's own always-on server. The page calls it `homelab`, after its workspace,
like every other card; `default` was a name for the file layout, not for a
workspace.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class ClaudeRcNames(unittest.TestCase):
    def setUp(self):
        # A scratch RC dir, so the assertions do not depend on which instances
        # this machine happens to have.
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        os.environ["STATUS_RC_DIR"] = self.dir.name
        for name in (".env", ".env.farah.example"):
            Path(self.dir.name, name).write_text("RC_WORKDIR=/tmp\n", encoding="utf-8")
        for module in [m for m in sys.modules if m == "claude_rc"]:
            del sys.modules[module]
        import claude_rc  # noqa: E402
        self.rc = claude_rc

    def test_unnamed_instance_is_labelled_homelab(self):
        self.assertEqual(self.rc.describe("")["label"], "homelab")
        self.assertEqual(self.rc.describe("")["unit"], "claude-rc-ai")
        # Still the unnamed one underneath: the label is display only.
        self.assertEqual(self.rc.describe("")["name"], "")
        self.assertTrue(self.rc.describe("")["env_file"].endswith(".env"))

    def test_named_instance_keeps_its_own_label(self):
        self.assertEqual(self.rc.describe("farah")["label"], "farah")

    def test_homelab_is_not_free_as_a_new_instance_name(self):
        # Two cards both reading "homelab" would be unreadable, so the create
        # form rejects the name the default already goes by.
        self.assertTrue(self.rc.validate_name("homelab"))
        self.assertEqual(self.rc.validate_name("myrepos"), "")


if __name__ == "__main__":
    unittest.main()
