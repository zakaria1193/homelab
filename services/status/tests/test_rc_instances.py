#!/usr/bin/env python3
"""Shared RC-instance lifecycle (cockpit/rc_instances.py), exercised through
both configurations that use it: claude_rc and antigravity_rc.

Every test works on a temp instance directory and a temp services.conf; `make`
is stubbed (no real systemd, no real Makefile) so these never touch the host.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CONF = """[DEFAULT]
pi = 192.168.1.11

[jellyfin]
group = Media
link = http://localhost:8096
"""


def _fake_run(argv, **kwargs):
    """Stands in for subprocess.run: `make` always succeeds, systemd units are
    never installed, `sudo -n true` always fails (no passwordless sudo)."""
    if argv[0] == "make":
        return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")
    if argv[0] == "systemctl":
        return subprocess.CompletedProcess(argv, 0, stdout="LoadState=not-found\n", stderr="")
    if argv[0] == "sudo":
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
    raise AssertionError("unexpected subprocess.run call: %r" % (argv,))


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


class RcInstancesTestBase(unittest.TestCase):
    """Common temp-dir, temp-config and `make`-stub plumbing for both kinds."""

    module_name = None  # "cockpit.claude_rc" or "cockpit.antigravity_rc"
    dir_env = None  # "STATUS_RC_DIR" / "STATUS_AGY_RC_DIR"

    def setUp(self):
        self.instance_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.instance_dir.cleanup)
        self.repo = tempfile.TemporaryDirectory()
        self.addCleanup(self.repo.cleanup)
        self.conf = os.path.join(self.repo.name, "services.conf")
        Path(self.conf).write_text(CONF, encoding="utf-8")
        _git(self.repo.name, "init", "-q")
        _git(self.repo.name, "config", "user.email", "t@t")
        _git(self.repo.name, "config", "user.name", "t")

        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        _git(self.workspace.name, "init", "-q")

        os.environ[self.dir_env] = self.instance_dir.name
        for module in [m for m in sys.modules if m == self.module_name]:
            del sys.modules[module]
        self.rc = __import__(self.module_name, fromlist=["_"])

        self._run_patch = mock.patch("cockpit.rc_instances.subprocess.run", side_effect=_fake_run)
        self._run_patch.start()
        self.addCleanup(self._run_patch.stop)

    def conf_text(self):
        return Path(self.conf).read_text(encoding="utf-8")


class ClaudeRcInstancesTest(RcInstancesTestBase):
    module_name = "cockpit.claude_rc"
    dir_env = "STATUS_RC_DIR"

    def test_create_writes_env_files_starts_and_registers(self):
        result = self.rc.create(
            "farah", self.workspace.name, "worktree", "8", "auto", "", config_path=self.conf,
        )
        self.assertTrue(result["ok"], result)
        self.assertTrue(os.path.isfile(os.path.join(self.instance_dir.name, ".env.farah")))
        self.assertTrue(
            os.path.isfile(os.path.join(self.instance_dir.name, ".env.farah.example"))
        )
        body = Path(self.instance_dir.name, ".env.farah").read_text(encoding="utf-8")
        self.assertIn("RC_WORKDIR=%s" % os.path.realpath(self.workspace.name), body)
        self.assertIn("[claude-rc-farah]", self.conf_text())

    def test_delete_stops_and_removes_env_and_section(self):
        self.rc.create("farah", self.workspace.name, "worktree", "8", "auto", "",
                        config_path=self.conf)
        result = self.rc.delete("farah", config_path=self.conf)
        self.assertTrue(result["ok"], result)
        self.assertFalse(os.path.isfile(os.path.join(self.instance_dir.name, ".env.farah")))
        self.assertFalse(
            os.path.isfile(os.path.join(self.instance_dir.name, ".env.farah.example"))
        )
        self.assertNotIn("[claude-rc-farah]", self.conf_text())

    def test_unknown_verb_is_refused(self):
        self.rc.create("farah", self.workspace.name, "worktree", "8", "auto", "",
                        config_path=self.conf)
        result = self.rc.run("reboot", "farah")
        self.assertFalse(result["ok"])

    def test_unknown_instance_is_refused(self):
        result = self.rc.run("start", "nope")
        self.assertFalse(result["ok"])

    def test_worktree_spawn_needs_a_git_repo(self):
        plain = tempfile.TemporaryDirectory()
        self.addCleanup(plain.cleanup)
        result = self.rc.create("farah", plain.name, "worktree", "8", "auto", "",
                                 config_path=self.conf)
        self.assertFalse(result["ok"])
        self.assertIn("git repository", result["message"])

    def test_same_dir_spawn_does_not_need_a_git_repo(self):
        plain = tempfile.TemporaryDirectory()
        self.addCleanup(plain.cleanup)
        result = self.rc.create("farah", plain.name, "same-dir", "8", "auto", "",
                                 config_path=self.conf)
        self.assertTrue(result["ok"], result)

    def test_homelab_is_reserved(self):
        self.assertNotEqual(self.rc.validate_name("homelab"), "")

    def test_describe_keys(self):
        self.rc.create("farah", self.workspace.name, "worktree", "8", "auto", "",
                        config_path=self.conf)
        row = self.rc.describe("farah")
        for key in (
            "name", "label", "unit", "env_file", "has_env", "workspace",
            "workspace_exists", "spawn", "capacity", "permission", "session",
            "prefix", "state", "detail", "scope", "needs_sudo", "removable",
        ):
            self.assertIn(key, row, key)
        self.assertEqual(row["unit"], "claude-rc-ai-farah")
        self.assertTrue(row["removable"])


class AntigravityRcInstancesTest(RcInstancesTestBase):
    module_name = "cockpit.antigravity_rc"
    dir_env = "STATUS_AGY_RC_DIR"

    def test_create_writes_env_files_starts_and_registers(self):
        result = self.rc.create("farah", self.workspace.name, "", "", config_path=self.conf)
        self.assertTrue(result["ok"], result)
        self.assertTrue(os.path.isfile(os.path.join(self.instance_dir.name, ".env.farah")))
        self.assertTrue(
            os.path.isfile(os.path.join(self.instance_dir.name, ".env.farah.example"))
        )
        body = Path(self.instance_dir.name, ".env.farah").read_text(encoding="utf-8")
        self.assertIn("AGY_RC_WORKDIR=%s" % os.path.realpath(self.workspace.name), body)
        self.assertIn("[antigravity-rc-farah]", self.conf_text())

    def test_delete_stops_and_removes_env_and_section(self):
        self.rc.create("farah", self.workspace.name, "", "", config_path=self.conf)
        result = self.rc.delete("farah", config_path=self.conf)
        self.assertTrue(result["ok"], result)
        self.assertFalse(os.path.isfile(os.path.join(self.instance_dir.name, ".env.farah")))
        self.assertNotIn("[antigravity-rc-farah]", self.conf_text())

    def test_unknown_verb_is_refused(self):
        self.rc.create("farah", self.workspace.name, "", "", config_path=self.conf)
        result = self.rc.run("reboot", "farah")
        self.assertFalse(result["ok"])

    def test_unknown_instance_is_refused(self):
        result = self.rc.run("start", "nope")
        self.assertFalse(result["ok"])

    # Antigravity does not check for a git repo the way Claude's `worktree`
    # spawn mode does: any readable directory is a valid workspace.
    def test_plain_directory_is_a_valid_workspace(self):
        plain = tempfile.TemporaryDirectory()
        self.addCleanup(plain.cleanup)
        result = self.rc.create("farah", plain.name, "", "", config_path=self.conf)
        self.assertTrue(result["ok"], result)

    def test_describe_keys(self):
        self.rc.create("farah", self.workspace.name, "", "", config_path=self.conf)
        row = self.rc.describe("farah")
        for key in (
            "name", "label", "unit", "env_file", "has_env", "workspace",
            "workspace_exists", "instance_name", "hub_port", "dashboard_url",
            "log_file", "state", "detail", "scope", "removable",
        ):
            self.assertIn(key, row, key)
        self.assertEqual(row["unit"], "agy-remote-control-farah.service")
        self.assertTrue(row["removable"])


if __name__ == "__main__":
    unittest.main()
