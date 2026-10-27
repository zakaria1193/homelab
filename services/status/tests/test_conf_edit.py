#!/usr/bin/env python3
"""conf_edit is the only code allowed to write services.conf: a lock, value
validation, a temp file, and a re-parse before the real file is replaced."""

import configparser
import glob
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cockpit import conf_edit  # noqa: E402

CONF = """[DEFAULT]
pi = 192.168.1.11

[jellyfin]
group = Media
link = http://localhost:8096
"""


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


class ConfEditTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = tmp.name
        self.conf = os.path.join(self.repo, "services.conf")
        Path(self.conf).write_text(CONF, encoding="utf-8")
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "add", "services.conf")
        git(self.repo, "commit", "-qm", "init")

    def read(self):
        return Path(self.conf).read_text(encoding="utf-8")

    def sections(self):
        parser = configparser.ConfigParser()
        parser.read(self.conf)
        return parser.sections()

    def temp_files(self):
        return glob.glob(os.path.join(self.repo, ".services.conf.*"))

    # --- add -------------------------------------------------------------- #
    def test_add_appends_a_section(self):
        res = conf_edit.add_section(self.conf, "my-ws", [("group", "AI Sessions"), ("dir", "/tmp")])
        self.assertTrue(res["ok"], res)
        self.assertIn("my-ws", self.sections())
        parser = configparser.ConfigParser()
        parser.read(self.conf)
        self.assertEqual(parser.get("my-ws", "dir"), "/tmp")

    def test_duplicate_add_refused(self):
        res = conf_edit.add_section(self.conf, "jellyfin", [("group", "Media")])
        self.assertFalse(res["ok"])
        self.assertEqual(self.read(), CONF)

    def test_bad_section_name_refused(self):
        res = conf_edit.add_section(self.conf, "evil]\n[worse", [("group", "x")])
        self.assertFalse(res["ok"])
        self.assertEqual(self.read(), CONF)

    def test_crlf_value_refused(self):
        res = conf_edit.add_section(self.conf, "x", [("note", "hi\n[evil]\ncommand = rm -rf ~")])
        self.assertFalse(res["ok"])
        self.assertEqual(self.read(), CONF)
        self.assertEqual(self.temp_files(), [])

    def test_percent_round_trips(self):
        res = conf_edit.add_section(self.conf, "pct", [("note", "100% done")])
        self.assertTrue(res["ok"], res)
        parser = configparser.ConfigParser()
        parser.read(self.conf)
        self.assertEqual(parser.get("pct", "note"), "100% done")

    # --- remove ------------------------------------------------------------ #
    def test_remove_drops_the_section_and_is_byte_identical_after_an_add(self):
        before = self.read()
        self.assertTrue(conf_edit.add_section(self.conf, "my-ws", [("group", "AI Sessions")])["ok"])
        self.assertTrue(conf_edit.remove_section(self.conf, "my-ws")["ok"])
        self.assertEqual(self.read(), before)

    def test_remove_drops_the_comment_block_above_it(self):
        self.assertTrue(
            conf_edit.add_section(
                self.conf, "farah", [("group", "AI")], comment_lines=["# a comment about farah"]
            )["ok"]
        )
        self.assertIn("# a comment about farah", self.read())
        self.assertTrue(conf_edit.remove_section(self.conf, "farah")["ok"])
        self.assertNotIn("farah", self.read())
        self.assertNotIn("# a comment about farah", self.read())

    def test_remove_leaves_one_blank_line_between_remaining_sections(self):
        conf_edit.add_section(self.conf, "a", [("group", "AI")])
        conf_edit.add_section(self.conf, "b", [("group", "AI")])
        conf_edit.remove_section(self.conf, "a")
        text = self.read()
        self.assertNotIn("\n\n\n", text)
        self.assertIn("[b]", text)

    def test_missing_remove_refused(self):
        res = conf_edit.remove_section(self.conf, "no-such-section")
        self.assertFalse(res["ok"])
        self.assertEqual(self.read(), CONF)

    # --- re-parse guard ------------------------------------------------------ #
    def test_badly_escaped_percent_is_refused_and_leaves_no_trace(self):
        # Bypass the module's own escaping to prove the re-parse catches it.
        res = conf_edit._write_checked(self.conf, CONF + "\n[bad]\nnote = 100% done\n")
        self.assertFalse(res[0])
        self.assertEqual(self.read(), CONF)
        self.assertEqual(self.temp_files(), [])

    # --- commit -------------------------------------------------------------- #
    def test_commits_only_when_a_message_is_given(self):
        conf_edit.add_section(self.conf, "no-commit", [("group", "AI")])
        self.assertEqual(git(self.repo, "log", "--oneline").count("\n"), 1)

        conf_edit.add_section(
            self.conf, "with-commit", [("group", "AI")],
            commit_message="feat: add with-commit", repo_root=self.repo,
        )
        log = git(self.repo, "log", "--oneline")
        self.assertEqual(log.count("\n"), 2)
        self.assertIn("feat: add with-commit", log)

    def test_commit_takes_services_conf_only(self):
        other = os.path.join(self.repo, "other.txt")
        Path(other).write_text("staged by someone else\n")
        git(self.repo, "add", "other.txt")
        conf_edit.add_section(
            self.conf, "my-ws", [("group", "AI")],
            commit_message="feat: add my-ws", repo_root=self.repo,
        )
        self.assertEqual(git(self.repo, "show", "--name-only", "--format=", "HEAD").split(), ["services.conf"])
        self.assertIn("A  other.txt", git(self.repo, "status", "--short"))

    # --- concurrency -------------------------------------------------------- #
    def test_concurrent_adds_all_land(self):
        names = ["sec-%d" % i for i in range(20)]
        threads = [
            threading.Thread(target=conf_edit.add_section, args=(self.conf, n, [("group", "AI")]))
            for n in names
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        sections = self.sections()
        for n in names:
            self.assertIn(n, sections)
        self.assertEqual(self.temp_files(), [])


if __name__ == "__main__":
    unittest.main()
