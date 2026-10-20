if (new URLSearchParams(window.location.search).get('embedded') === '1') {
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

    let maxTime = "";
    tokensData.forEach(t => {
      if (t.tested_at && (!maxTime || t.tested_at > maxTime)) {
        maxTime = t.tested_at;
      }
    });
    updateLastTestUI(maxTime);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="color: var(--down); padding: 20px; text-align: center;">Failed to load tokens: ${esc(err.message)}</td></tr>`;
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

// token status -> the shared theme's status-dot/badge modifier.
const STATUS_DOT = { active: "status-up", warn: "status-warn", error: "status-down", untested: "status-unknown" };
const STATUS_BADGE = { active: "up", warn: "warn", error: "down", untested: "" };

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
    const status = t.status || "untested";
    const dotClass = STATUS_DOT[status] || "status-unknown";
    const badgeClass = STATUS_BADGE[status] || "";
    const badgeText = t.badge || "Untested";

    const msg = t.message ? `<div class="status-resp">${esc(t.message)}</div>` : "";
    const time = t.tested_at ? `<div class="status-time">${esc(formatTime(t.tested_at))}</div>` : "";

    return `
      <tr id="row-${esc(t.id)}">
        <td id="status-${esc(t.id)}">
          <div class="status-badge-row">
            <span class="status-dot ${dotClass}"></span>
            <span class="badge ${badgeClass}">${esc(badgeText)}</span>
          </div>
          ${msg}
          ${time}
        </td>
        <td>
          <span class="svc-badge">${esc(t.service)}</span>
          <div class="token-title">${esc(t.name)}</div>
        </td>
        <td>
          <span class="code-token">${esc(t.variable)}</span>
          <span class="masked-token">${esc(t.masked || "empty / missing")}</span>
        </td>
        <td class="path-code">${esc(t.env_path)}</td>
        <td class="desc-muted">${esc(t.description)}</td>
        <td style="text-align: right;">
          <button type="button" class="btn secondary small" id="btn-${esc(t.id)}" onclick="testSingle('${esc(t.id)}')">
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
    const result = await postJSON("/api/tokens/test", { id: tokenId });
    if (!result.status) throw new Error(result.message || "request failed");

    const item = tokensData.find(t => t.id === tokenId);
    if (item) {
      item.status = result.status;
      item.badge = result.badge;
      item.message = result.message;
      item.tested_at = result.tested_at;
    }

    const dotClass = STATUS_DOT[result.status] || "status-unknown";
    const badgeClass = STATUS_BADGE[result.status] || "";
    statusCell.innerHTML = `
      <div class="status-badge-row">
        <span class="status-dot ${dotClass}"></span>
        <span class="badge ${badgeClass}">${esc(result.badge || "Done")}</span>
      </div>
      <div class="status-resp">${esc(result.message || "")}</div>
      <div class="status-time">${esc(formatTime(result.tested_at))}</div>
    `;
    updateStats();
    if (result.tested_at) {
      updateLastTestUI(result.tested_at);
    }
  } catch (err) {
    statusCell.innerHTML = `
      <div class="status-badge-row">
        <span class="status-dot status-down"></span>
        <span class="badge down">Error</span>
      </div>
      <div class="status-resp">${esc(err.message)}</div>
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
    const data = await postJSON("/api/tokens/test", { all: true });
    if (!data.results && data.ok === false) throw new Error(data.message || "request failed");
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

document.addEventListener("DOMContentLoaded", loadTokens);
