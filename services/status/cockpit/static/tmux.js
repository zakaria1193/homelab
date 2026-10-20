const qs = encodeURIComponent;
const out = document.getElementById("out");

function sessionCard(s) {
  const dotCls = s.attached ? "status-up" : "status-warn";
  const toneCls = s.attached ? "tone-up" : "tone-warn";
  const attachedBadge = s.attached
    ? `<span class="badge up">attached (${s.attached_count})</span>`
    : `<span class="badge">detached (background)</span>`;
  const typeBadge = s.is_cockpit
    ? `<span class="badge">cockpit</span>`
    : `<span class="badge">tmux</span>`;

  return `<div class="card ${toneCls}">
    <div class="top">
      <span class="status-dot ${dotCls}"></span>
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
      <a class="btn secondary small" href="/terminal?session=${qs(s.name)}">Open terminal</a>
      <button class="btn secondary small" data-rename="${esc(s.name)}">Rename</button>
      <button class="btn danger small" data-kill="${esc(s.name)}">Kill session</button>
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
    const result = await postJSON("/api/tmux/kill", { session: name });
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
    const result = await postJSON("/api/tmux/rename", { session: oldName, name: newName.trim() });
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
  const result = await postJSON("/api/tmux/create", { name, cwd: "~" });
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
