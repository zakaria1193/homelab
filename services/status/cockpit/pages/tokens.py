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
  .wrap { max-width: 1100px; margin: 0 auto; padding: 24px 18px 64px; }
  body.embedded .wrap { padding: 12px 14px; max-width: 100%; }
  body.embedded header .back { display: none; }
  header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px; margin-bottom: 4px; }
  h1 { font-size: 20px; font-weight: 600; margin: 0; display: flex; align-items: center; gap: 8px; color: var(--text); }
  .back { color: var(--muted); text-decoration: none; font-size: 13px; display: inline-flex; align-items: center; gap: 4px; }
  .back:hover { color: var(--text); }
  .top-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .lede { color: var(--muted); font-size: 13px; margin: 6px 0 16px; max-width: 80ch; line-height: 1.5; }

  /* Totals pill bar matching main.py */
  .totals { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 12px 0 16px; }
  .pill { display: inline-flex; align-items: center; gap: 7px; background: var(--panel);
    border: 1px solid var(--border); border-radius: var(--radius-pill); padding: 4px 12px; font-size: 12px;
    color: var(--text); text-decoration: none; font-family: inherit; font-variant-numeric: tabular-nums; }
  .pill b { font-weight: 600; }
  .pill.up .dot { background: var(--up); }
  .pill.warn .dot { background: var(--warn); }
  .pill.down .dot { background: var(--down); }
  .pill.unknown .dot { background: var(--unknown); }
  .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
  .dot.up, .dot.active { background: var(--up); }
  .dot.down, .dot.error { background: var(--down); }
  .dot.warn { background: var(--warn); }
  .dot.untested, .dot.unknown { background: var(--unknown); }

  /* Filter bar matching main.py */
  .filter-bar { display: flex; gap: 10px; align-items: center; justify-content: space-between; flex-wrap: wrap; margin-bottom: 12px; }
  .search-input-wrapper { position: relative; display: inline-flex; align-items: center; flex: 1; max-width: 380px; }
  .search-input-wrapper .search-ico { position: absolute; left: 10px; width: 14px; height: 14px; color: var(--muted); pointer-events: none; }
  .filter-search-input { width: 100%; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text); padding: 7px 12px 7px 32px; font-size: 13px; font-family: inherit; outline: none; transition: border-color 0.15s ease, box-shadow 0.15s ease; }
  .filter-search-input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 20%, transparent); }
  .filter-select { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text); padding: 7px 10px; font-size: 12px; font-family: inherit; outline: none; cursor: pointer; }
  .filter-select:focus { border-color: var(--accent); }

  /* Table container matching Cockpit services-table */
  .table-container { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); overflow-x: auto; box-shadow: 0 1px 3px rgba(0,0,0,0.02); }
  table.token-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
  table.token-table th { background: var(--raise); color: var(--muted); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; padding: 10px 14px; border-bottom: 1px solid var(--border); white-space: nowrap; }
  table.token-table td { padding: 11px 14px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  table.token-table tr:last-child td { border-bottom: none; }
  table.token-table tbody tr:hover td { background: color-mix(in srgb, var(--raise) 70%, transparent); }

  /* Badges matching Cockpit & Cron */
  .badge { font-size: 11px; padding: 2px 8px; border-radius: var(--radius-pill); background: var(--raise); border: 1px solid var(--border); color: var(--muted); font-weight: 500; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
  .badge.active { color: var(--up); border-color: color-mix(in srgb, var(--up) 35%, var(--border)); background: color-mix(in srgb, var(--up) 10%, transparent); }
  .badge.error { color: var(--down); border-color: color-mix(in srgb, var(--down) 35%, var(--border)); background: color-mix(in srgb, var(--down) 10%, transparent); }
  .badge.warn { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 35%, var(--border)); background: color-mix(in srgb, var(--warn) 10%, transparent); }
  .badge.untested { color: var(--muted); border-color: var(--border); background: var(--raise); }

  .status-badge-row { display: inline-flex; align-items: center; gap: 6px; }
  .svc-badge { font-size: 11px; padding: 2px 7px; border-radius: 4px; background: var(--raise); border: 1px solid var(--border); color: var(--text); font-weight: 600; display: inline-block; margin-bottom: 3px; }
  .token-title { font-weight: 600; font-size: 13px; color: var(--text); line-height: 1.3; }
  .code-token { font-family: ui-monospace, SFMono-Regular, monospace; background: var(--raise); border: 1px solid var(--border); padding: 2px 6px; border-radius: 4px; font-size: 11.5px; display: inline-block; color: var(--text); }
  .masked-token { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; color: var(--muted); margin-top: 3px; display: block; word-break: break-all; }
  .path-code { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; color: var(--muted); word-break: break-all; }
  .desc-muted { font-size: 12px; color: var(--muted); line-height: 1.4; max-width: 320px; }
  .status-resp { font-size: 11px; color: var(--muted); margin-top: 4px; line-height: 1.35; max-width: 250px; word-break: break-word; }
  .status-time { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 10.5px; color: var(--faint); margin-top: 2px; }

  /* Standard Cockpit action buttons */
  .btn-table-action {
    display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 500;
    text-decoration: none; border: 1px solid var(--border); border-radius: var(--radius-sm);
    padding: 4px 10px; color: var(--text); background: var(--panel); white-space: nowrap;
    transition: all 0.15s ease; cursor: pointer; font-family: inherit; line-height: 1.2;
  }
  .btn-table-action:hover { background: var(--raise); border-color: var(--muted); color: var(--accent); }
  .btn-table-action:disabled { opacity: 0.5; cursor: not-allowed; }

  .btn-primary {
    background: var(--accent); color: var(--accent-contrast); border: 1px solid var(--accent);
    border-radius: var(--radius-sm); padding: 6px 14px; font-size: 12px; font-weight: 600;
    cursor: pointer; display: inline-flex; align-items: center; gap: 6px; transition: all 0.15s ease; font-family: inherit;
  }
  .btn-primary:hover { filter: brightness(1.08); }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

  .btn-secondary {
    background: var(--panel); color: var(--text); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 6px 12px; font-size: 12px; font-weight: 500;
    cursor: pointer; display: inline-flex; align-items: center; gap: 6px; transition: all 0.15s ease; font-family: inherit;
  }
  .btn-secondary:hover { background: var(--raise); border-color: var(--muted); }
  .btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }

  .spinner {
    display: inline-block; width: 11px; height: 11px;
    border: 2px solid color-mix(in srgb, currentColor 30%, transparent);
    border-top-color: currentColor; border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  footer { margin-top: 36px; color: var(--muted); font-size: 12px; }
  footer code { font-family: ui-monospace, SFMono-Regular, monospace; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🔑 API Tokens & Credentials</h1>
    <div class="top-right">
      <button type="button" class="btn-secondary" id="btnRefresh" onclick="loadTokens(true)">↻ Refresh</button>
      <button type="button" class="btn-primary" id="btnTestAll" onclick="refreshAndTestTokens()">▶ Test All Tokens</button>
      <a class="back" href="/">&larr; Back to Cockpit</a>
    </div>
  </header>
  
  <p class="lede">Centralized credential inventory and live endpoint verification across homelab services. Tokens are tested on demand to avoid unnecessary external API consumption.</p>

  <div class="totals" id="totalsBar">
    <div class="pill"><b id="statTotal">--</b> registered</div>
    <div class="pill up"><span class="dot up"></span> <b id="statActive">--</b> active</div>
    <div class="pill warn"><span class="dot warn"></span> <b id="statWarn">--</b> warnings</div>
    <div class="pill down"><span class="dot down"></span> <b id="statError">--</b> errors</div>
    <div class="pill unknown"><span class="dot unknown"></span> <b id="statUntested">--</b> untested</div>
    <div class="pill" id="lastTestPill" style="margin-left: auto;">
      <span style="color:var(--muted)">Last test:</span> <b id="lastTestTime">--</b>
    </div>
  </div>

  <div class="filter-bar">
    <div class="search-input-wrapper">
      <svg class="search-ico" viewBox="0 0 16 16" fill="currentColor">
        <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>
      </svg>
      <input type="search" id="tokenSearch" class="filter-search-input" placeholder="Search tokens by service, variable, path, or status..." oninput="renderTable()">
    </div>
    <select id="statusFilter" class="filter-select" onchange="renderTable()">
      <option value="all">All statuses</option>
      <option value="active">Active only</option>
      <option value="issues">Issues only (warning / error)</option>
      <option value="untested">Untested only</option>
    </select>
  </div>

  <div class="table-container">
    <table class="cron-table token-table">
      <thead>
        <tr>
          <th style="width: 155px;">Status</th>
          <th style="width: 210px;">Service & Credential</th>
          <th style="width: 240px;">Environment Variable</th>
          <th style="width: 200px;">Config File</th>
          <th>Description & Scope</th>
          <th style="width: 85px; text-align: right;">Action</th>
        </tr>
      </thead>
      <tbody id="tokensTbody">
        <tr><td colspan="6" style="text-align: center; color: var(--muted); padding: 24px;">Loading token roster...</td></tr>
      </tbody>
    </table>
  </div>

  <footer>
    Registered across homelab services · Run manually anytime via <code>make test-tokens</code>
  </footer>
</div>

<script>
if (window.self !== window.top) {
  document.body.classList.add('embedded');
}

let tokensData = [];

function formatTime(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    const timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    if (isToday) {
      return "Today at " + timeStr;
    }
    return d.toISOString().slice(0, 10) + " " + timeStr;
  } catch (e) {
    return isoStr;
  }
}

function updateLastTestUI(timestamp) {
  const badge = document.getElementById("lastTestTime");
  if (!badge) return;
  if (!timestamp) {
    const saved = localStorage.getItem("homelab_tokens_last_test");
    if (saved) {
      badge.textContent = formatTime(saved);
      return;
    }
    badge.textContent = "Never tested";
    return;
  }
  localStorage.setItem("homelab_tokens_last_test", timestamp);
  badge.textContent = formatTime(timestamp);
}

async function loadTokens(userTriggered) {
  const btn = document.getElementById("btnRefresh");
  if (userTriggered && btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> Refreshing...`;
  }
  const tbody = document.getElementById("tokensTbody");
  try {
    const res = await fetch("/api/tokens");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    tokensData = data.tokens || [];
    renderTable();
    updateStats();

    // Check if any tokens have tested_at timestamps
    let maxTime = "";
    tokensData.forEach(t => {
      if (t.tested_at && (!maxTime || t.tested_at > maxTime)) {
        maxTime = t.tested_at;
      }
    });
    updateLastTestUI(maxTime);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="color: var(--down); padding: 20px; text-align: center;">Failed to load tokens: ${err.message}</td></tr>`;
  } finally {
    if (userTriggered && btn) {
      btn.disabled = false;
      btn.innerHTML = "↻ Refresh";
    }
  }
}

function updateStats() {
  let active = 0, untested = 0, warn = 0, error = 0;
  tokensData.forEach(t => {
    if (t.status === "active") active++;
    else if (t.status === "untested") untested++;
    else if (t.status === "warn") warn++;
    else error++;
  });
  const elTotal = document.getElementById("statTotal");
  const elActive = document.getElementById("statActive");
  const elWarn = document.getElementById("statWarn");
  const elError = document.getElementById("statError");
  const elUntested = document.getElementById("statUntested");
  if (elTotal) elTotal.textContent = tokensData.length;
  if (elActive) elActive.textContent = active;
  if (elWarn) elWarn.textContent = warn;
  if (elError) elError.textContent = error;
  if (elUntested) elUntested.textContent = untested;
}

function renderTable() {
  const tbody = document.getElementById("tokensTbody");
  const query = (document.getElementById("tokenSearch")?.value || "").toLowerCase().trim();
  const filter = document.getElementById("statusFilter")?.value || "all";

  let list = tokensData.filter(t => {
    if (filter === "active" && t.status !== "active") return false;
    if (filter === "issues" && (t.status !== "warn" && t.status !== "error")) return false;
    if (filter === "untested" && t.status !== "untested") return false;

    if (!query) return true;
    const haystack = [t.name, t.service, t.variable, t.env_path, t.description, t.status, t.badge, t.message]
      .join(" ").toLowerCase();
    return haystack.includes(query);
  });

  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="color: var(--muted); padding: 32px; text-align: center;">No credentials match the search or filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = list.map(t => {
    let badgeClass = "untested";
    let badgeText = t.badge || "Untested";
    if (t.status === "active") badgeClass = "active";
    else if (t.status === "warn") badgeClass = "warn";
    else if (t.status === "error") badgeClass = "error";

    const msg = t.message ? `<div class="status-resp">${escapeHtml(t.message)}</div>` : "";
    const time = t.tested_at ? `<div class="status-time">${escapeHtml(formatTime(t.tested_at))}</div>` : "";

    return `
      <tr id="row-${escapeHtml(t.id)}">
        <td id="status-${escapeHtml(t.id)}">
          <div class="status-badge-row">
            <span class="dot ${badgeClass}"></span>
            <span class="badge ${badgeClass}">${escapeHtml(badgeText)}</span>
          </div>
          ${msg}
          ${time}
        </td>
        <td>
          <span class="svc-badge">${escapeHtml(t.service)}</span>
          <div class="token-title">${escapeHtml(t.name)}</div>
        </td>
        <td>
          <span class="code-token">${escapeHtml(t.variable)}</span>
          <span class="masked-token">${escapeHtml(t.masked || "empty / missing")}</span>
        </td>
        <td class="path-code">${escapeHtml(t.env_path)}</td>
        <td class="desc-muted">${escapeHtml(t.description)}</td>
        <td style="text-align: right;">
          <button type="button" class="btn-table-action" id="btn-${escapeHtml(t.id)}" onclick="testSingle('${escapeHtml(t.id)}')">
            ▶ Test
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
    btn.innerHTML = `<span class="spinner"></span>`;
  }
  try {
    const res = await fetch("/api/tokens/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: tokenId })
    });
    const result = await res.json();

    const item = tokensData.find(t => t.id === tokenId);
    if (item) {
      item.status = result.status;
      item.badge = result.badge;
      item.message = result.message;
      item.tested_at = result.tested_at;
    }

    let badgeClass = result.status || "untested";
    statusCell.innerHTML = `
      <div class="status-badge-row">
        <span class="dot ${badgeClass}"></span>
        <span class="badge ${badgeClass}">${escapeHtml(result.badge || "Done")}</span>
      </div>
      <div class="status-resp">${escapeHtml(result.message || "")}</div>
      <div class="status-time">${escapeHtml(formatTime(result.tested_at))}</div>
    `;
    updateStats();
    if (result.tested_at) {
      updateLastTestUI(result.tested_at);
    }
  } catch (err) {
    statusCell.innerHTML = `
      <div class="status-badge-row">
        <span class="dot error"></span>
        <span class="badge error">Error</span>
      </div>
      <div class="status-resp">${escapeHtml(err.message)}</div>
    `;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = "▶ Test";
    }
  }
}

async function refreshAndTestTokens() {
  const btn = document.getElementById("btnTestAll");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Testing all...`;

  try {
    const res = await fetch("/api/tokens/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ all: true })
    });
    const data = await res.json();
    if (data.results) {
      let latestTime = new Date().toISOString();
      data.results.forEach(r => {
        const item = tokensData.find(t => t.id === r.id);
        if (item) {
          item.status = r.status;
          item.badge = r.badge;
          item.message = r.message;
          item.tested_at = r.tested_at || latestTime;
        }
        if (r.tested_at) latestTime = r.tested_at;
      });
      renderTable();
      updateStats();
      updateLastTestUI(latestTime);
    }
  } catch (err) {
    alert("Token test failed: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = "▶ Test All Tokens";
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
