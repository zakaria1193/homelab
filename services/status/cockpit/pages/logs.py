"""/logs: one service's journal, docker log or log file."""

from .theme import THEME

LOG_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ logs · __TITLE__</title>
<style>
  {THEME}
  .wrap { max-width: 1400px; margin: 0 auto; padding: 24px 20px 48px; }
  header { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; margin-bottom: 6px; }
  h1 { font-size: 20px; margin: 0; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .src { color: var(--muted); font-size: 12px; font-family: ui-monospace, SFMono-Regular,
    Menlo, Consolas, monospace; margin-bottom: 14px; overflow-wrap: anywhere; }
  .bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
  .bar a, .bar button { background: var(--panel); border: 1px solid var(--border);
    color: var(--text); border-radius: 6px; padding: 5px 11px; font-size: 13px;
    text-decoration: none; cursor: pointer; font-family: inherit; }
  .bar a.on { border-color: var(--muted); font-weight: 600; }
  .bar label { color: var(--muted); font-size: 13px; margin-left: 4px; }
  pre { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 14px 16px; margin: 0; max-height: 74vh; overflow: auto; font-size: 12.5px;
    line-height: 1.55; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <a class="back" href="/">&larr; all services</a>
    <h1>__NAME__</h1>
  </header>
  <div class="src">__SOURCE__</div>
  <div class="bar">
    <label>lines</label>
    __LINE_LINKS__
    <button id="reload" type="button">reload</button>
    <label><input type="checkbox" id="follow"> auto-refresh</label>
    <label><input type="checkbox" id="tailtoggle" checked> stick to bottom</label>
  </div>
  <pre id="log">__LOG__</pre>
</div>
<script>
const box = document.getElementById("log");
const stick = document.getElementById("tailtoggle");
function toBottom() { if (stick.checked) box.scrollTop = box.scrollHeight; }
toBottom();

async function reload() {
  const response = await fetch(location.pathname + location.search + "&raw=1",
                               { cache: "no-store" });
  box.textContent = await response.text();
  toBottom();
}
document.getElementById("reload").addEventListener("click", reload);

let timer = null;
document.getElementById("follow").addEventListener("change", (event) => {
  clearInterval(timer);
  if (event.target.checked) timer = setInterval(reload, 5000);
});
</script>
</body>
</html>
""".replace("{THEME}", THEME)
