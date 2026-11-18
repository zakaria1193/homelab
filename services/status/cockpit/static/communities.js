// The /communities overview, plus editing an existing community
// (homelab-0024 plan item 2). Creating one is a later plan item.

const FEATURE_KEYS = ["attendanceTaps", "classes", "welcomeHosts", "map", "cityPages", "styleFilters"];
const EDITABLE_STRING_FIELDS = ["name", "status", "ingestion"];

// One slug -> its last-loaded record, so a save can diff the form against
// what the page actually saw (sent back as `expected_old`) rather than
// against whatever is currently typed.
let loaded = {};
let pending = {}; // slug -> the confirmed diff waiting on a second click.

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

function featureCheckboxes(slug, features) {
  return FEATURE_KEYS.map(key => {
    const checked = (features || {})[key] ? "checked" : "";
    return `<label class="feature-flag"><input type="checkbox" data-slug="${esc(slug)}" data-field="${key}" ${checked}> ${key}</label>`;
  }).join("");
}

function editForm(c) {
  return `
    <label>name <input type="text" maxlength="80" data-slug="${esc(c.slug)}" data-field="name" value="${esc(c.name)}"></label>
    <label>status
      <select data-slug="${esc(c.slug)}" data-field="status">
        <option value="live" ${c.status === "live" ? "selected" : ""}>live</option>
        <option value="hidden" ${c.status === "hidden" ? "selected" : ""}>hidden</option>
      </select>
    </label>
    <label>ingestion
      <select data-slug="${esc(c.slug)}" data-field="ingestion">
        <option value="faurax" ${c.ingestion === "faurax" ? "selected" : ""}>faurax</option>
        <option value="manual" ${c.ingestion === "manual" ? "selected" : ""}>manual</option>
      </select>
    </label>
    <div class="feature-flags">${featureCheckboxes(c.slug, c.features)}</div>
    <div class="edit-actions">
      <button class="btn small" data-action="save" data-slug="${esc(c.slug)}">Save changes</button>
      <span class="muted small" data-role="edit-status" data-slug="${esc(c.slug)}"></span>
    </div>
    <div class="confirm-box" data-role="confirm" data-slug="${esc(c.slug)}" hidden></div>`;
}

function card(c) {
  if (c.error) {
    return `<div class="card community-card"><h2>${esc(c.slug)}</h2>
      <div class="msg-banner err">${esc(c.error)}</div></div>`;
  }
  loaded[c.slug] = c;
  return `<div class="card community-card">
    <div class="card-head">
      <h2>${esc(c.name)} <span class="muted small">${esc(c.slug)}</span></h2>
      <span class="badge ${c.status === "live" ? "up" : "warn"}">${esc(c.status)}</span>
    </div>
    <dl class="community-fields">
      <dt>id</dt><dd>${esc(String(c.id))}</dd>
      <dt>origin</dt><dd>${esc(c.origin)}</dd>
      <dt>hosts</dt><dd>${esc((c.hosts || []).join(", "))}</dd>
      <dt>launch checklist</dt><dd>${checklistCell(c.checklist)}</dd>
      <dt>D1</dt><dd>${d1Cell(c.d1)}</dd>
      <dt>deploy</dt><dd>${deployCell(c.deploy)}</dd>
    </dl>
    <form class="community-edit" data-slug="${esc(c.slug)}" onsubmit="return false">
      ${editForm(c)}
    </form>
  </div>`;
}

function fieldValue(input) {
  if (input.type === "checkbox") return input.checked;
  return input.value;
}

function formDiff(slug) {
  const original = loaded[slug];
  if (!original) return {};
  const diff = {};
  document.querySelectorAll(`[data-slug="${slug}"][data-field]`).forEach(input => {
    const field = input.dataset.field;
    const value = fieldValue(input);
    const old = EDITABLE_STRING_FIELDS.includes(field) ? original[field] : !!(original.features || {})[field];
    if (value !== old) diff[field] = { old, value };
  });
  return diff;
}

function fmt(v) {
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}

function renderConfirm(slug, diff) {
  const box = document.querySelector(`[data-role="confirm"][data-slug="${slug}"]`);
  const rows = Object.entries(diff)
    .map(([field, { old, value }]) => `<li>${esc(field)}: ${esc(fmt(old))} &rarr; ${esc(fmt(value))}</li>`)
    .join("");
  box.innerHTML = `<ul class="diff-list">${rows}</ul>
    <button class="btn small" data-action="confirm" data-slug="${esc(slug)}">Confirm save</button>
    <button class="btn small secondary" data-action="cancel" data-slug="${esc(slug)}">Cancel</button>`;
  box.hidden = false;
}

function setStatus(slug, text) {
  const el = document.querySelector(`[data-role="edit-status"][data-slug="${slug}"]`);
  if (el) el.textContent = text;
}

async function saveCommunity(slug) {
  const diff = pending[slug];
  if (!diff) return;
  setStatus(slug, "saving…");
  const original = loaded[slug] || {};
  const changes = {};
  for (const [field, { value }] of Object.entries(diff)) changes[field] = value;
  const expected_old = {};
  EDITABLE_STRING_FIELDS.forEach(field => { expected_old[field] = original[field]; });
  FEATURE_KEYS.forEach(key => { expected_old[key] = !!(original.features || {})[key]; });
  try {
    const res = await fetch("/api/communities/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug, changes, expected_old }),
    });
    const result = await res.json();
    if (result.ok) {
      setStatus(slug, "saved " + (result.commit || ""));
      await load();
    } else {
      setStatus(slug, "refused: " + result.message);
    }
  } catch (err) {
    setStatus(slug, "failed: " + err);
  }
  delete pending[slug];
  const box = document.querySelector(`[data-role="confirm"][data-slug="${slug}"]`);
  if (box) box.hidden = true;
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const slug = button.dataset.slug;
  if (button.dataset.action === "save") {
    const diff = formDiff(slug);
    if (Object.keys(diff).length === 0) {
      setStatus(slug, "nothing changed");
      return;
    }
    pending[slug] = diff;
    renderConfirm(slug, diff);
  } else if (button.dataset.action === "confirm") {
    saveCommunity(slug);
  } else if (button.dataset.action === "cancel") {
    delete pending[slug];
    const box = document.querySelector(`[data-role="confirm"][data-slug="${slug}"]`);
    if (box) box.hidden = true;
  }
});

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
    loaded = {};
    document.getElementById("cards").innerHTML = (data.communities || []).map(card).join("");
    document.getElementById("updated").textContent = "updated " + new Date().toLocaleTimeString();
  } catch (err) {
    notice.hidden = false;
    notice.textContent = "failed to load: " + err;
  }
}

load();
