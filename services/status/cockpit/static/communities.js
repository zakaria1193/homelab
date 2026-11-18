// The /communities overview. Read-only for now (homelab-0024 plan item 1):
// editing and creating a community land in later plan items.

function featureList(features) {
  const on = Object.entries(features || {}).filter(([, v]) => v).map(([k]) => k);
  return on.length ? esc(on.join(", ")) : '<span class="muted">none</span>';
}

function d1Cell(d1) {
  if (!d1 || d1.error) {
    return `<span class="muted" title="${esc((d1 && d1.error) || "")}">—</span>`;
  }
  const last = d1.last_ingest ? esc(d1.last_ingest) : "never";
  return `${d1.members} members · ${d1.events} events · last ingest ${last}`;
}

function checklistCell(checklist) {
  if (!checklist || checklist.error) {
    return `<span class="muted">${esc((checklist && checklist.error) || "unknown")}</span>`;
  }
  const base = `${checklist.checked} / ${checklist.required} required items`;
  const toLive = checklist.needed_for_live > 0
    ? ` · ${checklist.needed_for_live} more needed to go live`
    : "";
  return esc(base + toLive);
}

function deployCell(deploy) {
  if (!deploy) return "";
  if (deploy.deployed) return '<span class="badge up">deployed</span>';
  const steps = (deploy.hand_steps || []).map(s => `<li>${esc(s)}</li>`).join("");
  return `<span class="badge warn">not deployed</span><ul class="hand-steps">${steps}</ul>`;
}

function card(c) {
  if (c.error) {
    return `<div class="card community-card"><h2>${esc(c.slug)}</h2>
      <div class="msg-banner err">${esc(c.error)}</div></div>`;
  }
  return `<div class="card community-card">
    <div class="card-head">
      <h2>${esc(c.name)} <span class="muted small">${esc(c.slug)}</span></h2>
      <span class="badge ${c.status === "live" ? "up" : "warn"}">${esc(c.status)}</span>
    </div>
    <dl class="community-fields">
      <dt>id</dt><dd>${esc(String(c.id))}</dd>
      <dt>origin</dt><dd>${esc(c.origin)}</dd>
      <dt>hosts</dt><dd>${esc((c.hosts || []).join(", "))}</dd>
      <dt>ingestion</dt><dd>${esc(c.ingestion)}</dd>
      <dt>features</dt><dd>${featureList(c.features)}</dd>
      <dt>launch checklist</dt><dd>${checklistCell(c.checklist)}</dd>
      <dt>D1</dt><dd>${d1Cell(c.d1)}</dd>
      <dt>deploy</dt><dd>${deployCell(c.deploy)}</dd>
    </dl>
  </div>`;
}

async function load() {
  const notice = document.getElementById("notice");
  try {
    const res = await fetch("/api/communities");
    const data = await res.json();
    if (data.error) {
      notice.hidden = false;
      notice.textContent = data.error;
    } else {
      notice.hidden = true;
    }
    document.getElementById("cards").innerHTML = (data.communities || []).map(card).join("");
    document.getElementById("updated").textContent = "updated " + new Date().toLocaleTimeString();
  } catch (err) {
    notice.hidden = false;
    notice.textContent = "failed to load: " + err;
  }
}

load();
setInterval(load, 30000);
