"""/claude-rc: Claude Remote Control instances."""

from .theme import THEME

RC_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude Remote Control servers · __TITLE__</title>
<style>
  {THEME}
  .wrap { max-width: 900px; margin: 0 auto; padding: 24px 18px 64px; }
  header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 16px; }
  h1 { font-size: 22px; margin: 0; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--muted); margin: 30px 0 10px; font-weight: 600; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .lede { color: var(--muted); font-size: 13px; margin: 10px 0 0; max-width: 66ch; }
  .dot { width: 9px; height: 9px; border-radius: 50%; flex: none; background: var(--unknown); }
  .dot.up { background: var(--up); } .dot.down { background: var(--down); }
  .dot.warn { background: var(--warn); }
  .card { background: var(--panel); border: 1px solid var(--border); border-left-width: 3px;
    border-radius: 8px; padding: 13px 15px; margin-top: 10px; }
  .card.up { border-left-color: var(--up); } .card.down { border-left-color: var(--down); }
  .card.warn { border-left-color: var(--warn); }
  .card.unknown { border-left-color: var(--unknown); }
  .top { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
  .who { font-weight: 600; font-size: 15px; }
  .unit { color: var(--muted); font-size: 12px; font-family: ui-monospace, SFMono-Regular,
    Menlo, Consolas, monospace; }
  .facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 2px 16px; margin-top: 8px; font-size: 12px; color: var(--muted); }
  .facts b { color: var(--text); font-weight: 500; overflow-wrap: anywhere; }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  button, .btn { background: var(--panel); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 4px 11px; font-size: 12px; cursor: pointer;
    text-decoration: none; display: inline-flex; align-items: center; gap: 5px; }
  button:hover, .btn:hover { border-color: var(--muted); background: var(--raise); }
  button:disabled { opacity: 0.45; cursor: default; }
  button.danger:hover { border-color: var(--down); color: var(--down); }
  .warnrow { color: var(--warn); font-size: 12px; margin-top: 8px; }
  form { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 15px; }
  .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 12px; }
  label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
  input, select { width: 100%; background: var(--bg); color: var(--text); font: inherit;
    font-size: 14px; border: 1px solid var(--border); border-radius: 6px; padding: 6px 9px; }
  input:focus, select:focus { outline: none; border-color: var(--accent); }
  .hint { font-size: 12px; margin-top: 6px; min-height: 18px; color: var(--muted); }
  .hint.bad { color: var(--down); } .hint.good { color: var(--up); }
  pre { background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
    padding: 10px 12px; font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    white-space: pre-wrap; overflow-wrap: anywhere; margin: 10px 0 0; max-height: 320px;
    overflow: auto; }
  pre:empty { display: none; }
  footer { margin-top: 40px; color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Claude Remote Control servers</h1>
    <a class="back" href="/">&larr; __TITLE__</a>
  </header>
  <p class="lede">One <code>claude remote-control</code> process serves exactly one
  directory, so every workspace you want always-on is its own instance: its own
  <code>.env.&lt;name&gt;</code> and its own <code>claude-rc-ai-&lt;name&gt;</code> unit.
  Reach any of them from <a href="https://claude.ai/code" target="_blank"
  rel="noopener">claude.ai/code</a> or the Claude mobile app.</p>

  <h2>Instances</h2>
  <div id="list">loading…</div>
  <pre id="out"></pre>

  <h2>New instance</h2>
  <form id="new" autocomplete="off">
    <div class="row">
      <div>
        <label for="name">Name</label>
        <input id="name" name="name" placeholder="notes" spellcheck="false">
      </div>
      <div>
        <label for="workspace">Workspace directory</label>
        <input id="workspace" name="workspace" placeholder="/home/you/my_repos/notes"
          spellcheck="false">
      </div>
    </div>
    <div class="hint" id="check">The directory must already exist on this machine.</div>
    <div class="row">
      <div>
        <label for="spawn">Spawn mode</label>
        <select id="spawn"><option>worktree</option><option>same-dir</option>
          <option>session</option></select>
      </div>
      <div>
        <label for="permission">Permission mode</label>
        <select id="permission">__PERMISSIONS__</select>
      </div>
      <div>
        <label for="capacity">Capacity</label>
        <input id="capacity" type="number" min="1" max="256" value="8">
      </div>
      <div>
        <label for="session">Session name</label>
        <input id="session" placeholder="same as the name" spellcheck="false">
      </div>
    </div>
    <div class="acts"><button id="create" type="submit">Create &amp; start</button></div>
  </form>
  <footer>Instances live in <code>services/AI/claudeRcAI</code>; creating one writes its
  env files, starts the unit and registers it on the cockpit.</footer>
</div>
<script>
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const qs = encodeURIComponent;
const MANAGE = __MANAGE__;
const out = document.getElementById("out");

const post = (path, body) => fetch(path, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
}).then(r => r.json());

function say(result) {
  out.textContent = [result.message, result.output].filter(Boolean).join("\\n\\n");
  out.scrollIntoView({ block: "nearest" });
}

function card(i) {
  const acts = MANAGE ? `
    <button data-verb="restart" data-name="${esc(i.name)}">restart</button>
    <button data-verb="start" data-name="${esc(i.name)}">start</button>
    <button data-verb="stop" data-name="${esc(i.name)}">stop</button>
    ${i.removable ? `<button class="danger" data-verb="delete"
      data-name="${esc(i.name)}">delete</button>` : ""}` : "";
  return `<div class="card ${esc(i.state)}">
    <div class="top"><span class="dot ${esc(i.state)}"></span>
      <span class="who">${esc(i.label)}</span>
      <span class="unit">${esc(i.unit)}</span></div>
    <div class="facts">
      <span>state <b>${esc(i.detail)}</b></span>
      <span>workspace <b>${esc(i.workspace)}</b></span>
      <span>spawn <b>${esc(i.spawn)}</b></span>
      <span>capacity <b>${esc(i.capacity)}</b></span>
      <span>permissions <b>${esc(i.permission)}</b></span>
      <span>env <b>${esc(i.env_file)}</b></span>
    </div>
    ${i.workspace_exists ? "" :
      `<div class="warnrow">workspace is missing on this machine</div>`}
    ${i.needs_sudo ? `<div class="warnrow">system unit and no passwordless sudo:
      use “in a shell”, which can ask for your password.</div>` : ""}
    <div class="acts">
      ${acts}
      <a class="btn" href="/logs?service=${qs("rc:logs:" + i.name)}">logs</a>
      <a class="btn" href="/terminal?service=${qs("rc:restart:" + i.name)}">restart in a shell</a>
      <a class="btn" href="https://claude.ai/code" target="_blank" rel="noopener">open</a>
    </div>
  </div>`;
}

async function load() {
  const data = await (await fetch("/api/claude-rc", { cache: "no-store" })).json();
  document.getElementById("list").innerHTML = data.instances.map(card).join("");
}

document.getElementById("list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-verb]");
  if (!button) return;
  const { verb, name } = button.dataset;
  if (verb === "delete" && !confirm(
      `Stop claude-rc-ai-${name}, remove its unit and delete its env files?`)) return;
  document.querySelectorAll("#list button").forEach(b => { b.disabled = true; });
  out.textContent = `${verb} ${name || "homelab"}…`;
  say(await post("/api/claude-rc/" + (verb === "delete" ? "delete" : "action"),
                 { name, verb }));
  await load();
  document.querySelectorAll("#list button").forEach(b => { b.disabled = false; });
});

// Path checking as you type: the same check the create call runs, so the form
// never hands you a surprise after the fact.
let timer = null;
const hint = document.getElementById("check");
function verify() {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const workspace = document.getElementById("workspace").value.trim();
    if (!workspace) {
      hint.className = "hint";
      hint.textContent = "The directory must already exist on this machine.";
      return;
    }
    const nameInput = document.getElementById("name");
    const r = await post("/api/claude-rc/validate",
                         { workspace, spawn: document.getElementById("spawn").value });
    hint.className = "hint " + (r.ok ? "good" : "bad");
    hint.textContent = r.ok ? (r.message || "OK — " + r.path) : r.message;
    if (r.ok && r.deduced_name && (!nameInput.value.trim() || nameInput.dataset.autofilled)) {
      nameInput.value = r.deduced_name;
      nameInput.dataset.autofilled = "true";
    }
  }, 250);
}
document.getElementById("workspace").addEventListener("input", verify);
document.getElementById("name").addEventListener("input", () => {
  delete document.getElementById("name").dataset.autofilled;
});
document.getElementById("spawn").addEventListener("change", verify);
// The AI Sessions table's "+ RC" link names the workspace it came from.
const preset = new URLSearchParams(location.search).get("workspace");
if (preset) {
  document.getElementById("workspace").value = preset;
  verify();
}

document.getElementById("new").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.getElementById("create");
  button.disabled = true;
  out.textContent = "creating…";
  let nameVal = document.getElementById("name").value.trim();
  const wsVal = document.getElementById("workspace").value.trim();
  if (!nameVal && wsVal) {
    const parts = wsVal.replace(/[\\/]+$/, "").split("/");
    nameVal = (parts[parts.length - 1] || "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  }
  say(await post("/api/claude-rc/create", {
    name: nameVal,
    workspace: wsVal,
    spawn: document.getElementById("spawn").value,
    permission: document.getElementById("permission").value,
    capacity: document.getElementById("capacity").value,
    session: document.getElementById("session").value.trim(),
  }));
  button.disabled = false;
  await load();
});

load();
setInterval(load, 10000);
</script>
</body>
</html>
""".replace("{THEME}", THEME)
