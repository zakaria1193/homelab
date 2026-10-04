#!/usr/bin/env node
// Keep a Kandev automation in sync with its JSON definition (idempotent).
//
//   automations/upsert_automation.mjs automations/scrum_master.json
//   automations/upsert_automation.mjs --check automations/scrum_master.json
//
// Kandev edits automations over its WebSocket API only, hence Node (built-in
// WebSocket) rather than Python. Auth: KANDEV_PAT if set, else the
// KANDEV_MCP_TOKEN that kandev_mcp.py keeps in .env. KANDEV_URL overrides
// http://localhost:3040.

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

// Fields copied verbatim from the definition onto the automation.
const FIELDS = [
  "name",
  "description",
  "enabled",
  "max_concurrent_runs",
  "continuation_policy",
  "task_mode",
  "repository_mode",
  "task_title_template",
];

export function desiredAutomation(def, workspaceId, profileId) {
  const out = { workspace_id: workspaceId, agent_profile_id: profileId };
  for (const f of FIELDS) out[f] = def[f];
  out.prompt = Array.isArray(def.prompt) ? def.prompt.join("\n") : def.prompt;
  return out;
}

export function desiredTrigger(def) {
  return {
    type: "scheduled",
    enabled: true,
    config: { cron_expression: def.cron_expression, timezone: def.timezone || "UTC" },
  };
}

// Returns the WebSocket requests that bring `existing` (or nothing) to the
// definition, as [action, payload] pairs. No pair means already in sync.
export function plan(def, existing, workspaceId, profileId) {
  const want = desiredAutomation(def, workspaceId, profileId);
  const trigger = desiredTrigger(def);
  if (!existing) {
    return [["automation.create", { ...want, triggers: [trigger] }]];
  }
  const ops = [];
  const changed = {};
  for (const [k, v] of Object.entries(want)) {
    if (k !== "workspace_id" && existing[k] !== v) changed[k] = v;
  }
  if (Object.keys(changed).length) ops.push(["automation.update", { id: existing.id, ...changed }]);
  const scheduled = (existing.triggers || []).find((t) => t.type === "scheduled");
  if (!scheduled) {
    ops.push(["automation.trigger.add", { automation_id: existing.id, ...trigger }]);
  } else {
    const cfg = typeof scheduled.config === "string" ? JSON.parse(scheduled.config) : scheduled.config || {};
    const same =
      cfg.cron_expression === trigger.config.cron_expression &&
      (cfg.timezone || "UTC") === trigger.config.timezone &&
      scheduled.enabled === true;
    if (!same) {
      ops.push(["automation.trigger.update", { id: scheduled.id, config: trigger.config, enabled: true }]);
    }
  }
  return ops;
}

export function findProfile(agents, agentName, profileName) {
  const agent = agents.find((a) => a.name === agentName);
  return agent?.profiles?.find((p) => p.name === profileName)?.id;
}

function token() {
  if (process.env.KANDEV_PAT) return process.env.KANDEV_PAT;
  const env = readFileSync(join(HERE, "..", ".env"), "utf8");
  const m = env.match(/^KANDEV_MCP_TOKEN=(.+)$/m);
  if (!m) throw new Error("no KANDEV_PAT and no KANDEV_MCP_TOKEN in .env (run make mcp)");
  return m[1].trim();
}

async function http(base, tok, path) {
  const res = await fetch(base + path, { headers: { Authorization: `Bearer ${tok}` } });
  if (!res.ok) throw new Error(`GET ${path}: ${res.status}`);
  return res.json();
}

function wsClient(url) {
  const ws = new WebSocket(url);
  const pending = new Map();
  let seq = 0;
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    const p = pending.get(msg.id);
    if (!p) return;
    pending.delete(msg.id);
    if (msg.type === "error") p.reject(new Error(`${msg.action}: ${JSON.stringify(msg.payload)}`));
    else p.resolve(msg.payload);
  };
  const open = new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = () => reject(new Error(`cannot connect to ${url.replace(/token=[^&]+/, "token=***")}`));
  });
  return {
    async call(action, payload) {
      await open;
      const id = String(++seq);
      const done = new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
      ws.send(JSON.stringify({ id, type: "request", action, payload }));
      return done;
    },
    close: () => ws.close(),
  };
}

async function main(argv) {
  const check = argv.includes("--check");
  const file = argv.find((a) => !a.startsWith("--"));
  if (!file) throw new Error("usage: upsert_automation.mjs [--check] <definition.json>");
  const def = JSON.parse(readFileSync(file, "utf8"));
  const base = process.env.KANDEV_URL || "http://localhost:3040";
  const tok = token();

  const workspaces = (await http(base, tok, "/api/v1/workspaces")).workspaces;
  const workspace = workspaces.find((w) => w.name === def.workspace);
  if (!workspace) throw new Error(`no workspace named ${def.workspace}`);
  const agents = await http(base, tok, "/api/v1/agents");
  const profileId = findProfile(agents.agents || agents, def.agent, def.agent_profile);
  if (!profileId) throw new Error(`no profile "${def.agent_profile}" on agent ${def.agent}`);

  const ws = wsClient(`${base.replace(/^http/, "ws")}/ws?token=${encodeURIComponent(tok)}`);
  try {
    const list = await ws.call("automation.list", { workspace_id: workspace.id });
    const existing = (list.automations || list).find((a) => a.name === def.name);
    const ops = plan(def, existing, workspace.id, profileId);
    if (!ops.length) return console.log(`[OK] ${def.name} in sync`);
    for (const [action, payload] of ops) {
      if (check) {
        console.log(`[DRIFT] ${action} ${Object.keys(payload).join(", ")}`);
        continue;
      }
      await ws.call(action, payload);
      console.log(`[OK] ${action}`);
    }
    if (check) process.exitCode = 1;
  } finally {
    ws.close();
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).catch((err) => {
    console.error(`[ERROR] ${err.message}`);
    process.exit(1);
  });
}
