#!/usr/bin/env python3
"""Keep the Slack notification provider in sync with slack.json (idempotent
upsert), and check that step_names covers every step where a card waits on
the user (see notifications/slack.json and the "Slack notifications"
section of the README).

    notifications/upsert_provider.py           # PATCH or POST slack.json
    notifications/upsert_provider.py --check   # drift check, no write

Auth: KANDEV_PAT env var if set, else the token kandev_mcp.py already keeps
in .env (minted from KANDEV_ADMIN_EMAIL / KANDEV_ADMIN_PASSWORD on first use).
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import kandev_mcp  # noqa: E402

HTTP_TIMEOUT = 10
PROVIDERS_PATH = "/api/v1/notification-providers"


def waiting_steps(steps):
    """Steps of one workflow where a card waits for the user: no
    auto_start_agent on enter, not the inbox (position 0), and not
    complete_task_on_enter."""
    result = []
    for step in steps:
        on_enter = step.get("events", {}).get("on_enter", [])
        auto_starts = any(event.get("type") == "auto_start_agent" for event in on_enter)
        if auto_starts or step.get("position") == 0 or step.get("complete_task_on_enter"):
            continue
        result.append(step)
    return result


class HttpClient:
    """Thin JSON wrapper around urllib, swapped for a fake in tests."""

    def __init__(self, base_url, token):
        self.base_url = base_url
        self.token = token

    def request(self, method, path, body=None):
        headers = {"Authorization": "Bearer %s" % self.token, "Content-Type": "application/json"}
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as res:
            raw = res.read()
            return json.loads(raw) if raw else {}


def upsert(client, payload):
    """GET existing providers, PATCH the one whose name matches payload["name"],
    else POST a new one. Returns (verb, response)."""
    existing = client.request("GET", PROVIDERS_PATH)
    match = next((p for p in existing.get("providers", []) if p["name"] == payload["name"]), None)
    if match is None:
        return "POST", client.request("POST", PROVIDERS_PATH, payload)
    return "PATCH", client.request("PATCH", "%s/%s" % (PROVIDERS_PATH, match["id"]), payload)


def load_payload():
    return json.loads((HERE / "slack.json").read_text())


def resolve_token(env):
    return (os.environ.get("KANDEV_PAT")
            or env.get(kandev_mcp.TOKEN_KEY)
            or kandev_mcp.mint_token(env))


def fetch_live_workflows(client):
    """Every workspace -> workflow -> steps from the live API, shaped like
    tests/fixtures/workflow_steps.json."""
    workflows = []
    for workspace in client.request("GET", "/api/v1/workspaces").get("workspaces", []):
        workspace_workflows = client.request(
            "GET", "/api/v1/workspaces/%s/workflows" % workspace["id"]).get("workflows", [])
        for workflow in workspace_workflows:
            snapshot = client.request("GET", "/api/v1/workflows/%s/snapshot" % workflow["id"])
            workflows.append({
                "workspace": workspace["name"],
                "workflow": workflow["name"],
                "steps": snapshot.get("steps", []),
            })
    return workflows


def missing_waiting_steps(workflows, step_names):
    """Waiting-step names (see waiting_steps()) not covered, case-insensitively,
    by step_names. Maps each missing name to the workspace/workflow it was
    seen in, so --check can say where it came from."""
    configured = {name.lower() for name in step_names}
    missing = {}
    for workflow in workflows:
        location = "%s/%s" % (workflow["workspace"], workflow["workflow"])
        for step in waiting_steps(workflow["steps"]):
            if step["name"].lower() not in configured:
                missing.setdefault(step["name"], set()).add(location)
    return missing


def check(client, step_names):
    """Drift check: live waiting steps not in step_names. Prints and returns
    an exit code; makes no write."""
    missing = missing_waiting_steps(fetch_live_workflows(client), step_names)
    if not missing:
        print("[notifications] step_names covers every waiting step")
        return 0
    for name, locations in sorted(missing.items()):
        print("[notifications] missing from step_names: %r (seen in %s)"
              % (name, ", ".join(sorted(locations))))
    return 1


def main(argv):
    env = kandev_mcp.read_env()
    kandev_mcp.ensure_running(env)
    token = resolve_token(env)
    client = HttpClient(kandev_mcp.base_url(env), token)
    payload = load_payload()
    if "--check" in argv[1:]:
        return check(client, payload["config"]["step_names"])
    verb, response = upsert(client, payload)
    print("[notifications] %s %s (id=%s)" % (verb, response.get("name"), response.get("id")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
