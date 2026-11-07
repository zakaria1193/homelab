// The GitHub limits page. Everything comes from /api/github-limits, which
// answers at once and collects in the background: poll fast only while it does.
if (new URLSearchParams(window.location.search).get("embedded") === "1") {
  document.body.classList.add("embedded");
}

const num = n => Number(n || 0).toLocaleString("en-US");

function size(bytes) {
  const n = Number(bytes || 0);
  if (n >= 1e9) return (n / 1e9).toFixed(1) + " GB";
  if (n >= 1e6) return Math.round(n / 1e6) + " MB";
  if (n >= 1e3) return Math.round(n / 1e3) + " KB";
  return n + " B";
}

function meter(ratio, cls) {
  const pct = Math.min(100, Math.max(0, ratio * 100));
  return `<div class="bar ${cls || ""}"><i style="width:${pct.toFixed(1)}%"></i></div>`;
}

function level(ratio) {
  return ratio >= 1 ? "hot" : ratio >= 0.8 ? "warn" : "";
}

function renderTiles(d) {
  const m = d.minutes, s = d.storage;
  const pace = m.projected;
  let paceText = `<div class="state">Too early in the month for a pace</div>`;
  if (pace !== null && pace !== undefined) {
    const over = pace > m.limit;
    paceText = `<div class="state ${over ? "warn" : "ok"}">${over ? "⚠ On pace to go over" : "✓ On pace to stay under"}: about ${num(pace)} by month end</div>`;
  }
  const previous = m.previous === null || m.previous === undefined ? ""
    : `<div class="detail">${esc(m.previous_month)}: ${num(m.previous)} minutes</div>`;
  const artRatio = s.artifact_bytes / s.artifact_limit_bytes;
  const artOver = artRatio >= 1;
  document.getElementById("tiles").innerHTML = `
    <div class="card tile">
      <div class="label">Actions minutes this month</div>
      <div class="detail">One pool shared by all your private repos. Public repos are free and not counted.</div>
      <div class="value">${num(m.used)} <small>of ${num(m.limit)}</small></div>
      ${meter(m.used / m.limit, level(m.used / m.limit))}
      ${paceText}${previous}
    </div>
    <div class="card tile">
      <div class="label">Artifact storage held now</div>
      <div class="detail">One pool shared by all your private repos. Public repos are not counted.</div>
      <div class="value">${size(s.artifact_bytes)} <small>of ${size(s.artifact_limit_bytes)}</small></div>
      ${meter(artRatio, level(artRatio))}
      <div class="state ${artOver ? "hot" : "ok"}">${artOver ? "⚠ Over the included amount" : "✓ Within the included amount"}</div>
      <div class="detail">GitHub bills the average over the month, not this figure</div>
    </div>
    <div class="card tile">
      <div class="label">Actions caches</div>
      <div class="value">${size(s.cache_bytes)}</div>
      <div class="detail">Limit is ${size(s.cache_limit_bytes)} per repo; above it GitHub drops the oldest</div>
    </div>`;
}

function renderDays(d) {
  const days = d.minutes.days;
  const max = Math.max(1, ...days.map(x => x.minutes));
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById("days").innerHTML = days.map((x, i) => {
    const n = Number(x.day.slice(8));
    const showLabel = n === 1 || n % 5 === 0;
    return `<div class="col${x.day > today ? " future" : ""}" title="${esc(x.day)}: ${num(x.minutes)} minutes">
      <i style="height:${(x.minutes / max * 100).toFixed(1)}%"></i>
      ${showLabel ? `<span>${n}</span>` : ""}</div>`;
  }).join("");
  document.getElementById("daysMeta").textContent = `${d.month}, highest ${num(max)} minutes`;
}

function renderRepos(d) {
  const repos = d.minutes.repos;
  const el = document.getElementById("repos");
  if (!repos.length) {
    el.innerHTML = `<tr><td class="muted">No runs in private repos yet this month.</td></tr>`;
    return;
  }
  const used = Math.max(1, d.minutes.used);
  const lastLabel = d.minutes.previous_month || "Last month";
  el.innerHTML = `<tr><th>Repo / workflow</th><th>Runs</th><th>Minutes</th><th></th><th>Share</th><th>${esc(lastLabel)}</th></tr>` +
    repos.map(r => `<tr>
        <td><code>${esc(r.name)}</code></td><td>${num(r.runs)}</td><td>${num(r.minutes)}</td>
        <td class="share">${meter(r.minutes / used, "plain")}</td>
        <td>${Math.round(r.minutes / used * 100)}%</td><td>${num(r.previous)}</td></tr>` +
      r.workflows.map(w => `<tr class="sub">
        <td>${esc(w.name)}</td><td>${num(w.runs)}</td><td>${num(w.minutes)}</td><td></td><td></td><td></td></tr>`).join("")
    ).join("");
}

function renderStorage(d) {
  const s = d.storage;
  const el = document.getElementById("storage");
  document.getElementById("storageMeta").textContent = "private repos, right now";
  if (!s.repos.length) {
    el.innerHTML = `<tr><td class="muted">No artifacts or caches in private repos.</td></tr>`;
    return;
  }
  el.innerHTML = `<tr><th>Repo / artifact</th><th>Artifacts</th><th>Caches</th><th>Cache entries</th></tr>` +
    s.repos.map(r => `<tr>
        <td><code>${esc(r.name)}</code></td><td>${size(r.artifact_bytes)}</td>
        <td>${size(r.cache_bytes)}${r.cache_bytes > s.cache_limit_bytes ? ` <span class="flag">⚠ over limit</span>` : ""}</td>
        <td>${num(r.cache_count)}</td></tr>` +
      r.top_artifacts.map(a => `<tr class="sub">
        <td>${esc(a.name)} × ${num(a.count)}</td><td>${size(a.bytes)}</td><td></td><td></td></tr>`).join("")
    ).join("");
}

function renderRate(d) {
  const el = document.getElementById("rate");
  if (!d.rate || !d.rate.length) {
    el.innerHTML = `<div class="muted small">Reading the counters…</div>`;
    return;
  }
  el.innerHTML = d.rate.map(r => {
    const ratio = r.limit ? r.used / r.limit : 0;
    const reset = r.reset ? new Date(r.reset * 1000).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"}) : "";
    return `<div class="meter" title="Resets at ${esc(reset)}"><span><code>${esc(r.name)}</code></span>
      ${meter(ratio, level(ratio))}<span class="count">${num(r.used)} of ${num(r.limit)}</span></div>`;
  }).join("");
}

function render(d) {
  const notice = document.getElementById("notice");
  const lines = [d.message, ...(d.problems || [])].filter(Boolean);
  notice.hidden = !lines.length;
  notice.textContent = lines.join(" · ");

  const updated = document.getElementById("updated");
  if (d.refreshing) updated.textContent = "Counting runs…";
  else if (d.updated_at) updated.textContent = "Updated " + new Date(d.updated_at).toLocaleString();
  else updated.textContent = "";

  renderRate(d);
  if (!d.minutes) {
    if (d.refreshing) {
      document.getElementById("tiles").innerHTML =
        `<div class="card tile muted">Counting this month's runs for the first time. This takes a minute or two.</div>`;
    }
    return;
  }
  renderTiles(d);
  renderDays(d);
  renderRepos(d);
  renderStorage(d);
  document.getElementById("note").textContent =
    `Counted by the cockpit from the ${num(d.repos_checked)} private repos you own. They share one account-wide pool; public repos and repos owned by an organization are not included. Each job rounded up to a whole minute, ` +
    `Windows counted twice and macOS ten times, public repos and self-hosted runners free. ` +
    `It is an estimate, not your invoice. The limits assume the Free plan; ` +
    `set STATUS_GITHUB_MINUTES_LIMIT and STATUS_GITHUB_ARTIFACT_LIMIT_MB if yours differs. ` +
    `"This month" runs from the billing day set in STATUS_GITHUB_BILLING_DAY (default the 1st). ` +
    `Package and Git LFS storage are not counted.`;
}

async function load() {
  let d = null;
  try {
    d = await (await fetch("/api/github-limits", {headers: {"Accept": "application/json"}})).json();
    render(d);
  } catch (err) {
    const notice = document.getElementById("notice");
    notice.hidden = false;
    notice.textContent = "Could not reach the cockpit: " + err;
  }
  setTimeout(load, d && d.refreshing ? 3000 : 60000);
}

load();
