"""/tokens: on-demand verification of homelab API tokens and credentials."""

from .theme import THEME

TOKENS_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tokens & Credentials · __TITLE__</title>
<style>
  {THEME}
  .wrap { max-width: 1200px; margin: 0 auto; padding: 24px 18px 64px; }
  body.embedded .wrap { padding: 12px 14px; max-width: 100%; }
  body.embedded header .back { display: none; }
  header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px; margin-bottom: 8px; }
  h1 { font-size: 22px; margin: 0; display: flex; align-items: center; gap: 8px; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .top-right { display: flex; align-items: center; gap: 10px; }
  .lede { color: var(--muted); font-size: 13px; margin: 4px 0 16px; max-width: 85ch; line-height: 1.5; }
  
  /* Stats Cards */
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 18px; }
  .stat-card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; }
  .stat-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; margin-bottom: 4px; }
  .stat-value { font-size: 20px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
  .stat-value.active { color: var(--up); }
  .stat-value.warn { color: #d29922; }
  .stat-value.err { color: var(--down); }

  /* Table styling */
  .table-container { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; }
  table.token-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
  table.token-table th { background: var(--raise); color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; padding: 10px 14px; border-bottom: 1px solid var(--border); }
  table.token-table td { padding: 12px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }
  table.token-table tr:last-child td { border-bottom: none; }
  table.token-table tr:hover { background: rgba(255,255,255,0.02); }

  .svc-badge { font-size: 11px; padding: 2px 7px; border-radius: 4px; background: var(--raise); border: 1px solid var(--border); color: var(--text); font-weight: 600; display: inline-block; margin-bottom: 4px; }
  .var-name { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px; font-weight: 600; color: var(--text); display: block; word-break: break-all; }
  .masked-val { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; color: var(--muted); background: var(--bg); border: 1px solid var(--border); padding: 1px 6px; border-radius: 4px; display: inline-block; margin-top: 4px; }
  .path-cell { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; color: var(--muted); word-break: break-all; }
  .desc-cell { font-size: 12px; color: var(--muted); line-height: 1.4; max-width: 320px; }
  
  /* Status Badges */
  .status-badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 600; display: inline-flex; align-items: center; gap: 5px; }
  .status-badge.untested { color: var(--muted); background: var(--raise); border: 1px solid var(--border); }
  .status-badge.active { color: var(--up); background: rgba(63,185,80,0.12); border: 1px solid rgba(63,185,80,0.3); }
  .status-badge.warn { color: #d29922; background: rgba(210,153,34,0.12); border: 1px solid rgba(210,153,34,0.3); }
  .status-badge.error { color: var(--down); background: rgba(248,81,73,0.12); border: 1px solid rgba(248,81,73,0.3); }
  
  .status-msg { font-size: 11px; color: var(--muted); margin-top: 4px; line-height: 1.35; max-width: 280px; }
  .status-time { font-size: 10px; color: var(--muted); margin-top: 2px; opacity: 0.8; font-family: ui-monospace, monospace; }

  /* Buttons */
  button { background: var(--panel); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 5px 12px; font-size: 12px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; font-weight: 500; font-family: inherit; transition: all 0.15s ease; }
  button:hover { border-color: var(--muted); background: var(--raise); }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  button.btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); }
  button.btn-primary:hover { opacity: 0.9; }
  button.btn-sm { padding: 3px 8px; font-size: 11px; }

  .spinner { display: inline-block; width: 10px; height: 10px; border: 2px solid rgba(255,255,255,0.3); border-radius: 50%; border-top-color: currentColor; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <a href="/" class="back">← back to cockpit</a>
    <h1><span>🔑</span> API Tokens & Credentials</h1>
    <div class="top-right">
      <button type="button" id="btnRefresh" onclick="loadTokens()">↻ Refresh List</button>
      <button type="button" class="btn-primary" id="btnTestAll" onclick="testAllTokens()">▶ Test All Tokens</button>
    </div>
  </header>
  
  <p class="lede">
    Centralized credential roster across homelab services. 
    <strong>Tokens are tested on demand only</strong> to avoid unnecessary API calls or rate-limiting external services.
  </p>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Total Registered</div>
      <div class="stat-value" id="statTotal">--</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Active / Valid</div>
      <div class="stat-value active" id="statActive">--</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Untested</div>
      <div class="stat-value" id="statUntested">--</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Warnings / Errors</div>
      <div class="stat-value err" id="statIssues">--</div>
    </div>
  </div>

  <div class="table-container">
    <table class="token-table">
      <thead>
        <tr>
          <th>Service & Name</th>
          <th>Variable & Masked Token</th>
          <th>Config Location</th>
          <th>Scope & Policy</th>
          <th>Verification Status</th>
          <th style="text-align: right;">Action</th>
        </tr>
      </thead>
      <tbody id="tokensTbody">
        <tr><td colspan="6" style="text-align: center; color: var(--muted); padding: 24px;">Loading token roster…</td></tr>
      </tbody>
    </table>
  </div>
</div>

<script>
if (window.self !== window.top) {
  document.body.classList.add('embedded');
}

let tokensData = [];

async function loadTokens() {
  const tbody = document.getElementById("tokensTbody");
  try {
    const res = await fetch("/api/tokens");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    tokensData = data.tokens || [];
    renderTable();
    updateStats();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="color: var(--down); padding: 20px; text-align: center;">Failed to load tokens: ${err.message}</td></tr>`;
  }
}

function updateStats() {
  document.getElementById("statTotal").textContent = tokensData.length;
  let active = 0, untested = 0, issues = 0;
  tokensData.forEach(t => {
    if (t.status === "active") active++;
    else if (t.status === "untested") untested++;
    else issues++;
  });
  document.getElementById("statActive").textContent = active;
  document.getElementById("statUntested").textContent = untested;
  document.getElementById("statIssues").textContent = issues;
}

function renderTable() {
  const tbody = document.getElementById("tokensTbody");
  if (!tokensData.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="color: var(--muted); padding: 24px; text-align: center;">No tokens registered.</td></tr>`;
    return;
  }

  tbody.innerHTML = tokensData.map(t => {
    let badgeClass = "untested";
    let badgeText = t.badge || "Untested";
    if (t.status === "active") badgeClass = "active";
    else if (t.status === "warn") badgeClass = "warn";
    else if (t.status === "error") badgeClass = "error";

    const msg = t.message ? `<div class="status-msg">${escapeHtml(t.message)}</div>` : "";
    const time = t.tested_at ? `<div class="status-time">Checked: ${escapeHtml(t.tested_at)}</div>` : "";

    return `
      <tr id="row-${escapeHtml(t.id)}">
        <td>
          <span class="svc-badge">${escapeHtml(t.service)}</span>
          <div style="font-weight: 600; color: var(--text);">${escapeHtml(t.name)}</div>
        </td>
        <td>
          <span class="var-name">${escapeHtml(t.variable)}</span>
          <span class="masked-val">${escapeHtml(t.masked || "empty / missing")}</span>
        </td>
        <td class="path-cell">${escapeHtml(t.env_path)}</td>
        <td class="desc-cell">${escapeHtml(t.description)}</td>
        <td id="status-${escapeHtml(t.id)}">
          <span class="status-badge ${badgeClass}">${badgeText}</span>
          ${msg}
          ${time}
        </td>
        <td style="text-align: right;">
          <button type="button" class="btn-sm" id="btn-${escapeHtml(t.id)}" onclick="testSingle('${escapeHtml(t.id)}')">
            Test
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

async function testSingle(tokenId) {
  const btn = document.getElementById("btn-" + tokenId);
  const statusCell = document.getElementById("status-" + tokenId);
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> Testing…`;
  }
  try {
    const res = await fetch("/api/tokens/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: tokenId })
    });
    const result = await res.json();
    
    // Update local data
    const item = tokensData.find(t => t.id === tokenId);
    if (item) {
      item.status = result.status;
      item.badge = result.badge;
      item.message = result.message;
      item.tested_at = result.tested_at;
    }

    let badgeClass = result.status || "untested";
    statusCell.innerHTML = `
      <span class="status-badge ${badgeClass}">${escapeHtml(result.badge || "Done")}</span>
      <div class="status-msg">${escapeHtml(result.message || "")}</div>
      <div class="status-time">Checked: ${escapeHtml(result.tested_at || "")}</div>
    `;
    updateStats();
  } catch (err) {
    statusCell.innerHTML = `
      <span class="status-badge error">Error</span>
      <div class="status-msg">${escapeHtml(err.message)}</div>
    `;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Test";
    }
  }
}

async function testAllTokens() {
  const btn = document.getElementById("btnTestAll");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Testing all…`;

  try {
    const res = await fetch("/api/tokens/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ all: true })
    });
    const data = await res.json();
    if (data.results) {
      data.results.forEach(r => {
        const item = tokensData.find(t => t.id === r.id);
        if (item) {
          item.status = r.status;
          item.badge = r.badge;
          item.message = r.message;
          item.tested_at = r.tested_at;
        }
      });
      renderTable();
      updateStats();
    }
  } catch (err) {
    alert("Test All failed: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "▶ Test All Tokens";
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

document.addEventListener("DOMContentLoaded", loadTokens);
</script>
</body>
</html>
"""
