#!/usr/bin/env python3
"""Tests for what a session's claude / agy buttons type into the terminal.

An entry can set `claude_command` / `agy_command` to run a launcher instead of
the bare CLI (a launcher that prepares the session first);
entries without it must keep typing plain `claude` / `agy`.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import terminal  # noqa: E402


def init_for(check, cmd):
    with mock.patch.object(terminal.tmux_manager, "is_available", return_value=False):
        _argv, _cwd, _label, init, _session = terminal.build_command(
            check, "/tmp", "/bin/zsh", cmd=cmd)
    return init


class LaunchCommandTest(unittest.TestCase):
    def test_plain_entry_types_the_bare_cli(self):
        check = {"name": "homelab", "type": "shell", "command": "claude"}
        self.assertEqual(init_for(check, "claude"), "claude\n")
        self.assertEqual(init_for(check, "agy"), "agy\n")

    def test_override_replaces_the_cli(self):
        check = {
            "name": "mcp-board", "type": "shell", "command": "x.py check",
            "claude_command": "x.py claude", "agy_command": "x.py agy",
        }
        self.assertEqual(init_for(check, "claude"), "x.py claude\n")
        self.assertEqual(init_for(check, "agy"), "x.py agy\n")

    def test_empty_override_falls_back(self):
        check = {"name": "n", "type": "shell", "command": "c", "claude_command": ""}
        self.assertEqual(init_for(check, "claude"), "claude\n")

    def test_shell_button_still_runs_command(self):
        check = {"name": "mcp-board", "type": "shell", "command": "x.py check",
                 "claude_command": "x.py claude"}
        self.assertEqual(init_for(check, ""), "x.py check\n")


if __name__ == "__main__":
    unittest.main()
