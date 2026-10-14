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
  header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px; }
  h1 { font-size: 22px; margin: 0; display: flex; align-items: center; gap: 8px; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .top-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .lede { color: var(--muted); font-size: 13px; margin: 8px 0 14px; max-width: 80ch; line-height: 1.5; }

  /* Toolbar */
  .meta-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; font-size: 12px; color: var(--muted); }
  .meta-counts { display: flex; align-items: center; gap: 8px; }
  .last-test-badge { display: inline-flex; align-items: center; gap: 6px; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; background: var(--panel); border: 1px solid var(--border); padding: 4px 10px; border-radius: 6px; color: var(--text); }
  .last-test-badge b { color: var(--muted); font-weight: normal; }

  /* Badges matching Cockpit & Cron */
  .badge { font-size: 11px; padding: 2px 7px; border-radius: 999px; background: var(--raise); border: 1px solid var(--border); color: var(--muted); font-weight: 500; display: inline-flex; align-items: center; gap: 4px; }
  .badge.active { color: var(--up); border-color: rgba(63,185,80,0.3); background: rgba(63,185,80,0.08); }
  .badge.error { color: var(--down); border-color: rgba(248,81,73,0.3); background: rgba(248,81,73,0.08); }
  .badge.warn { color: #d29922; border-color: rgba(210,153,34,0.3); background: rgba(210,153,34,0.08); }
  .badge.untested { color: var(--muted); border-color: var(--border); background: var(--raise); }

  /* Table layout matching cron.table */
  .table-container { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; margin-top: 6px; }
  table.cron-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
  table.cron-table th { background: var(--raise); color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; padding: 10px 14px; border-bottom: 1px solid var(--border); }
  table.cron-table td { padding: 12px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }
  table.cron-table tr:last-child td { border-bottom: none; }
  table.cron-table tr:hover { background: rgba(255,255,255,0.02); }

  .svc-badge { font-size: 11px; padding: 1px 6px; border-radius: 4px; background: var(--raise); border: 1px solid var(--border); color: var(--muted); font-weight: 600; display: inline-block; margin-bottom: 4px; }
  .token-title { font-weight: 600; font-size: 13px; color: var(--text); }
  .code-token { font-family: ui-monospace, SFMono-Regular, monospace; background: var(--bg); border: 1px solid var(--border); padding: 2px 6px; border-radius: 4px; font-size: 11px; display: inline-block; color: var(--text); }
  .masked-token { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; color: var(--muted); margin-top: 4px; display: block; word-break: break-all; }
  .path-code { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; color: var(--muted); word-break: break-all; }
  .desc-muted { font-size: 12px; color: var(--muted); line-height: 1.4; max-width: 280px; }
  .status-resp { font-size: 11px; color: var(--muted); margin-top: 4px; line-height: 1.35; max-width: 240px; word-break: break-word; }
  .status-time { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 10px; color: var(--muted); margin-top: 3px; opacity: 0.8; }

  /* Standard Cockpit buttons */
  button { background: var(--panel); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 4px 11px; font-size: 12px; cursor: pointer; display: inline-flex; align-items: center; gap: 5px; font-weight: 500; font-family: inherit; transition: all 0.12s ease; }
  button:hover { border-color: var(--muted); background: var(--raise); }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  button.btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); }
  button.btn-primary:hover { opacity: 0.9; }
  button.btn-sm { padding: 3px 8px; font-size: 11px; }

  .spinner { display: inline-block; width: 10px; height: 10px; border: 2px solid rgba(255,255,255,0.3); border-radius: 50%; border-top-color: currentColor; animation: spin 0.8s linear infinite; }
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
      <button type="button" id="btnRefresh" onclick="loadTokens(true)">↻ Refresh</button>
      <button type="button" class="btn-primary" id="btnTestAll" onclick="refreshAndTestTokens()">▶ Test All Tokens</button>
      <a class="back" href="/">&larr; Back to Cockpit</a>
    </div>
  </header>
  
  <p class="lede">Centralized credential inventory and live endpoint verification across homelab services. Tokens are tested on demand to avoid unnecessary external API consumption.</p>

  <div class="meta-toolbar">
    <div class="meta-counts" id="countsBar">
      <span id="statTotal">-- registered</span> ·
      <span style="color:var(--up)" id="statActive">-- active</span> ·
      <span style="color:var(--muted)" id="statUntested">-- untested</span> ·
      <span style="color:var(--down)" id="statIssues">-- issues</span>
    </div>
    <div class="last-test-badge" id="lastTestBadge">
      <b>Last full test:</b> <span id="lastTestTime">Never tested</span>
    </div>
  </div>

  <div class="table-container">
    <table class="cron-table token-table">
      <thead>
        <tr>
          <th style="width: 140px;">Status</th>
          <th style="width: 220px;">Service & Credential</th>
          <th style="width: 250px;">Environment Variable</th>
          <th style="width: 200px;">Config File</th>
          <th>Description & Scope</th>
          <th style="width: 75px; text-align: right;">Action</th>
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
  let active = 0, untested = 0, issues = 0;
  tokensData.forEach(t => {
    if (t.status === "active") active++;
    else if (t.status === "untested") untested++;
    else issues++;
  });
  document.getElementById("statTotal").textContent = tokensData.length + " registered";
  document.getElementById("statActive").textContent = active + " active";
  document.getElementById("statUntested").textContent = untested + " untested";
  document.getElementById("statIssues").textContent = issues + " issues";
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

    const msg = t.message ? `<div class="status-resp">${escapeHtml(t.message)}</div>` : "";
    const time = t.tested_at ? `<div class="status-time">${escapeHtml(formatTime(t.tested_at))}</div>` : "";

    return `
      <tr id="row-${escapeHtml(t.id)}">
        <td id="status-${escapeHtml(t.id)}">
          <span class="badge ${badgeClass}">${escapeHtml(badgeText)}</span>
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
      <span class="badge ${badgeClass}">${escapeHtml(result.badge || "Done")}</span>
      <div class="status-resp">${escapeHtml(result.message || "")}</div>
      <div class="status-time">${escapeHtml(formatTime(result.tested_at))}</div>
    `;
    updateStats();
    if (result.tested_at) {
      updateLastTestUI(result.tested_at);
    }
  } catch (err) {
    statusCell.innerHTML = `
      <span class="badge error">Error</span>
      <div class="status-resp">${escapeHtml(err.message)}</div>
    `;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Test";
    }
  }
}

async function refreshAndTestTokens() {
  const btn = document.getElementById("btnRefresh");
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
    btn.innerHTML = "↻ Refresh & Test All";
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
