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


class FakeClient:
    """Records calls and answers GET with a canned provider list, like the
    real /api/v1/notification-providers would."""

    def __init__(self, existing_providers):
        self.existing_providers = existing_providers
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET":
            return {"providers": self.existing_providers, "apprise_available": False, "events": []}
        return {**(body or {}), "id": "provider-1"}


class FakeLiveClient:
    """Answers the GET sequence fetch_live_workflows() makes against a live
    Kandev: /workspaces, each workspace's /workflows, then each workflow's
    /snapshot. `workflows` is the same shape as workflow_steps.json."""

    def __init__(self, workflows):
        self.workflows = workflows

    def request(self, method, path, body=None):
        assert method == "GET"
        if path == "/api/v1/workspaces":
            names = sorted({w["workspace"] for w in self.workflows})
            return {"workspaces": [{"id": name, "name": name} for name in names]}
        if path.startswith("/api/v1/workspaces/") and path.endswith("/workflows"):
            workspace = path.split("/")[-2]
            matches = [w for w in self.workflows if w["workspace"] == workspace]
            return {"workflows": [{"id": "%s-%s" % (workspace, w["workflow"]), "name": w["workflow"]}
                                   for w in matches]}
        if path.startswith("/api/v1/workflows/") and path.endswith("/snapshot"):
            workflow_id = path.split("/")[-2]
            workspace, _, name = workflow_id.rpartition("-")
            match = next(w for w in self.workflows
                         if w["workspace"] == workspace and w["workflow"] == name)
            return {"steps": match["steps"]}
        raise AssertionError("unexpected request: %s %s" % (method, path))


class UpsertTest(unittest.TestCase):
    def setUp(self):
        self.payload = load_json(NOTIFICATIONS_DIR / "slack.json")

    def test_posts_when_no_provider_with_that_name_exists(self):
        client = FakeClient(existing_providers=[])
        verb, response = upsert_provider.upsert(client, self.payload)
        self.assertEqual(verb, "POST")
        self.assertEqual(response["id"], "provider-1")
        self.assertEqual(client.calls[-1], ("POST", "/api/v1/notification-providers", self.payload))

    def test_patches_the_existing_provider_by_name(self):
        client = FakeClient(existing_providers=[{"id": "existing-42", "name": "Slack", "type": "slack"}])
        verb, response = upsert_provider.upsert(client, self.payload)
        self.assertEqual(verb, "PATCH")
        self.assertEqual(response["id"], "provider-1")
        self.assertEqual(client.calls[-1],
                          ("PATCH", "/api/v1/notification-providers/existing-42", self.payload))

    def test_payload_sent_matches_slack_json_exactly(self):
        client = FakeClient(existing_providers=[])
        upsert_provider.upsert(client, self.payload)
        _, _, sent_body = client.calls[-1]
        self.assertEqual(sent_body, self.payload)

    def test_no_token_value_is_ever_sent_in_the_payload(self):
        client = FakeClient(existing_providers=[{"id": "existing-42", "name": "Slack", "type": "slack"}])
        upsert_provider.upsert(client, self.payload)
        for _, _, body in client.calls:
            self.assertNotIn("xox", json.dumps(body))


class DriftCheckTest(unittest.TestCase):
    def setUp(self):
        self.fixture = load_json(FIXTURES_DIR / "workflow_steps.json")["workflows"]
        self.step_names = load_json(NOTIFICATIONS_DIR / "slack.json")["config"]["step_names"]

    def test_current_fixture_has_no_missing_step(self):
        client = FakeLiveClient(self.fixture)
        self.assertEqual(upsert_provider.check(client, self.step_names), 0)

    def test_a_new_waiting_step_not_in_step_names_fails(self):
        workflows = [dict(w) for w in self.fixture]
        workflows[1] = dict(workflows[1])
        workflows[1]["steps"] = workflows[1]["steps"] + [
            {"name": "New waiting step", "position": 99,
             "complete_task_on_enter": False, "events": {}},
        ]
        client = FakeLiveClient(workflows)
        self.assertEqual(upsert_provider.check(client, self.step_names), 1)

    def test_missing_waiting_steps_reports_the_workflow_it_came_from(self):
        workflows = [{
            "workspace": "kandev", "workflow": "Kanban",
            "steps": [{"name": "New waiting step", "position": 1,
                       "complete_task_on_enter": False, "events": {}}],
        }]
        missing = upsert_provider.missing_waiting_steps(workflows, self.step_names)
        self.assertEqual(missing, {"New waiting step": {"kandev/Kanban"}})


if __name__ == "__main__":
    unittest.main()
