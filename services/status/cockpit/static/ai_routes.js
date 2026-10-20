if (new URLSearchParams(window.location.search).get('embedded') === '1') {
  document.body.classList.add('embedded');
}

let state = {
  classes: {},
  clients: {},
  models: { claude: {}, agy: {} }
};
let usageWindowDays = 7;

function fmtNum(n) {
  return Number(n || 0).toLocaleString();
}

function setUsageWindow(days) {
  usageWindowDays = days;
  document.querySelectorAll('#usageWindowSwitch button').forEach(b => {
    b.classList.toggle('active', Number(b.dataset.days) === days);
  });
  loadUsage();
}

function renderUsageRows(tbodyId, rows, keyName) {
  const tbody = document.getElementById(tbodyId);
  if (!rows || rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--muted); padding: 16px;">No data.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td><code>${esc(r[keyName])}</code></td>
      <td>${fmtNum(r.requests)}</td>
      <td>${fmtNum(r.tokens)}</td>
      <td>${fmtNum(r.input)}</td>
      <td>${fmtNum(r.output)}</td>
      <td>${fmtNum((r.cache_write || 0) + (r.cache_read || 0))}</td>
      <td>${fmtNum(r.unreported)}</td>
    </tr>
  `).join('');
}

function renderUsageChart(days) {
  const chart = document.getElementById('usageChart');
  chart.innerHTML = '';
  const maxTokens = Math.max(1, ...days.map(d => d.tokens));
  const showLabel = days.length <= 10;
  for (const d of days) {
    const col = document.createElement('div');
    col.className = 'usage-bar-col';
    const pct = Math.max(1, Math.round((d.tokens / maxTokens) * 100));
    const label = d.day.slice(5);
    col.innerHTML = `
      <div class="usage-bar" style="height: ${pct}%;" title="${esc(d.day)}: ${fmtNum(d.requests)} requests, ${fmtNum(d.tokens)} tokens"></div>
      ${showLabel ? `<div class="usage-bar-label">${esc(label)}</div>` : ''}
    `;
    chart.appendChild(col);
  }
}

async function loadUsage() {
  const body = document.getElementById('usageBody');
  const summary = document.getElementById('usageSummary');
  try {
    const res = await fetch('/api/aicli-usage?days=' + usageWindowDays);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (!data.ok) {
      body.innerHTML = `<div class="usage-error">${esc(data.message || 'aicli usage log not readable.')}</div>`;
      summary.textContent = '';
      return;
    }
    const totals = data.totals || { requests: 0, tokens: 0, unreported: 0 };
    if (!totals.requests) {
      body.innerHTML = '<div class="usage-empty">No aicli usage logged yet.</div>';
      summary.textContent = '';
      return;
    }
    body.innerHTML = `
      <div class="usage-chart" id="usageChart"></div>
      <div class="usage-tables">
        <div class="table-container">
          <table class="routes-table" id="usageByModelTable">
            <thead><tr><th>Model</th><th>Requests</th><th>Tokens</th><th>Input</th><th>Output</th><th>Cache</th><th>Unreported</th></tr></thead>
            <tbody id="usageByModelTbody"></tbody>
          </table>
        </div>
        <div class="table-container">
          <table class="routes-table" id="usageByClientTable">
            <thead><tr><th>Client</th><th>Requests</th><th>Tokens</th><th>Input</th><th>Output</th><th>Cache</th><th>Unreported</th></tr></thead>
            <tbody id="usageByClientTbody"></tbody>
          </table>
        </div>
      </div>
    `;
    summary.textContent = `${fmtNum(totals.requests)} requests, ${fmtNum(totals.tokens)} tokens over the last ${usageWindowDays} days (${fmtNum(totals.unreported)} with no token counts).`;
    renderUsageChart(data.days || []);
    renderUsageRows('usageByModelTbody', data.by_model, 'model');
    renderUsageRows('usageByClientTbody', data.by_client, 'client');
  } catch (err) {
    body.innerHTML = `<div class="usage-error">Failed to load usage: ${esc(err.message)}</div>`;
    summary.textContent = '';
  }
}

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
        <button type="button" class="btn danger small" onclick="removeClient(this.closest('tr').dataset.client)">Remove</button>
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
  loadUsage();
}

async function saveRoutes() {
  const payload = {
    classes: state.classes,
    clients: state.clients,
    optiplex_projects: state.optiplex_projects
  };
  const data = await postJSON('/api/ai-routes', payload);
  if (data.ok === false && !data.routes) {
    banner("Failed to save routes: " + (data.message || "request failed"), true);
    return;
  }
  banner("Routes saved successfully! Applied immediately across homelab and aicli.");
  loadRoutes();
}

document.addEventListener('DOMContentLoaded', loadRoutes);
