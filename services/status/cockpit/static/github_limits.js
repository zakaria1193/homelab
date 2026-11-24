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
  const m = d.minutes, s = d.storage, b = d.billing;
  const usedMin = b && b.minutes_used !== undefined ? b.minutes_used : m.used;
  const minRatio = usedMin / m.limit;
  const pace = m.projected;
  let paceText = `<div class="state">Too early in the month for a pace</div>`;
  if (usedMin >= m.limit) {
    paceText = `<div class="state hot">⚠ At or over the ${num(m.limit)}-minute monthly allowance</div>`;
  } else if (pace !== null && pace !== undefined) {
    const over = pace > m.limit;
    paceText = `<div class="state ${over ? "warn" : "ok"}">${over ? "⚠ On pace to go over" : "✓ On pace to stay under"}: about ${num(pace)} by month end</div>`;
  }
  const skuParts = b && b.minutes_by_sku
    ? Object.entries(b.minutes_by_sku).map(([k, v]) => `${esc(k.replace(/^Actions /, ""))}: ${num(v)}`).join(" · ")
    : "";
  const minMeta = b
    ? `<div class="detail">Official GitHub Billing API${skuParts ? ` (${skuParts})` : ""}</div>`
    : `<div class="detail">One pool shared by all your private repos. Public repos are free and not counted.</div>`;
  const previous = m.previous === null || m.previous === undefined ? ""
    : `<div class="detail">${esc(m.previous_month)}: ${num(m.previous)} minutes (estimated)</div>`;

  const quotaHit = Boolean(s.quota_exceeded);
  let storageValue, storageSub, storageRatio, storageDetail;
  if (b && b.storage_gb_hours !== undefined && b.storage_limit_gb_hours) {
    storageRatio = b.storage_gb_hours / b.storage_limit_gb_hours;
    storageValue = `${b.storage_gb_hours.toFixed(1)} GB-h <small>of ${Math.round(b.storage_limit_gb_hours)} GB-h</small>`;
    storageSub = `Official monthly cumulative usage (~${b.storage_mb_month.toFixed(0)} MB-month avg vs ${Math.round(s.artifact_limit_bytes / 1e6)} MB limit).`;
    const pkgText = `${num(b.private_packages_count)} private packages (${num(b.packages_count)} total)`;
    storageDetail = quotaHit && s.quota_repos && s.quota_repos.length
      ? `<div class="detail" style="color:var(--down)">Failing in: ${esc(s.quota_repos.join(", "))}. Live artifacts now: ${size(s.artifact_bytes)} · ${pkgText}.</div>`
      : `<div class="detail">Live artifacts now: ${size(s.artifact_bytes)} · ${pkgText}</div>`;
  } else {
    storageRatio = s.artifact_bytes / s.artifact_limit_bytes;
    storageValue = `${size(s.artifact_bytes)} <small>of ${size(s.artifact_limit_bytes)}</small>`;
    storageSub = `One pool shared by all your private repos. Public repos are not counted.`;
    storageDetail = quotaHit && s.quota_repos && s.quota_repos.length
      ? `<div class="detail" style="color:var(--down)">Failing in: ${esc(s.quota_repos.join(", "))}. Private GitHub Packages (GHCR) share this 500 MB quota.</div>`
      : `<div class="detail">GitHub bills the average over the month, not this figure</div>`;
  }
  const artOver = storageRatio >= 1 || quotaHit;
  const ratioForMeter = quotaHit ? Math.max(storageRatio, 1.0) : storageRatio;
  const meterLevel = quotaHit ? "hot" : level(storageRatio);
  const stateClass = artOver ? "hot" : "ok";
  const stateText = quotaHit
    ? `⚠ Storage quota hit: CI uploads failing`
    : (artOver ? `⚠ Over the included monthly storage` : `✓ Within the included amount`);

  document.getElementById("tiles").innerHTML = `
    <div class="card tile">
      <div class="label">Actions minutes this month</div>
      ${minMeta}
      <div class="value">${num(usedMin)} <small>of ${num(m.limit)}</small></div>
      ${meter(minRatio, level(minRatio))}
      ${paceText}${previous}
    </div>
    <div class="card tile">
      <div class="label">${b ? "Actions &amp; Package storage (this month)" : "Artifact storage held now"}</div>
      <div class="detail">${storageSub}</div>
      <div class="value">${storageValue}</div>
      ${meter(ratioForMeter, meterLevel)}
      <div class="state ${stateClass}">${stateText}</div>
      ${storageDetail}
    </div>
    <div class="card tile">
      <div class="label">Actions caches</div>
      <div class="value">${size(s.cache_bytes)}</div>
      <div class="detail">Limit is ${size(s.cache_limit_bytes)} per repo; above it GitHub drops the oldest</div>
    </div>`;
}

const PALETTE = ["#4f8ef7", "#f0883e", "#3fb950", "#bc8cff", "#e5534b", "#39c5cf", "#d4a72c", "#8b949e"];
const RANGE_LABEL = {"7d": "7 days", "14d": "14 days", "30d": "30 days", "month": "the billing month"};
let range = "30d";
try { range = localStorage.getItem("github_limits_range") || "30d"; } catch (e) { /* private window */ }
if (!RANGE_LABEL[range]) range = "30d";
let last = null;

// The days a range covers, as indexes into the 30-day series: the last N days,
// or from the billing-month start.
function rangeDays(d) {
  const days = d.minutes.series_days || [];
  if (range === "month") {
    const start = d.month + "-01";
    const first = days.findIndex(x => x >= start);
    return days.map((day, i) => i).slice(first < 0 ? days.length : first);
  }
  const n = parseInt(range, 10);
  return days.map((day, i) => i).slice(-n);
}

// Repos coloured by their total in the range; the tail shares "other".
function groupByRepo(lines, idx) {
  const names = Object.keys(lines).sort((a, b) =>
    idx.reduce((t, i) => t + lines[b][i], 0) - idx.reduce((t, i) => t + lines[a][i], 0))
    .filter(n => idx.some(i => lines[n][i]));
  const shown = names.slice(0, PALETTE.length - 1), rest = names.slice(shown.length);
  const groups = shown.map((n, i) => ({name: n, color: PALETTE[i], line: lines[n]}));
  if (rest.length) {
    const n = lines[names[0]].length;
    groups.push({name: `other (${rest.length})`, color: PALETTE[PALETTE.length - 1],
      line: Array.from({length: n}, (_, i) => rest.reduce((t, r) => t + lines[r][i], 0))});
  }
  return groups;
}

// Stacked bars, one segment per repo per day.
function stackChart(chartId, legendId, labels, idx, groups, unit) {
  const totals = idx.map(i => groups.reduce((t, g) => t + g.line[i], 0));
  const max = Math.max(1, ...totals);
  const today = new Date().toISOString().slice(0, 10);
  const every = Math.ceil(idx.length / 15);
  document.getElementById(chartId).innerHTML = idx.map((i, k) => {
    const day = labels[i];
    const parts = groups.filter(g => g.line[i]);
    const tip = [`${day}: ${unit(totals[k])}`, ...parts.map(g => `${g.name}: ${unit(g.line[i])}`)].join("\n");
    const segs = parts.map(g => `<i style="height:${(g.line[i] / max * 100).toFixed(1)}%;background:${g.color}"></i>`).join("");
    return `<div class="col${day > today ? " future" : ""}" title="${esc(tip)}">${segs}
      ${k % every === 0 ? `<span>${day.slice(5)}</span>` : ""}</div>`;
  }).join("");
  document.getElementById(legendId).innerHTML = groups.map(g =>
    `<span class="key"><b style="background:${g.color}"></b>${esc(g.name)} <small>${unit(idx.reduce((t, i) => t + g.line[i], 0))}</small></span>`).join("");
  return max;
}

function renderDays(d) {
  const idx = rangeDays(d);
  const groups = groupByRepo(d.minutes.series || {}, idx);
  const max = stackChart("days", "daysLegend", d.minutes.series_days, idx, groups, n => `${num(n)} min`);
  document.getElementById("daysMeta").textContent = `last ${RANGE_LABEL[range]}, busiest day ${num(max)} minutes`;
}

function renderRepos(d) {
  const el = document.getElementById("repos");
  const idx = rangeDays(d);
  const series = d.minutes.series || {};
  const rows = Object.keys(series).map(n => ({name: n, minutes: idx.reduce((t, i) => t + series[n][i], 0)}))
    .filter(r => r.minutes).sort((a, b) => b.minutes - a.minutes);
  document.getElementById("reposMeta").textContent = `private repos, ${RANGE_LABEL[range]}`;
  if (!rows.length) {
    el.innerHTML = `<tr><td class="muted">No runs in private repos in this range.</td></tr>`;
    return;
  }
  const total = Math.max(1, rows.reduce((t, r) => t + r.minutes, 0));
  const month = Object.fromEntries(d.minutes.repos.map(r => [r.name, r]));
  const lastLabel = d.minutes.previous_month || "Last month";
  el.innerHTML = `<tr><th>Repo / workflow</th><th>Runs this month</th><th>Minutes</th><th></th><th>Share</th><th>${esc(lastLabel)}</th></tr>` +
    rows.map(r => {
      const m = month[r.name] || {runs: 0, previous: 0, workflows: []};
      return `<tr>
        <td><code>${esc(r.name)}</code></td><td>${num(m.runs)}</td><td>${num(r.minutes)}</td>
        <td class="share">${meter(r.minutes / total, "plain")}</td>
        <td>${Math.round(r.minutes / total * 100)}%</td><td>${num(m.previous)}</td></tr>` +
      (range === "month" ? m.workflows.map(w => `<tr class="sub">
        <td>${esc(w.name)}</td><td>${num(w.runs)}</td><td>${num(w.minutes)}</td><td></td><td></td><td></td></tr>`).join("") : "");
    }).join("");
}

function renderUploads(d) {
  const s = d.storage;
  const labels = d.minutes.series_days || [];
  const idx = rangeDays(d);
  const lines = {};
  for (const r of s.repos) {
    const line = labels.map(day => (r.by_day || {})[day] || 0);
    if (line.some(Boolean)) lines[r.name] = line;
  }
  const groups = groupByRepo(lines, idx);
  const el = document.getElementById("upDays");
  if (!groups.length) {
    el.innerHTML = `<div class="muted">No artifacts still held were uploaded in this range.</div>`;
    document.getElementById("upLegend").innerHTML = "";
  } else {
    stackChart("upDays", "upLegend", labels, idx, groups, size);
  }
  document.getElementById("upMeta").textContent =
    `artifacts still held, by upload day, last ${RANGE_LABEL[range]}`;
}

function renderStorage(d) {
  const s = d.storage;
  const b = d.billing;
  const el = document.getElementById("storage");
  const billedMap = Object.fromEntries(((b && b.storage_by_repo) || []).map(r => [r.name, r]));
  const hasBilling = Object.keys(billedMap).length > 0;
  document.getElementById("storageMeta").textContent = hasBilling
    ? "private repos: live artifacts/caches + official billed GB-h this month"
    : "private repos, right now";

  const byName = new Map(s.repos.map(r => [r.name, r]));
  for (const br of (b && b.storage_by_repo) || []) {
    if (!byName.has(br.name)) {
      byName.set(br.name, {
        name: br.name,
        artifact_bytes: 0,
        cache_bytes: 0,
        cache_count: 0,
        top_artifacts: [],
        by_day: {},
        quota_failure: false,
      });
    }
  }
  const rows = Array.from(byName.values()).sort((a, c) => {
    const ba = (billedMap[a.name] || {}).gb_hours || 0;
    const bc = (billedMap[c.name] || {}).gb_hours || 0;
    if (bc !== ba) return bc - ba;
    return (c.artifact_bytes + c.cache_bytes) - (a.artifact_bytes + a.cache_bytes);
  });

  if (!rows.length) {
    el.innerHTML = `<tr><td class="muted">No artifacts, caches, or billed storage in private repos.</td></tr>`;
    return;
  }
  const idxS = rangeDays(last);
  const labelsS = last.minutes.series_days || [];
  const daysIn = new Set(idxS.map(i => labelsS[i]));
  const uploaded = r => Object.entries(r.by_day || {}).reduce((t, [day, b]) => t + (daysIn.has(day) ? b : 0), 0);
  const billedCol = hasBilling ? `<th>Billed (GB-h)</th>` : "";
  el.innerHTML = `<tr><th>Repo / artifact</th>${billedCol}<th>Artifacts now</th><th>Uploaded in range</th><th>Caches</th><th>Cache entries</th></tr>` +
    rows.map(r => {
      const br = billedMap[r.name];
      const billedCell = hasBilling
        ? `<td>${br ? `${br.gb_hours.toFixed(2)} GB-h` : "—"}</td>`
        : "";
      return `<tr>
        <td><code>${esc(r.name)}</code>${r.quota_failure ? ` <span class="flag">⚠ quota exceeded</span>` : ""}</td>
        ${billedCell}
        <td>${size(r.artifact_bytes)}</td><td>${size(uploaded(r))}</td>
        <td>${size(r.cache_bytes)}${r.cache_bytes > s.cache_limit_bytes ? ` <span class="flag">⚠ over limit</span>` : ""}</td>
        <td>${num(r.cache_count)}</td></tr>` +
      (r.top_artifacts || []).map(a => `<tr class="sub">
        <td>${esc(a.name)} × ${num(a.count)}</td>${hasBilling ? "<td></td>" : ""}<td>${size(a.bytes)}</td><td></td><td></td><td></td></tr>`).join("");
    }).join("");
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
  const loading = document.getElementById("loadingOverlay");
  const content = document.getElementById("content");
  const notice = document.getElementById("notice");
  const updated = document.getElementById("updated");

  if (d.refreshing || (!d.minutes && !d.message)) {
    notice.hidden = true;
    content.hidden = true;
    loading.hidden = false;
    updated.textContent = "Refreshing…";
    return;
  }

  loading.hidden = true;
  content.hidden = false;

  const lines = [d.message, ...(d.problems || [])].filter(Boolean);
  notice.hidden = !lines.length;
  notice.textContent = lines.join(" · ");

  if (d.updated_at) updated.textContent = "Updated " + new Date(d.updated_at).toLocaleString();
  else updated.textContent = "";

  renderRate(d);
  if (!d.minutes) {
    return;
  }
  renderTiles(d);
  last = d;
  renderDays(d);
  renderUploads(d);
  renderRepos(d);
  renderStorage(d);
  const billingNote = d.billing
    ? `Official monthly minutes, cumulative storage GB-hours, and package counts come from GitHub's Billing & Packages APIs via GH_TOKEN_ADMIN. `
    : `Package and Git LFS storage are not counted (set GH_TOKEN_ADMIN to include official Billing & Packages APIs). `;
  document.getElementById("note").textContent =
    `${billingNote}` +
    `Per-repo daily charts are counted from the ${num(d.repos_checked)} private repos you own (each job rounded up to a whole minute, Windows 2×, macOS 10×, public/self-hosted free). ` +
    `Data refreshes automatically only when older than 5 minutes. ` +
    `The limits assume the Free plan; set STATUS_GITHUB_MINUTES_LIMIT, STATUS_GITHUB_ARTIFACT_LIMIT_MB, and STATUS_GITHUB_BILLING_DAY if yours differs.`;
}

function setRange(next) {
  range = next;
  try { localStorage.setItem("github_limits_range", range); } catch (e) { /* private window */ }
  document.querySelectorAll("#rangeSwitch button").forEach(b => b.classList.toggle("active", b.dataset.range === range));
  if (last && last.minutes) { renderDays(last); renderUploads(last); renderRepos(last); renderStorage(last); }
}
document.querySelectorAll("#rangeSwitch button").forEach(b => b.addEventListener("click", () => setRange(b.dataset.range)));
setRange(range);

async function load() {
  let d = null;
  try {
    d = await (await fetch("/api/github-limits", {headers: {"Accept": "application/json"}})).json();
    render(d);
  } catch (err) {
    const notice = document.getElementById("notice");
    document.getElementById("loadingOverlay").hidden = true;
    document.getElementById("content").hidden = false;
    notice.hidden = false;
    notice.textContent = "Could not reach the cockpit: " + err;
  }
  if (d && d.refreshing) {
    setTimeout(load, 2000);
  }
}

load();
