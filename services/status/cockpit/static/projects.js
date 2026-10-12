if (new URLSearchParams(window.location.search).get("embedded") === "1") {
  document.body.classList.add("embedded");
}

// Same rule as the cockpit: lead with the tunnel URL when we were reached by
// hostname, with the LAN URL when we were reached by IP.
const PUBLIC_VIEW = !/^[\d.]+$|^\[|^localhost$|\.local$/i.test(location.hostname);
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
    return `<li><span class="status-dot status-${esc(r.state)}"></span>
      <span class="name">${esc(r.name)}</span>
      ${syncBadge(r)}
      <span class="state">${esc(r.state)}</span>
      ${ghLink(r)}
      ${href ? `<a class="open" href="${esc(href)}" target="_blank" rel="noopener">${esc(href.replace(/^https?:\/\//, ""))}</a>` : `<span class="open"></span>`}</li>`;
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
  $("summary").textContent = "Name, LAN link, public link and GitHub repo (only name is required). Order here is the order on the page.";
  $("list").className = "edit";
  $("list").innerHTML = draft.length ? draft.map((p, i) => `<li data-i="${i}">
      <div class="fields">
        <input data-k="name" placeholder="name" value="${esc(p.name)}" aria-label="name">
        <input data-k="link" placeholder="http://192.168.1.10:8080" value="${esc(p.link)}" aria-label="LAN link">
        <input data-k="remote" placeholder="https://x.zakariafadli.com" value="${esc(p.remote)}" aria-label="public link">
        <input data-k="github" placeholder="https://github.com/owner/repo" value="${esc(p.github)}" aria-label="GitHub repo">
      </div>
      <div class="row-acts">
        <button type="button" class="btn secondary small icon" data-act="up" ${i === 0 ? "disabled" : ""} title="move up">&uarr;</button>
        <button type="button" class="btn secondary small icon" data-act="down" ${i === draft.length - 1 ? "disabled" : ""} title="move down">&darr;</button>
        <button type="button" class="btn danger small icon" data-act="del" title="remove">Remove</button>
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

const REFRESH = parseInt(pageConfig().refresh, 10) || 15;
load(true);
setInterval(() => load(false), REFRESH * 1000);
