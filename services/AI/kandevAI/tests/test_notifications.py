#!/usr/bin/env python3
"""Tests for the Slack notification provider config (notifications/slack.json)
and the pure waiting_steps() helper in upsert_provider.py.

No Kandev instance and no Slack token are needed to run these.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notifications"))
import upsert_provider  # noqa: E402

NOTIFICATIONS_DIR = Path(__file__).resolve().parent.parent / "notifications"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_json(path):
    return json.loads(path.read_text())


class WaitingStepsTest(unittest.TestCase):
    def test_matches_the_current_workflows(self):
        fixture = load_json(FIXTURES_DIR / "workflow_steps.json")
        names = set()
        for workflow in fixture["workflows"]:
            names.update(step["name"] for step in upsert_provider.waiting_steps(workflow["steps"]))
        self.assertEqual(names, {"Spec feedback", "Human check", "Review"})

    def test_excludes_inbox_auto_start_and_completing_steps(self):
        steps = [
            {"name": "Raw", "position": 0, "complete_task_on_enter": False, "events": {}},
            {"name": "Spec", "position": 1, "complete_task_on_enter": False,
             "events": {"on_enter": [{"type": "auto_start_agent"}]}},
            {"name": "Spec feedback", "position": 2, "complete_task_on_enter": False, "events": {}},
            {"name": "Done", "position": 3, "complete_task_on_enter": True, "events": {}},
        ]
        self.assertEqual([s["name"] for s in upsert_provider.waiting_steps(steps)], ["Spec feedback"])


class ConfigCoverageTest(unittest.TestCase):
    def setUp(self):
        self.config = load_json(NOTIFICATIONS_DIR / "slack.json")
        self.step_names_lower = {name.lower() for name in self.config["config"]["step_names"]}

    def test_every_waiting_step_is_covered(self):
        fixture = load_json(FIXTURES_DIR / "workflow_steps.json")
        waiting = set()
        for workflow in fixture["workflows"]:
            waiting.update(step["name"] for step in upsert_provider.waiting_steps(workflow["steps"]))
        missing = {name for name in waiting if name.lower() not in self.step_names_lower}
        self.assertEqual(missing, set(), "waiting steps missing from slack.json step_names: %s" % missing)

    def test_no_token_value_in_the_committed_config(self):
        payload = json.dumps(self.config)
        self.assertNotIn("xox", payload)


if __name__ == "__main__":
    unittest.main()
