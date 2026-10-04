import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { findProfile, plan } from "../automations/upsert_automation.mjs";

const def = JSON.parse(readFileSync(new URL("../automations/scrum_master.json", import.meta.url)));

function inSync(overrides = {}) {
  return {
    id: "a1",
    name: def.name,
    description: def.description,
    enabled: true,
    max_concurrent_runs: 1,
    continuation_policy: "reuse_thread",
    task_mode: "automation_run",
    repository_mode: "none",
    task_title_template: def.task_title_template,
    agent_profile_id: "p-agy",
    prompt: def.prompt.join("\n"),
    triggers: [{ id: "t1", type: "scheduled", enabled: true, config: { cron_expression: def.cron_expression, timezone: "UTC" } }],
    ...overrides,
  };
}

test("creates the automation with its schedule when missing", () => {
  const [[action, payload], ...rest] = plan(def, undefined, "ws1", "p-agy");
  assert.equal(action, "automation.create");
  assert.equal(rest.length, 0);
  assert.equal(payload.workspace_id, "ws1");
  assert.equal(payload.agent_profile_id, "p-agy");
  assert.deepEqual(payload.triggers, [
    { type: "scheduled", enabled: true, config: { cron_expression: def.cron_expression, timezone: "UTC" } },
  ]);
});

test("does nothing when already in sync", () => {
  assert.deepEqual(plan(def, inSync(), "ws1", "p-agy"), []);
});

test("updates only the changed fields, e.g. moving off a Claude profile", () => {
  const ops = plan(def, inSync({ agent_profile_id: "p-claude", prompt: "old" }), "ws1", "p-agy");
  assert.deepEqual(ops, [["automation.update", { id: "a1", agent_profile_id: "p-agy", prompt: def.prompt.join("\n") }]]);
});

test("fixes a drifted or missing schedule", () => {
  const drifted = inSync({ triggers: [{ id: "t1", type: "scheduled", enabled: true, config: '{"cron_expression":"*/45 * * * *","timezone":"UTC"}' }] });
  assert.deepEqual(plan(def, drifted, "ws1", "p-agy"), [
    ["automation.trigger.update", { id: "t1", config: { cron_expression: def.cron_expression, timezone: "UTC" }, enabled: true }],
  ]);
  const [[action]] = plan(def, inSync({ triggers: [] }), "ws1", "p-agy");
  assert.equal(action, "automation.trigger.add");
});

test("the prompt alerts on errored cards and never runs shell commands", () => {
  const prompt = def.prompt.join("\n");
  assert.match(prompt, /ALERT/);
  assert.match(prompt, /e0d98bab-6213-43a7-8674-1876a2fdf29b/); // alert cards land in Human check
  assert.match(prompt, /never edit files or run shell commands/);
  assert.notEqual(def.agent, "claude-acp");
});

test("finds a profile by agent and profile name", () => {
  const agents = [{ name: "antigravity-acp", profiles: [{ id: "p-agy", name: "Scrum master - agy" }] }];
  assert.equal(findProfile(agents, "antigravity-acp", "Scrum master - agy"), "p-agy");
  assert.equal(findProfile(agents, "claude-acp", "Scrum master - agy"), undefined);
});
