const qs = encodeURIComponent;
const out = document.getElementById("out");

function say(r) {
  out.textContent = (r.message ? r.message + "\n\n" : "") + (r.output || "");
}

function card(i) {
  const acts = `
    <button class="btn secondary small" data-verb="start" data-name="${esc(i.name)}">start</button>
    <button class="btn secondary small" data-verb="restart" data-name="${esc(i.name)}">restart</button>
    <button class="btn secondary small" data-verb="stop" data-name="${esc(i.name)}">stop</button>
    <button class="btn secondary small" data-verb="upgrade" data-name="${esc(i.name)}">upgrade</button>
    <button class="btn secondary small" data-verb="doctor" data-name="${esc(i.name)}">doctor</button>
    ${i.removable ? `<button class="btn danger small" data-verb="delete" data-name="${esc(i.name)}">delete</button>` : ""}`;
  return `<div class="card ${esc(i.state)}">
    <div class="top">
      <span class="status-dot status-${esc(i.state)}"></span>
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
  say(await postJSON("/api/antigravity-rc/" + (verb === "delete" ? "delete" : "action"), { verb, name }));
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
    const r = await postJSON("/api/antigravity-rc/validate", { workspace });
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
    const parts = workspace.replace(/[\/]+$/, "").split("/");
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
  say(await postJSON("/api/antigravity-rc/create", {
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
