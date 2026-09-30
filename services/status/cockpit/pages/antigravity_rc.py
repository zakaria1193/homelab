"""/antigravity-rc: Antigravity Remote Control instances."""

AGY_RC_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Antigravity Remote Control servers · __TITLE__</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --raise: #1c2430; --border: #30363d; --text: #e6edf3;
    --muted: #8b949e; --up: #3fb950; --down: #f85149; --warn: #d29922; --unknown: #6e7681;
    --accent: #58a6ff;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --panel: #fff; --raise: #eef2f6; --border: #d0d7de;
            --text: #1f2328; --muted: #636c76; --accent: #0969da; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5
    ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  a { color: inherit; }
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
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Antigravity Remote Control servers</h1>
    <a class="back" href="/">&larr; __TITLE__</a>
  </header>
  <p class="lede">Always-on Antigravity daemons (<code>agy-remote-control[-&lt;name&gt;].service</code>)
  exposing your workspaces to <a href="https://antigravity.google.com/" target="_blank"
  rel="noopener">antigravity.google.com</a>. Drive remote sessions from any browser without running local commands.</p>

  <h2>Instances</h2>
  <div id="list">loading…</div>
  <pre id="out"></pre>

  <h2>New instance</h2>
  <form id="new" autocomplete="off">
    <div class="row">
      <div>
        <label for="name">Name</label>
        <input id="name" name="name" placeholder="myproject" spellcheck="false">
      </div>
      <div>
        <label for="workspace">Workspace directory</label>
        <input id="workspace" name="workspace" placeholder="/home/zfadli/my_repos/myproject"
          spellcheck="false">
      </div>
    </div>
    <div class="hint" id="check">The directory must already exist on this machine.</div>
    <div class="row" style="margin-top: 10px;">
      <div>
        <label for="port">Hub Port (optional)</label>
        <input id="port" name="port" placeholder="auto" type="number" min="1024" max="65535">
      </div>
      <div>
        <label for="session">Machine / instance label</label>
        <input id="session" name="session" placeholder="myproject">
      </div>
    </div>
    <button type="submit" style="margin-top: 15px;">Create and start instance</button>
  </form>
</div>
<script>
const out = document.getElementById("out");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const qs = encodeURIComponent;

function say(r) {
  out.textContent = (r.message ? r.message + "\\n\\n" : "") + (r.output || "");
}

async function post(url, payload) {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    return await res.json();
  } catch (err) {
    return { ok: false, message: "Request failed", output: String(err) };
  }
}

function card(i) {
  const acts = `
    <button data-verb="start" data-name="${esc(i.name)}">start</button>
    <button data-verb="restart" data-name="${esc(i.name)}">restart</button>
    <button data-verb="stop" data-name="${esc(i.name)}">stop</button>
    <button data-verb="upgrade" data-name="${esc(i.name)}">upgrade</button>
    <button data-verb="doctor" data-name="${esc(i.name)}">doctor</button>
    ${i.removable ? `<button class="danger" data-verb="delete" data-name="${esc(i.name)}">delete</button>` : ""}`;
  return `<div class="card ${esc(i.state)}">
    <div class="top">
      <span class="dot ${esc(i.state)}"></span>
      <span class="who">${esc(i.label)}</span>
      <span class="unit">${esc(i.unit)}</span>
    </div>
    <div class="facts">
      <div>Workspace: <b>${esc(i.workspace)}</b></div>
      <div>Dashboard: <a href="${esc(i.dashboard_url)}" target="_blank" rel="noopener"><b>${esc(i.dashboard_url)}</b></a></div>
      <div>Hub port: <b>127.0.0.1:${esc(i.hub_port)}</b></div>
      <div>Status: <b>${esc(i.detail)}</b></div>
    </div>
    <div class="acts">
      ${acts}
      <a class="btn" href="/logs?service=${qs(i.name ? "antigravity-rc-" + i.name : "antigravity-rc")}">logs</a>
      <a class="btn" href="${esc(i.dashboard_url)}" target="_blank" rel="noopener">open dashboard</a>
    </div>
  </div>`;
}

async function load() {
  const data = await (await fetch("/api/antigravity-rc", { cache: "no-store" })).json();
  document.getElementById("list").innerHTML = data.instances.map(card).join("");
}

document.getElementById("list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-verb]");
  if (!button) return;
  const { verb, name } = button.dataset;
  if (verb === "delete" && !confirm(`Stop ${name}, remove unit and env files?`)) return;
  document.querySelectorAll("#list button").forEach(b => { b.disabled = true; });
  out.textContent = `${verb} ${name || "default"}…`;
  say(await post("/api/antigravity-rc/" + (verb === "delete" ? "delete" : "action"), { verb, name }));
  await load();
  document.querySelectorAll("#list button").forEach(b => { b.disabled = false; });
});

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
    const r = await post("/api/antigravity-rc/validate", { workspace });
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

document.getElementById("new").addEventListener("submit", async (event) => {
  event.preventDefault();
  let name = document.getElementById("name").value.trim();
  const workspace = document.getElementById("workspace").value.trim();
  if (!name && workspace) {
    const parts = workspace.replace(/[\\/]+$/, "").split("/");
    name = (parts[parts.length - 1] || "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  }
  if (!workspace) {
    hint.className = "hint bad";
    hint.textContent = "Workspace directory is required.";
    return;
  }
  const button = event.target.querySelector("button[type=submit]");
  button.disabled = true;
  out.textContent = `Creating ${name} in ${workspace}…`;
  say(await post("/api/antigravity-rc/create", {
    name,
    workspace,
    port: document.getElementById("port").value.trim(),
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
"""
