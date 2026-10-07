"""/projects: every live project, its status and its link - editable in place."""

from .theme import THEME

PROJECTS_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Projects · __TITLE__</title>
<style>
  {THEME}
  .wrap { max-width: 860px; margin: 0 auto; padding: 24px 16px 64px; }
  body.embedded .wrap { max-width: 100%; padding: 12px 14px 24px; }
  body.embedded .back { display: none; }
  header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px; }
  h1 { font-size: 22px; margin: 0; }
  .tools { display: flex; align-items: center; gap: 10px; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .summary { color: var(--muted); font-size: 13px; margin: 8px 0 16px; }
  .summary b { color: var(--text); font-weight: 600; }
  ul { list-style: none; margin: 0; padding: 0; background: var(--panel);
    border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  li { display: flex; align-items: center; gap: 12px; padding: 11px 14px;
    border-bottom: 1px solid var(--border); }
  li:last-child { border-bottom: none; }
  .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; background: var(--unknown); }
  .dot.up { background: var(--up); } .dot.down { background: var(--down); }
  .dot.warn { background: var(--warn); }
  .name { font-weight: 600; min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .state { font-size: 12px; color: var(--muted); flex: none; width: 4.5em; }
  a.open { color: var(--accent); text-decoration: none; font-size: 13px; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; flex: 0 0 42%; text-align: right; }
  a.open:hover { text-decoration: underline; }
  /* repo link with open PR / issue counts; a fixed width keeps the column aligned */
  a.gh { flex: none; width: 12em; display: flex; gap: 8px; justify-content: flex-end;
    color: var(--muted); text-decoration: none; font-size: 12px; white-space: nowrap; }
  a.gh:hover { color: var(--text); }
  a.gh .busy { color: var(--warn); }
  a.gh .vis { border: 1px solid var(--border); border-radius: 9px; padding: 0 6px; font-size: 11px; }
  a.gh .vis.public { color: var(--up); border-color: var(--up); }
  .sync { flex: none; font-size: 11px; color: var(--warn); border: 1px solid var(--warn);
    border-radius: 9px; padding: 0 6px; white-space: nowrap; }
  .sync.behind { color: var(--muted); border-color: var(--border); }
  span.gh { flex: none; width: 12em; font-size: 12px; }
  /* on a phone the dot carries the state; the name keeps line one, repo and link go below */
  @media (max-width: 520px) { .state, span.gh { display: none; }
    li { flex-wrap: wrap; row-gap: 4px; }
    .name { flex: 1 1 calc(100% - 22px); }
    a.gh { order: 1; width: auto; margin-left: 22px; }
    a.open { order: 2; flex: 1 1 0; min-width: 0; } }
  .empty { color: var(--muted); padding: 16px; }
  button { background: var(--panel); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 5px 12px; font: inherit; font-size: 13px; cursor: pointer; }
  button:hover { border-color: var(--muted); background: var(--raise); }
  button:disabled { opacity: 0.4; cursor: default; }
  button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  button.icon { padding: 3px 8px; font-size: 12px; }
  button.danger:hover { border-color: var(--down); color: var(--down); }
  /* edit mode: one card per project, fields stack on a phone */
  .edit li { flex-wrap: wrap; gap: 8px; }
  .edit .fields { display: grid; grid-template-columns: 1fr 1.2fr 1.2fr 1.2fr; gap: 8px; flex: 1 1 100%; }
  @media (max-width: 640px) { .edit .fields { grid-template-columns: 1fr; } }
  .edit .row-acts { display: flex; gap: 6px; margin-left: auto; }
  input { width: 100%; min-width: 0; background: var(--bg); color: var(--text); font: inherit;
    font-size: 13px; border: 1px solid var(--border); border-radius: 6px; padding: 6px 9px; }
  input:focus { outline: none; border-color: var(--accent); }
  .edit-bar { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; align-items: center; }
  .edit-bar[hidden], [hidden] { display: none !important; }
  .msg { font-size: 13px; }
  .msg.err { color: var(--down); } .msg.ok { color: var(--up); }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Projects</h1>
    <div class="tools">
      <span class="msg" id="pushMsg"></span>
      <button type="button" class="primary" id="pushAll" hidden>Push all</button>
      <button type="button" id="editBtn">Edit</button>
      <a class="back" href="/">&larr; Cockpit</a>
    </div>
  </header>
  <p class="summary" id="summary">Loading…</p>
  <ul id="list"></ul>
  <div class="edit-bar" id="editBar" hidden>
    <button type="button" id="addBtn">+ Add project</button>
    <span style="flex:1"></span>
    <span class="msg" id="msg"></span>
    <button type="button" id="cancelBtn">Cancel</button>
    <button type="button" class="primary" id="saveBtn">Save</button>
  </div>
</div>
<script>
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// Same rule as the cockpit: lead with the tunnel URL when we were reached by
// hostname, with the LAN URL when we were reached by IP.
const PUBLIC_VIEW = !/^[\\d.]+$|^\\[|^localhost$|\\.local$/i.test(location.hostname);
const $ = (id) => document.getElementById(id);

let rows = [];       // last list from the server, with states
let counts = {};     // GitHub counts by repo url, read once when the page loads
let draft = null;    // the list being edited, or null when just viewing

function renderView() {
  const up = rows.filter(r => r.state === "up").length;
  const ahead = rows.filter(r => r.sync && r.sync.ahead).length;
  $("summary").innerHTML = rows.length ? `<b>${up}</b> of <b>${rows.length}</b> up` : "";
  $("pushAll").hidden = !ahead;
  $("pushAll").textContent = `Push all (${ahead})`;
  $("list").className = "";
  $("list").innerHTML = rows.length ? rows.map(r => {
    const href = (PUBLIC_VIEW && r.remote) || r.link || r.remote;
    return `<li><span class="dot ${esc(r.state)}"></span>
      <span class="name">${esc(r.name)}</span>
      ${syncBadge(r)}
      <span class="state">${esc(r.state)}</span>
      ${ghLink(r)}
      <a class="open" href="${esc(href)}" target="_blank" rel="noopener">${esc(href.replace(/^https?:\\/\\//, ""))}</a></li>`;
  }).join("") : `<li class="empty">No projects yet. Click Edit to add one.</li>`;
}

// Local default branch against origin's: shown only when they differ.
function syncBadge(r) {
  const s = r.sync;
  if (!s || (!s.ahead && !s.behind)) return "";
  const bits = [s.ahead ? `${s.ahead} ahead` : "", s.behind ? `${s.behind} behind` : ""].filter(Boolean).join(", ");
  return `<span class="sync ${s.ahead ? "" : "behind"}" title="${esc(s.branch)} vs origin/${esc(s.branch)}">${esc(s.branch)}: ${bits}</span>`;
}

// GitHub repo link, with the open PR and issue counts when gh could read them.
function ghLink(r) {
  if (!r.github) return `<span class="gh"></span>`;
  const repo = r.github.replace(/^https:\/\/github\.com\//, "");
  const n = (v, label) => `<span class="${v ? "busy" : ""}" title="${v} open ${label}">${v} ${label}</span>`;
  const c = counts[r.github];
  const vis = c ? `<span class="vis ${c.private ? "private" : "public"}">${c.private ? "private" : "public"}</span>` : "";
  const label = c ? vis + n(c.prs, "PR") + n(c.issues, "iss.") : "GitHub";
  return `<a class="gh" href="${esc(r.github)}" target="_blank" rel="noopener" title="${esc(repo)}">${label}</a>`;
}

function renderEdit() {
  $("summary").textContent = "Name, LAN link, public link and GitHub repo (all optional but one link). Order here is the order on the page.";
  $("list").className = "edit";
  $("list").innerHTML = draft.length ? draft.map((p, i) => `<li data-i="${i}">
      <div class="fields">
        <input data-k="name" placeholder="name" value="${esc(p.name)}" aria-label="name">
        <input data-k="link" placeholder="http://192.168.1.10:8080" value="${esc(p.link)}" aria-label="LAN link">
        <input data-k="remote" placeholder="https://x.zakariafadli.com" value="${esc(p.remote)}" aria-label="public link">
        <input data-k="github" placeholder="https://github.com/owner/repo" value="${esc(p.github)}" aria-label="GitHub repo">
      </div>
      <div class="row-acts">
        <button type="button" class="icon" data-act="up" ${i === 0 ? "disabled" : ""} title="move up">&uarr;</button>
        <button type="button" class="icon" data-act="down" ${i === draft.length - 1 ? "disabled" : ""} title="move down">&darr;</button>
        <button type="button" class="icon danger" data-act="del" title="remove">Remove</button>
      </div></li>`).join("") : `<li class="empty">Empty list. Add a project below.</li>`;
}

function render() {
  $("editBar").hidden = !draft;
  $("editBtn").hidden = !!draft;
  draft ? renderEdit() : renderView();
}

// The timer only refreshes states; the GitHub counts are asked for once, when
// the page loads, since each read is a `gh` call.
async function load(github) {
  if (draft) return;  // never clobber an edit in progress
  try {
    rows = await (await fetch("/api/projects" + (github ? "?github=1" : ""), { cache: "no-store" })).json();
    if (github) rows.forEach(r => { if (r.prs !== undefined) counts[r.github] = { prs: r.prs, issues: r.issues, private: r.private }; });
    render();
  } catch (e) {
    $("summary").textContent = "Could not load status.";
  }
}

$("pushAll").onclick = async () => {
  $("pushAll").disabled = true;
  $("pushMsg").className = "msg";
  $("pushMsg").textContent = "Pushing…";
  try {
    const out = await (await fetch("/api/projects/push-all", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })).json();
    const bad = (out.pushed || []).filter(r => !r.ok);
    $("pushMsg").className = "msg " + (bad.length ? "err" : "ok");
    $("pushMsg").textContent = bad.length ? bad.map(r => `${r.name}: ${r.message}`).join("; ")
      : `Pushed ${out.pushed.length}`;
    await load();
  } catch (e) {
    $("pushMsg").className = "msg err";
    $("pushMsg").textContent = "Push failed: " + e.message;
  } finally {
    $("pushAll").disabled = false;
  }
};

function setMsg(text, kind) { $("msg").textContent = text; $("msg").className = "msg " + (kind || ""); }

$("editBtn").onclick = () => {
  // `service` is not shown in the form but must survive a save.
  draft = rows.map(r => ({ name: r.name, link: r.link, remote: r.remote, service: r.service || "", github: r.github || "" }));
  setMsg("");
  render();
};
$("cancelBtn").onclick = () => { draft = null; render(); };
$("addBtn").onclick = () => {
  draft.push({ name: "", link: "", remote: "", github: "" });
  render();
  $("list").querySelector("li:last-child input").focus();
};
$("list").addEventListener("input", (e) => {
  const li = e.target.closest("li[data-i]");
  if (li && e.target.dataset.k) draft[+li.dataset.i][e.target.dataset.k] = e.target.value;
});
$("list").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const i = +btn.closest("li").dataset.i;
  if (btn.dataset.act === "del") draft.splice(i, 1);
  else {
    const j = btn.dataset.act === "up" ? i - 1 : i + 1;
    [draft[i], draft[j]] = [draft[j], draft[i]];
  }
  render();
});
$("saveBtn").onclick = async () => {
  $("saveBtn").disabled = true;
  setMsg("Saving…");
  try {
    const res = await fetch("/api/projects/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projects: draft }),
    });
    const out = await res.json();
    if (!out.ok) { setMsg(out.message || "Save failed", "err"); return; }
    draft = null;
    await load();
  } catch (e) {
    setMsg("Save failed: " + e.message, "err");
  } finally {
    $("saveBtn").disabled = false;
  }
};

load(true);
setInterval(() => load(false), __REFRESH__ * 1000);
</script>
</body>
</html>
""".replace("{THEME}", THEME)
