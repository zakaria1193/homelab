"""/tmux: the cockpit's tmux sessions."""

from .theme import THEME

TMUX_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>tmux sessions · __TITLE__</title>
<style>
  {THEME}
  .wrap { max-width: 960px; margin: 0 auto; padding: 24px 18px 64px; }
  header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 16px; }
  h1 { font-size: 22px; margin: 0; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--muted); margin: 30px 0 10px; font-weight: 600; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .lede { color: var(--muted); font-size: 13px; margin: 10px 0 0; max-width: 70ch; }
  .dot { width: 9px; height: 9px; border-radius: 50%; flex: none; background: var(--unknown); }
  .dot.up { background: var(--up); } .dot.down { background: var(--down); }
  .dot.warn { background: var(--warn); }
  .card { background: var(--panel); border: 1px solid var(--border); border-left-width: 3px;
    border-radius: 8px; padding: 13px 15px; margin-top: 10px; }
  .card.up { border-left-color: var(--up); } .card.down { border-left-color: var(--down); }
  .card.warn { border-left-color: var(--warn); }
  .top { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
  .who { font-weight: 600; font-size: 15px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  .badge { font-size: 11px; padding: 2px 7px; border-radius: 999px; background: var(--raise);
    border: 1px solid var(--border); color: var(--muted); }
  .badge.live { color: var(--up); border-color: var(--up); }
  .facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 2px 16px; margin-top: 8px; font-size: 12px; color: var(--muted); }
  .facts b { color: var(--text); font-weight: 500; }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  button, .btn { background: var(--panel); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 4px 11px; font-size: 12px; cursor: pointer;
    text-decoration: none; display: inline-flex; align-items: center; gap: 5px; }
  button:hover, .btn:hover { border-color: var(--muted); background: var(--raise); }
  button:disabled { opacity: 0.45; cursor: default; }
  button.danger:hover { border-color: var(--down); color: var(--down); }
  .empty { color: var(--muted); font-size: 13px; padding: 16px; background: var(--panel);
    border: 1px dashed var(--border); border-radius: 8px; margin-top: 10px; }
  form { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 15px; margin-top: 10px; }
  .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
  label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
  input { width: 100%; background: var(--bg); color: var(--text); font: inherit;
    font-size: 14px; border: 1px solid var(--border); border-radius: 6px; padding: 6px 9px; }
  input:focus { outline: none; border-color: var(--accent); }
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
    <h1>Tmux sessions</h1>
    <a class="back" href="/">&larr; All services</a>
  </header>
  <p class="lede">All cockpit terminal sessions run inside named <code>tmux</code> sessions
  (prefixed with <code>__PREFIX__</code>). Work remains running in the background across
  page closes, reloads, or disconnects.</p>

  <h2>Active Sessions</h2>
  <div id="list">loading…</div>
  <pre id="out"></pre>

  <h2 id="newSessionHeading">Start Session in ~</h2>
  <form id="newSession" autocomplete="off">
    <div class="row">
      <div>
        <label for="name">Session name (optional)</label>
        <input id="name" name="name" placeholder="terminal" spellcheck="false">
      </div>
    </div>
    <div class="acts" style="margin-top:12px">
      <button type="submit" id="createBtn">Start session at ~</button>
    </div>
  </form>

  <footer>Manage sessions with the native <code>tmux</code> CLI on the host anytime:
    <code>tmux ls</code> · <code>tmux attach -t &lt;name&gt;</code></footer>
</div>
<script>
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const qs = encodeURIComponent;
const out = document.getElementById("out");

const post = (path, body) => fetch(path, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
}).then(r => r.json());

function sessionCard(s) {
  const attachedCls = s.attached ? "up" : "warn";
  const attachedBadge = s.attached
    ? `<span class="badge live">attached (${s.attached_count})</span>`
    : `<span class="badge">detached (background)</span>`;
  const typeBadge = s.is_cockpit
    ? `<span class="badge">cockpit</span>`
    : `<span class="badge">tmux</span>`;

  return `<div class="card ${attachedCls}">
    <div class="top">
      <span class="dot ${attachedCls}"></span>
      <span class="who">${esc(s.name)}</span>
      ${attachedBadge}
      ${typeBadge}
    </div>
    <div class="facts">
      <span>created <b>${esc(s.created_human)}</b></span>
      <span>windows <b>${esc(s.windows)}</b></span>
      <span>size <b>${esc(s.size)}</b></span>
      ${s.service_name ? `<span>service <b>${esc(s.service_name)}</b></span>` : ""}
    </div>
    <div class="acts">
      <a class="btn" href="/terminal?session=${qs(s.name)}">Open terminal</a>
      <button class="btn" data-rename="${esc(s.name)}">Rename</button>
      <button class="danger" data-kill="${esc(s.name)}">Kill session</button>
    </div>
  </div>`;
}

async function load() {
  try {
    const res = await fetch("/api/tmux", { cache: "no-store" });
    const data = await res.json();
    const listEl = document.getElementById("list");
    if (!data.sessions || data.sessions.length === 0) {
      listEl.innerHTML = '<div class="empty">No active tmux sessions right now. Start one below or from any service card.</div>';
    } else {
      listEl.innerHTML = data.sessions.map(sessionCard).join("");
    }
  } catch (err) {
    document.getElementById("list").innerHTML = '<div class="empty">Failed to load tmux sessions.</div>';
  }
}

document.getElementById("list").addEventListener("click", async (event) => {
  const killBtn = event.target.closest("button[data-kill]");
  if (killBtn) {
    const name = killBtn.dataset.kill;
    if (!confirm(`Terminate tmux session "${name}" and all processes in it?`)) return;
    killBtn.disabled = true;
    out.textContent = `Terminating ${name}…`;
    const result = await post("/api/tmux/kill", { session: name });
    out.textContent = result.message || (result.ok ? "Session killed." : "Failed to kill session.");
    await load();
    return;
  }

  const renameBtn = event.target.closest("button[data-rename]");
  if (renameBtn) {
    const oldName = renameBtn.dataset.rename;
    const currentShort = oldName.startsWith("cockpit-") ? oldName.slice(8) : oldName;
    const newName = prompt(`Enter new name for tmux session "${oldName}":`, currentShort);
    if (!newName || newName.trim() === currentShort || newName.trim() === oldName) return;
    renameBtn.disabled = true;
    out.textContent = `Renaming ${oldName} to ${newName}…`;
    const result = await post("/api/tmux/rename", { session: oldName, name: newName.trim() });
    out.textContent = result.message || (result.ok ? "Session renamed." : "Failed to rename session.");
    await load();
    return;
  }
});

document.getElementById("newSession").addEventListener("submit", async (event) => {
  event.preventDefault();
  const rawName = document.getElementById("name").value.trim();
  const name = rawName || ("session-" + Math.floor(Date.now() / 1000).toString().slice(-4));
  const btn = document.getElementById("createBtn");
  btn.disabled = true;
  out.textContent = `Starting session ${name} in ~…`;
  const result = await post("/api/tmux/create", { name, cwd: "~" });
  if (result.ok && result.session) {
    location.href = "/terminal?session=" + qs(result.session);
  } else {
    out.textContent = result.message || "Failed to start session.";
    btn.disabled = false;
    await load();
  }
});

load();
setInterval(load, 5000);
</script>
</body>
</html>
""".replace("{THEME}", THEME)
