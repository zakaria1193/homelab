"""/projects: every live web project, its status and its link - nothing else."""

PROJECTS_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Projects · __TITLE__</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --raise: #1c2430; --border: #30363d; --text: #e6edf3;
    --muted: #8b949e; --up: #3fb950; --down: #f85149; --warn: #d29922; --unknown: #6e7681;
    --accent: #58a6ff;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --panel: #fff; --raise: #eef2f6; --border: #d0d7de;
            --text: #1f2328; --muted: #636c76; --accent: #0969da; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5
    ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  .wrap { max-width: 720px; margin: 0 auto; padding: 24px 16px 64px; }
  header { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 10px 16px; }
  h1 { font-size: 22px; margin: 0; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .summary { color: var(--muted); font-size: 13px; margin: 8px 0 16px; }
  .summary b { color: var(--text); font-weight: 600; }
  ul { list-style: none; margin: 0; padding: 0; background: var(--panel);
    border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  li { display: flex; align-items: center; gap: 12px; padding: 11px 14px;
    border-bottom: 1px solid var(--border); }
  li:last-child { border-bottom: none; }
  .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; background: var(--unknown); }
  .dot.up { background: var(--up); } .dot.down { background: var(--down); }
  .dot.warn { background: var(--warn); }
  .name { font-weight: 600; min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .state { font-size: 12px; color: var(--muted); flex: none; width: 4.5em; }
  a.open { color: var(--accent); text-decoration: none; font-size: 13px; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; flex: 0 0 42%; text-align: right; }
  a.open:hover { text-decoration: underline; }
  .empty { color: var(--muted); padding: 16px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Projects</h1>
    <a class="back" href="/">&larr; Cockpit</a>
  </header>
  <p class="summary" id="summary">Loading…</p>
  <ul id="list"></ul>
</div>
<script>
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// Same rule as the cockpit: lead with the tunnel URL when we were reached by
// hostname, with the LAN URL when we were reached by IP.
const PUBLIC_VIEW = !/^[\\d.]+$|^\\[|^localhost$|\\.local$/i.test(location.hostname);

async function load() {
  try {
    const rows = await (await fetch("/api/projects", { cache: "no-store" })).json();
    const up = rows.filter(r => r.state === "up").length;
    document.getElementById("summary").innerHTML = rows.length
      ? `<b>${up}</b> of <b>${rows.length}</b> up`
      : "";
    document.getElementById("list").innerHTML = rows.length ? rows.map(r => {
      const href = (PUBLIC_VIEW && r.remote) || r.link;
      return `<li><span class="dot ${esc(r.state)}"></span>
        <span class="name">${esc(r.name)}</span>
        <span class="state">${esc(r.state)}</span>
        <a class="open" href="${esc(href)}" target="_blank" rel="noopener">${esc(href.replace(/^https?:\\/\\//, ""))}</a></li>`;
    }).join("") : `<li class="empty">No live projects.</li>`;
  } catch (e) {
    document.getElementById("summary").textContent = "Could not load status.";
  }
}
load();
setInterval(load, __REFRESH__ * 1000);
</script>
</body>
</html>
"""
