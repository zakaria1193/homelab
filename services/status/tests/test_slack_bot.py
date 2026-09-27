#!/usr/bin/env python3
"""The Slack ideas bot's command handling, without Slack.

slack_bolt is only imported by slack_bot.main(), so these run on the bare
stdlib like the rest of the cockpit's tests.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ideas_manager  # noqa: E402
import slack_bot  # noqa: E402
from slack_bot import parse_idea_command  # noqa: E402

MONEY = "2 - Money making.md"
FRONTMATTER = "---\ntags:\n  - myJira/backend\n---\n"


class ParseTests(unittest.TestCase):
    def test_empty_opens_the_modal(self):
        self.assertEqual(parse_idea_command("  "), {"action": "modal"})

    def test_help(self):
        self.assertEqual(parse_idea_command("help")["action"], "help")

    def test_quick_idea_with_tags_and_notes(self):
        self.assertEqual(
            parse_idea_command("Test idea from Slack #owned #SaaS — seen on reddit"),
            {"action": "create", "title": "Test idea from Slack", "notes": "seen on reddit",
             "tags": ["owned", "saas"]})

    def test_append_to_project(self):
        self.assertEqual(
            parse_idea_command("to Farah ERP: add low-stock alerts: SMS too"),
            {"action": "append", "project": "Farah ERP", "note": "add low-stock alerts: SMS too"})

    def test_a_title_starting_with_to_is_still_an_idea(self):
        self.assertEqual(parse_idea_command("todo app for couples")["action"], "create")

    def test_modal_values(self):
        values = {
            "title": {"value": {"type": "plain_text_input", "value": " Farah stock "}},
            "board": {"value": {"type": "static_select", "selected_option": {"value": MONEY}}},
            "category": {"value": {"type": "plain_text_input", "value": None}},
            "tags": {"value": {"type": "plain_text_input", "value": "#erp, retail"}},
            "owned": {"value": {"type": "checkboxes", "selected_options": [{"value": "owned"}]}},
            "notes": {"value": {"type": "plain_text_input", "value": "for the shop"}},
        }
        self.assertEqual(slack_bot.parse_modal_values(values), {
            "title": "Farah stock", "target_file": MONEY, "category": slack_bot.INBOX_CATEGORY,
            "tags": ["erp", "retail", "owned"], "notes": "for the shop"})


class HandleTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._env = os.environ.get("PROJECT_IDEAS_DIR")
        os.environ["PROJECT_IDEAS_DIR"] = self.dir
        self._sync = ideas_manager.trigger_obsidian_sync
        ideas_manager.trigger_obsidian_sync = lambda reason="": None
        with open(os.path.join(self.dir, MONEY), "w", encoding="utf-8") as f:
            f.write(FRONTMATTER + "## Active\n- [ ] Farah ERP #owned\n\n---\n\n## Warning\ntext\n")

    def tearDown(self):
        ideas_manager.trigger_obsidian_sync = self._sync
        if self._env is None:
            os.environ.pop("PROJECT_IDEAS_DIR", None)
        else:
            os.environ["PROJECT_IDEAS_DIR"] = self._env
        shutil.rmtree(self.dir)

    def read(self):
        with open(os.path.join(self.dir, MONEY), encoding="utf-8") as f:
            return f.read()

    def test_quick_idea_lands_in_the_inbox_untagged(self):
        reply = slack_bot.handle_text("Test idea from Slack #owned")
        self.assertIn("Added *Test idea from Slack*", reply)
        self.assertIn("`#owned`", reply)
        idea = [i for i in ideas_manager.list_all_ideas() if i["title"] == "Test idea from Slack"][0]
        self.assertEqual((idea["status"], idea["category"], idea["tags"]), ("untagged", "Inbox", ["owned"]))
        # The new section goes above the '---' rule, not inside the frontmatter.
        content = self.read()
        self.assertTrue(content.startswith(FRONTMATTER))
        self.assertLess(content.index("## Inbox"), content.index("## Warning"))

    def test_append_note(self):
        reply = slack_bot.handle_text("to farah: add low-stock alerts")
        self.assertIn("Added to *Farah ERP*", reply)
        self.assertIn("- **Note via Slack (", self.read())
        self.assertIn("No card matches", slack_bot.handle_text("to nothing like it: x"))

    def test_modal_lists_the_backends(self):
        view = slack_bot.build_idea_modal()
        board = [b for b in view["blocks"] if b["block_id"] == "board"][0]
        self.assertEqual([o["value"] for o in board["element"]["options"]], [MONEY])
        self.assertIsNone(slack_bot.handle_text(""))


if __name__ == "__main__":
    unittest.main()
