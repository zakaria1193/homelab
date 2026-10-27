// AI usage: every plan meter now, how far it rose over the range and a line of
// it over time (usage.py keeps a reading every few minutes, since /usage only
// gives the current %), then what went through aicli per hour or day.

if (new URLSearchParams(window.location.search).get("embedded") === "1") {
  document.body.classList.add("embedded");
}

const RANGE_LABEL = { "24h": "24 h", "48h": "48 h", "7d": "7 days", "30d": "30 days" };
const SERIES = ["#155bd0", "#d97706", "#059669", "#db2777", "#7c3aed", "#0891b2", "#65a30d", "#dc2626"];
const BAR_NAME = { five_hour: "5 h", weekly: "week" };
let range = "24h";
try { range = localStorage.getItem("ai_usage_range") || "24h"; } catch (e) { /* private window */ }
if (!RANGE_LABEL[range]) range = "24h";

const fmtInt = (n) => Number(n || 0).toLocaleString();
function short(n) {
  for (const [size, unit] of [[1e9, "B"], [1e6, "M"], [1e3, "k"]]) {
    if (n >= size) { const v = n / size; return (v < 10 ? v.toFixed(1).replace(/\.0$/, "") : Math.round(v)) + unit; }
  }
  return String(n || 0);
}
function usd(n) {
  if (n == null) return "–";
  if (n > 0 && n < 0.01) return "<$0.01";
  return n < 100 ? "$" + n.toFixed(2) : "$" + Math.round(n);
}

// Claude prints its own wording ("Nov 1, 5:59pm (Europe/Paris)"); agy an ISO time.
function resetText(reset) {
  if (!reset) return "";
  if (!/^\d{4}-\d\d-\d\dT/.test(reset)) return reset;
  const t = new Date(reset);
  return isNaN(t) ? reset : t.toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// {"claude/weekly": {pct, reset}, "agy/Gemini Models/five_hour": {...}} from an `aicli usage --json` reading.
function currentMeters(now) {
  const out = {};
  const claude = (now || {}).claude || {};
  if (claude.state === "ok") {
    for (const [bar, b] of Object.entries(claude.bars || {})) out["claude/" + bar] = b;
  }
  const agy = (now || {}).agy || {};
  if (agy.state === "ok") {
    for (const [group, bars] of Object.entries(agy.groups || {})) {
      for (const [bar, b] of Object.entries(bars || {})) out[`agy/${group}/${bar}`] = b;
    }
  }
  return out;
}

function meterName(key) {
  const parts = key.split("/");
  const bar = BAR_NAME[parts[parts.length - 1]] || parts[parts.length - 1];
  if (parts[0] === "claude") return `Claude plan · ${bar}`;
  return `agy ${parts[1].replace(/ models?$/i, "")} · ${bar}`;
}

function spark(history, key, start, end) {
  const t0 = new Date(start).getTime() / 1000, t1 = end / 1000;
  const pts = history.filter((s) => s.meters[key] != null)
    .map((s) => [(100 * (s.at - t0)) / Math.max(1, t1 - t0), 24 - (22 * Math.min(s.meters[key], 100)) / 100]);
  if (pts.length < 2) return '<svg class="spark" viewBox="0 0 100 26" preserveAspectRatio="none" aria-hidden="true"></svg>';
  const line = pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  return `<svg class="spark" viewBox="0 0 100 26" preserveAspectRatio="none" aria-hidden="true"><polyline points="${line}"/></svg>`;
}

function renderPlan(plan, start, label) {
  const now = currentMeters(plan.now);
  const latest = plan.history.length ? plan.history[plan.history.length - 1].meters : {};
  const keys = [...new Set([...Object.keys(now), ...Object.keys(latest)])]
    .sort((a, b) => (a.startsWith("claude") ? 0 : 1) - (b.startsWith("claude") ? 0 : 1) || a.localeCompare(b));
  const el = document.getElementById("meters");
  if (!keys.length) {
    el.innerHTML = '<div class="muted">No plan reading yet: the cockpit asks aicli every few minutes.</div>';
  } else {
    el.innerHTML = keys.map((key) => {
      const b = now[key] || { pct: latest[key] };
      const pct = Math.max(0, Math.min(100, b.pct));
      const grew = plan.growth[key];
      const level = pct >= 95 ? " hot" : pct >= 75 ? " warn" : "";
      return `<div class="meter">
        <span class="name">${esc(meterName(key))}</span>
        <div class="bar${level}"><i style="width:${pct}%"></i></div>
        <span class="pct">${esc(b.pct)}%</span>
        <span class="rise${grew ? "" : " muted"}" title="Rises added up; a drop is a reset.">${grew == null ? "no history yet" : `+${grew} pts in ${esc(label)}`}</span>
        ${spark(plan.history, key, start, Date.now())}
        <span class="reset">${b.reset ? "resets " + esc(resetText(b.reset)) : now[key] ? "" : "last reading"}</span>
      </div>`;
    }).join("");
  }
  const bad = ["claude", "agy"].filter((t) => plan.now && plan.now[t] && plan.now[t].state !== "ok");
  document.getElementById("planMeta").textContent = bad.length
    ? bad.map((t) => `${t}: ${plan.now[t].detail || "unknown"}`).join(" · ")
    : `${plan.history.length} readings in ${label}`;
}

function renderAicli(a, pjmUsage, label) {
  const chart = document.getElementById("aicliChart");
  const meta = document.getElementById("aicliMeta");
  const note = document.getElementById("aicliNote");
  if (!a.ok) {
    chart.innerHTML = `<div class="muted">${esc(a.message || "aicli usage log not readable.")}</div>`;
    meta.textContent = "";
    document.getElementById("byClient").innerHTML = "";
    document.getElementById("byModel").innerHTML = "";
    return;
  }
  const t = a.totals;
  meta.textContent = `${fmtInt(t.requests)} requests in ${label}` + (t.cost != null ? ` · Claude ${usd(t.cost)} at API price` : "");
  const clients = a.by_client.slice().sort((x, y) => y.requests - x.requests).map((c) => c.client);
  const colour = Object.fromEntries(clients.map((c, i) => [c, SERIES[i % SERIES.length]]));
  if (!t.requests) {
    chart.innerHTML = '<div class="muted">Nothing went through aicli in this range.</div>';
  } else {
    const top = Math.max(1, ...a.buckets.map((b) => b.requests));
    const every = Math.ceil(a.buckets.length / 8);
    const name = (at) => (a.bucket === "hour" ? `${new Date(at).getHours()}h` : at.slice(5));
    chart.innerHTML = `<div class="chart">${a.buckets.map((b, i) => {
      const tip = `${a.bucket === "hour" ? new Date(b.at).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" }) : b.at}: ${b.requests} requests\n`
        + Object.entries(b.clients).map(([c, n]) => `${c} ${n}`).join("\n");
      const parts = clients.filter((c) => b.clients[c]).map((c) => `<i style="flex:${b.clients[c]};background:${colour[c]}"></i>`).join("");
      return `<div class="col" title="${esc(tip)}"><div class="stack" style="height:${(100 * b.requests) / top}%">${parts}</div>`
        + `<span style="${i % every ? "visibility:hidden" : ""}">${esc(name(b.at))}</span></div>`;
    }).join("")}</div>
    <div class="legend">${clients.map((c) => `<span><i class="swatch" style="background:${colour[c]}"></i>${esc(c)}</span>`).join("")}</div>`;
  }
  const head = (first) => `<tr><th>${first}</th><th>requests</th><th>API $</th><th class="opt">tokens</th><th class="opt">in</th><th class="opt">out</th><th class="opt">cache</th></tr>`;
  const row = (key, r) => `<tr><td><code>${esc(r[key])}</code></td>
    <td title="${r.unreported ? esc(r.unreported + " without token counts") : ""}">${fmtInt(r.requests)}${r.unreported ? "*" : ""}</td>
    <td><strong>${usd(r.cost)}</strong></td><td class="opt">${r.tokens ? short(r.tokens) : "–"}</td>
    ${r.tokens ? `<td class="opt">${short(r.input)}</td><td class="opt">${short(r.output)}</td><td class="opt">${short(r.cache_write + r.cache_read)}</td>`
      : '<td class="opt">–</td><td class="opt">–</td><td class="opt">–</td>'}</tr>`;
  document.getElementById("byClient").innerHTML = a.by_client.length ? head("Client") + a.by_client.map((r) => row("client", r)).join("") : "";
  document.getElementById("byModel").innerHTML = a.by_model.length ? head("Model") + a.by_model.map((r) => row("model", r)).join("") : "";
  note.innerHTML = (t.unreported ? "* Requests started with <code>aicli run</code> have no token counts: aicli hands over to the CLI and never sees them. " : "")
    + `pjm counts its own runs from their transcripts: <a href="${esc(pjmUsage)}" target="_blank" rel="noopener">pjm Usage</a>. `
    + "API $ is what the same Claude tokens would cost on the API at list price, a stand-in for how the plan meters weigh them; it is not a bill.";
}

async function load() {
  document.querySelectorAll("#rangeSwitch button").forEach((b) => b.classList.toggle("active", b.dataset.range === range));
  try {
    const res = await fetch("/api/ai-usage?range=" + range, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    const label = RANGE_LABEL[range];
    renderPlan(data.plan, data.aicli.start || new Date(Date.now() - 86400000).toISOString(), label);
    renderAicli(data.aicli, data.pjm_usage, label);
  } catch (err) {
    document.getElementById("meters").innerHTML = `<div class="muted">Could not load usage: ${esc(err.message)}</div>`;
  }
}

document.querySelectorAll("#rangeSwitch button").forEach((b) => b.addEventListener("click", () => {
  range = b.dataset.range;
  try { localStorage.setItem("ai_usage_range", range); } catch (e) { /* private window */ }
  load();
}));
load();
setInterval(load, 60000);
