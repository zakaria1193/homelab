"""/ai-routes: interactive control panel for aicli AI model routing."""

from .theme import THEME

AI_ROUTES_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Routing & Models · __TITLE__</title>
<style>
  {THEME}
  .wrap { max-width: 1100px; margin: 0 auto; padding: 24px 18px 64px; }
  body.embedded .wrap { padding: 12px 14px; max-width: 100%; }
  body.embedded header .back { display: none; }
  header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px; margin-bottom: 4px; }
  h1 { font-size: 22px; margin: 0; display: flex; align-items: center; gap: 8px; color: var(--text); }
  .back { color: var(--muted); text-decoration: none; font-size: 13px; display: inline-flex; align-items: center; gap: 4px; }
  .back:hover { color: var(--text); }
  .top-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .lede { color: var(--muted); font-size: 13px; margin: 6px 0 16px; max-width: 80ch; line-height: 1.5; }

  /* Quota banner */
  .quota-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-bottom: 20px; }
  .quota-card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; }
  .quota-card-title { font-size: 12px; font-weight: 600; text-transform: uppercase; color: var(--muted); letter-spacing: 0.05em; display: flex; justify-content: space-between; margin-bottom: 8px; }
  .quota-bar-wrapper { background: var(--bg); border: 1px solid var(--border); border-radius: 999px; height: 10px; overflow: hidden; margin-bottom: 6px; }
  .quota-bar-fill { height: 100%; border-radius: 999px; transition: width 0.3s ease; }
  .quota-bar-fill.safe { background: var(--up); }
  .quota-bar-fill.warn { background: var(--warn); }
  .quota-bar-fill.danger { background: var(--down); }
  .quota-bar-meta { font-size: 11px; color: var(--muted); display: flex; justify-content: space-between; }

  /* Tables */
  .section-title { font-size: 15px; font-weight: 600; color: var(--text); margin: 24px 0 8px; display: flex; justify-content: space-between; align-items: center; }
  .table-container { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.02); }
  table.routes-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
  table.routes-table th { background: var(--raise); color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; padding: 10px 14px; border-bottom: 1px solid var(--border); white-space: nowrap; }
  table.routes-table td { padding: 11px 14px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  table.routes-table tr:last-child td { border-bottom: none; }
  table.routes-table tbody tr:hover td { background: color-mix(in srgb, var(--raise) 70%, transparent); }

  /* Badges & Pills */
  .badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: var(--raise); border: 1px solid var(--border); color: var(--muted); font-weight: 500; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
  .badge.class-name { font-weight: 600; color: var(--text); background: var(--panel); }
  .badge.model-tag { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; background: var(--bg); color: var(--accent); border-color: color-mix(in srgb, var(--accent) 30%, transparent); }

  /* Form controls */
  select.form-control, input.form-control { background: var(--bg); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 6px 10px; font-size: 12px; font-family: inherit; outline: none; }
  select.form-control:focus, input.form-control:focus { border-color: var(--accent); }

  button { background: var(--panel); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 5px 12px; font-size: 12px; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; font-weight: 500; }
  button:hover { border-color: var(--muted); background: var(--raise); }
  button.btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); font-weight: 600; }
  button.btn-primary:hover { opacity: 0.9; }
  button.btn-danger { color: var(--down); }
  button.btn-danger:hover { border-color: var(--down); background: rgba(248,81,73,0.1); }

  .actions-bar { display: flex; justify-content: flex-end; gap: 10px; margin-top: 14px; }
  .msg-banner { margin-bottom: 14px; padding: 10px 14px; border-radius: 6px; font-size: 13px; display: none; }
  .msg-banner.ok { background: rgba(63,185,80,0.15); border: 1px solid var(--up); color: var(--up); }
  .msg-banner.err { background: rgba(248,81,73,0.15); border: 1px solid var(--down); color: var(--down); }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🧭 AI Model Routing Switchboard</h1>
    <div class="top-right">
      <button type="button" onclick="loadRoutes()">↻ Refresh</button>
      <button type="button" class="btn-primary" onclick="saveRoutes()">💾 Save All Routes</button>
      <a class="back" href="/">&larr; Back to Cockpit</a>
    </div>
  </header>
  <p class="lede">Assign workload classes and clients to AI providers (Claude Code vs Antigravity Gemini). Changes update <code>routes.json</code> instantly without requiring service restarts.</p>

  <div id="msgBanner" class="msg-banner"></div>

  <!-- Live Quotas Header -->
  <div class="quota-grid" id="quotaGrid">
    <div class="quota-card">
      <div class="quota-card-title"><span>Claude Session</span><span id="claudeSessionPct">--%</span></div>
      <div class="quota-bar-wrapper"><div class="quota-bar-fill safe" id="claudeSessionBar" style="width: 0%;"></div></div>
      <div class="quota-bar-meta"><span>5-hour rolling</span><span id="claudeSessionReset">--</span></div>
    </div>
    <div class="quota-card">
      <div class="quota-card-title"><span>Claude Weekly</span><span id="claudeWeeklyPct">--%</span></div>
      <div class="quota-bar-wrapper"><div class="quota-bar-fill safe" id="claudeWeeklyBar" style="width: 0%;"></div></div>
      <div class="quota-bar-meta"><span>Weekly budget</span><span id="claudeWeeklyReset">--</span></div>
    </div>
    <div class="quota-card">
      <div class="quota-card-title"><span>Gemini 5-Hour</span><span id="agyFiveHourPct">--%</span></div>
      <div class="quota-bar-wrapper"><div class="quota-bar-fill safe" id="agyFiveHourBar" style="width: 0%;"></div></div>
      <div class="quota-bar-meta"><span>5-hour rolling</span><span id="agyFiveHourReset">--</span></div>
    </div>
    <div class="quota-card">
      <div class="quota-card-title"><span>Gemini Weekly</span><span id="agyWeeklyPct">--%</span></div>
      <div class="quota-bar-wrapper"><div class="quota-bar-fill safe" id="agyWeeklyBar" style="width: 0%;"></div></div>
      <div class="quota-bar-meta"><span>Weekly budget</span><span id="agyWeeklyReset">--</span></div>
    </div>
  </div>

  <!-- Workload Classes Table -->
  <div class="section-title">
    <span>Workload Classes</span>
  </div>
  <div class="table-container">
    <table class="routes-table" id="classesTable">
      <thead>
        <tr>
          <th style="width: 170px;">Class</th>
          <th>Description & Frequency</th>
          <th style="width: 140px;">Routed Tool</th>
          <th style="width: 120px;">Tier</th>
          <th style="width: 220px;">Effective Model</th>
        </tr>
      </thead>
      <tbody id="classesTbody">
        <tr><td colspan="5" style="text-align: center; color: var(--muted); padding: 20px;">Loading routing table...</td></tr>
      </tbody>
    </table>
  </div>

  <!-- Registered Clients & Overrides Table -->
  <div class="section-title">
    <span>Registered Clients & Overrides</span>
    <button type="button" onclick="addClientRow()">+ Add Client Override</button>
  </div>
  <div class="table-container">
    <table class="routes-table" id="clientsTable">
      <thead>
        <tr>
          <th style="width: 200px;">Client ID</th>
          <th>Description & Frequency</th>
          <th style="width: 170px;">Assigned Class</th>
          <th style="width: 140px;">Override Tool</th>
          <th style="width: 120px;">Override Tier</th>
          <th style="width: 90px; text-align: right;">Actions</th>
        </tr>
      </thead>
      <tbody id="clientsTbody">
        <tr><td colspan="6" style="text-align: center; color: var(--muted); padding: 20px;">No client overrides configured.</td></tr>
      </tbody>
    </table>
  </div>

  <!-- OptiPlex Projects (aicli enabled) -->
  <div class="section-title">
    <span>OptiPlex Projects (aicli enabled)</span>
    <button type="button" onclick="addProject()">+ Add Project</button>
  </div>
  <div class="table-container" style="padding: 14px 18px;">
    <div id="projectsList" style="display: flex; flex-wrap: wrap; gap: 8px;">
      <span style="color: var(--muted); font-size: 13px;">Loading projects...</span>
    </div>
  </div>

  <div class="actions-bar">
    <button type="button" onclick="loadRoutes()">Cancel / Discard</button>
    <button type="button" class="btn-primary" onclick="saveRoutes()">💾 Save All Changes</button>
  </div>
</div>

<script>
if (new URLSearchParams(window.location.search).get('embedded') === '1') {
  document.body.classList.add('embedded');
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

let state = {
  classes: {},
  clients: {},
  models: { claude: {}, agy: {} }
};

function banner(msg, isErr) {
  const b = document.getElementById('msgBanner');
  b.className = 'msg-banner ' + (isErr ? 'err' : 'ok');
  b.textContent = msg;
  b.style.display = 'block';
  setTimeout(() => { b.style.display = 'none'; }, 4000);
}

function updateBar(barId, pctId, resetId, barData) {
  const bar = document.getElementById(barId);
  const pct = document.getElementById(pctId);
  const reset = document.getElementById(resetId);
  if (!barData || typeof barData.pct !== 'number') {
    pct.textContent = 'N/A';
    bar.style.width = '0%';
    reset.textContent = 'disabled / no limit';
    return;
  }
  const p = Math.max(0, Math.min(100, barData.pct));
  pct.textContent = p + '%';
  bar.style.width = p + '%';
  bar.className = 'quota-bar-fill ' + (p > 90 ? 'danger' : p > 70 ? 'warn' : 'safe');
  reset.textContent = barData.reset ? 'resets ' + barData.reset : 'active';
}

function renderQuota(usage) {
  if (!usage) return;
  if (usage.claude && usage.claude.bars) {
    updateBar('claudeSessionBar', 'claudeSessionPct', 'claudeSessionReset', usage.claude.bars.five_hour);
    updateBar('claudeWeeklyBar', 'claudeWeeklyPct', 'claudeWeeklyReset', usage.claude.bars.weekly);
  }
  if (usage.agy && usage.agy.bars) {
    updateBar('agyFiveHourBar', 'agyFiveHourPct', 'agyFiveHourReset', usage.agy.bars.five_hour);
    updateBar('agyWeeklyBar', 'agyWeeklyPct', 'agyWeeklyReset', usage.agy.bars.weekly);
  }
}

function getModelName(tool, tier) {
  if (state.models && state.models[tool] && state.models[tool][tier]) {
    return state.models[tool][tier];
  }
  return tier || '';
}

function renderClasses() {
  const tbody = document.getElementById('classesTbody');
  tbody.innerHTML = '';
  const entries = Object.entries(state.classes).sort(([a], [b]) => a.localeCompare(b));
  if (entries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--muted); padding: 20px;">No classes configured.</td></tr>';
    return;
  }

  for (const [name, c] of entries) {
    const tr = document.createElement('tr');
    tr.dataset.className = name;
    tr.innerHTML = `
      <td><span class="badge class-name">${esc(name)}</span></td>
      <td>
        <div><strong>${esc(c.description)}</strong></div>
        <div style="color: var(--muted); font-size: 11px; margin-top: 2px;">Frequency: ${esc(c.frequency || 'N/A')}</div>
      </td>
      <td>
        <select class="form-control class-tool" onchange="onClassChange(this.closest('tr'))">
          <option value="claude" ${c.tool === 'claude' ? 'selected' : ''}>Claude Code</option>
          <option value="agy" ${c.tool === 'agy' ? 'selected' : ''}>Gemini (agy)</option>
        </select>
      </td>
      <td>
        <select class="form-control class-tier" onchange="onClassChange(this.closest('tr'))">
          <option value="low" ${c.tier === 'low' ? 'selected' : ''}>low</option>
          <option value="default" ${(!c.tier || c.tier === 'default') ? 'selected' : ''}>default</option>
          <option value="deep" ${c.tier === 'deep' ? 'selected' : ''}>deep</option>
        </select>
      </td>
      <td>
        <span class="badge model-tag class-model">${esc(getModelName(c.tool || 'claude', c.tier || 'default'))}</span>
      </td>
    `;
    tbody.appendChild(tr);
  }
}

function onClassChange(tr) {
  const className = tr.dataset.className;
  const tool = tr.querySelector('.class-tool').value;
  const tier = tr.querySelector('.class-tier').value;
  state.classes[className].tool = tool;
  state.classes[className].tier = tier;
  tr.querySelector('.class-model').textContent = getModelName(tool, tier);
}

function renderClients() {
  const tbody = document.getElementById('clientsTbody');
  tbody.innerHTML = '';
  const entries = Object.entries(state.clients).sort(([a], [b]) => a.localeCompare(b));
  if (entries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--muted); padding: 16px;">No clients configured.</td></tr>';
    return;
  }

  for (const [clientId, c] of entries) {
    const tr = document.createElement('tr');
    tr.dataset.client = clientId;
    const descText = c.description ? esc(c.description) : '<span style="color:var(--muted); font-style:italic;">Default client</span>';
    const freqText = c.frequency ? `<div style="font-size: 11px; color: var(--muted); margin-top: 2px;">${esc(c.frequency)}</div>` : '';
    tr.innerHTML = `
      <td><code>${esc(clientId)}</code></td>
      <td>
        <div>${descText}</div>
        ${freqText}
      </td>
      <td>
        <select class="form-control client-class" onchange="onClientChange(this.closest('tr'))">
          <option value="">(none)</option>
          ${Object.keys(state.classes).map(k => `<option value="${esc(k)}" ${c.class === k ? 'selected' : ''}>${esc(k)}</option>`).join('')}
        </select>
      </td>
      <td>
        <select class="form-control client-tool" onchange="onClientChange(this.closest('tr'))">
          <option value="" ${!c.tool ? 'selected' : ''}>Inherit from class</option>
          <option value="claude" ${c.tool === 'claude' ? 'selected' : ''}>Claude Code</option>
          <option value="agy" ${c.tool === 'agy' ? 'selected' : ''}>Gemini (agy)</option>
        </select>
      </td>
      <td>
        <select class="form-control client-tier" onchange="onClientChange(this.closest('tr'))">
          <option value="" ${!c.tier ? 'selected' : ''}>Inherit from class</option>
          <option value="low" ${c.tier === 'low' ? 'selected' : ''}>low</option>
          <option value="default" ${c.tier === 'default' ? 'selected' : ''}>default</option>
          <option value="deep" ${c.tier === 'deep' ? 'selected' : ''}>deep</option>
        </select>
      </td>
      <td style="text-align: right;">
        <button type="button" class="btn-danger" onclick="removeClient(this.closest('tr').dataset.client)">Remove</button>
      </td>
    `;
    tbody.appendChild(tr);
  }
}

function onClientChange(tr) {
  const clientId = tr.dataset.client;
  const cls = tr.querySelector('.client-class').value;
  const tool = tr.querySelector('.client-tool').value;
  const tier = tr.querySelector('.client-tier').value;
  const prev = state.clients[clientId] || {};
  state.clients[clientId] = {
    ...prev,
    class: cls || undefined,
    tool: tool || undefined,
    tier: tier || undefined
  };
}

function addClientRow() {
  const clientId = prompt("Enter client identifier (e.g. pjm:auto-execute, homelab:audit):");
  if (!clientId || !clientId.trim()) return;
  const cleanId = clientId.trim();
  if (state.clients[cleanId]) {
    alert("Client already exists.");
    return;
  }
  state.clients[cleanId] = { class: "maintenance" };
  renderClients();
}

function removeClient(clientId) {
  delete state.clients[clientId];
  renderClients();
}

function renderProjects() {
  const container = document.getElementById('projectsList');
  if (!container) return;
  container.innerHTML = '';
  if (!state.optiplex_projects || state.optiplex_projects.length === 0) {
    container.innerHTML = '<span style="color: var(--muted); font-size: 13px;">No projects registered.</span>';
    return;
  }
  for (const p of state.optiplex_projects) {
    const chip = document.createElement('span');
    chip.className = 'badge';
    chip.style.fontSize = '12px';
    chip.style.padding = '4px 10px';
    chip.dataset.project = p;
    chip.innerHTML = `🖥️ <strong>${esc(p)}</strong> <span style="cursor:pointer; margin-left:6px; opacity:0.6; font-size:14px;" title="Remove project" onclick="removeProject(this.parentElement.dataset.project)">&times;</span>`;
    container.appendChild(chip);
  }
}

function addProject() {
  const name = prompt("Enter project name running on OptiPlex with aicli access:");
  if (!name || !name.trim()) return;
  const clean = name.trim();
  if (state.optiplex_projects.includes(clean)) {
    alert("Project already registered.");
    return;
  }
  state.optiplex_projects.push(clean);
  state.optiplex_projects.sort();
  renderProjects();
}

function removeProject(name) {
  state.optiplex_projects = state.optiplex_projects.filter(p => p !== name);
  renderProjects();
}

async function loadRoutes() {
  try {
    const res = await fetch('/api/ai-routes');
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    state.classes = data.classes || {};
    state.clients = data.clients || {};
    state.optiplex_projects = data.optiplex_projects || [];
    state.models = data.models || {
      claude: { low: "claude-haiku-5-5", default: "claude-sonnet-5", deep: "claude-opus-5-5" },
      agy: { low: "gemini-3.8-flash-low", default: "gemini-3.8-flash-high", deep: "gemini-3.8-flash-high" }
    };
    renderClasses();
    renderClients();
    renderProjects();
    renderQuota(data.usage);
  } catch (err) {
    banner("Failed to load routes: " + err.message, true);
  }
}

async function saveRoutes() {
  try {
    const payload = {
      classes: state.classes,
      clients: state.clients,
      optiplex_projects: state.optiplex_projects
    };
    const res = await fetch('/api/ai-routes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    banner("Routes saved successfully! Applied immediately across homelab and aicli.");
    loadRoutes();
  } catch (err) {
    banner("Failed to save routes: " + err.message, true);
  }
}

document.addEventListener('DOMContentLoaded', loadRoutes);
</script>
</body>
</html>
""".replace("{THEME}", THEME)
