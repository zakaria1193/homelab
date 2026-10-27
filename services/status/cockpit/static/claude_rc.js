const qs = encodeURIComponent;
const MANAGE = pageConfig().manage === "true";
const out = document.getElementById("out");

function say(result) {
  out.textContent = [result.message, result.output].filter(Boolean).join("\n\n");
  out.scrollIntoView({ block: "nearest" });
}

function card(i) {
  const acts = MANAGE ? `
    <button class="btn secondary small" data-verb="restart" data-name="${esc(i.name)}">restart</button>
    <button class="btn secondary small" data-verb="start" data-name="${esc(i.name)}">start</button>
    <button class="btn secondary small" data-verb="stop" data-name="${esc(i.name)}">stop</button>
    ${i.removable ? `<button class="btn danger small" data-verb="delete"
      data-name="${esc(i.name)}">delete</button>` : ""}` : "";
  return `<div class="card ${esc(i.state)}">
    <div class="top"><span class="status-dot status-${esc(i.state)}"></span>
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
  say(await postJSON("/api/claude-rc/" + (verb === "delete" ? "delete" : "action"),
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
    const r = await postJSON("/api/claude-rc/validate",
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
    const parts = wsVal.replace(/[\/]+$/, "").split("/");
    nameVal = (parts[parts.length - 1] || "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  }
  say(await postJSON("/api/claude-rc/create", {
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
