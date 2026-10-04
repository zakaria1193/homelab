"""The cockpit itself: the page served at /."""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --raise: #1c2430; --border: #30363d; --text: #e6edf3;
    --muted: #8b949e; --up: #3fb950; --down: #f85149; --warn: #d29922; --unknown: #6e7681;
    --accent: #58a6ff; --usage-bg: rgba(88, 166, 255, 0.08); --usage-border: rgba(88, 166, 255, 0.35);
  }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --panel: #fff; --raise: #eef2f6; --border: #d0d7de;
            --text: #1f2328; --muted: #636c76; --accent: #0969da;
            --usage-bg: rgba(9, 105, 218, 0.06); --usage-border: rgba(9, 105, 218, 0.28); }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5
    ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  a { color: inherit; }
  .wrap { max-width: 100%; margin: 0 auto; padding: 12px 20px 40px; }
  #pane-ideas iframe, #pane-cron iframe, #pane-projects iframe { width: 100%; height: 88vh; border: 1px solid var(--border); border-radius: 8px; background: var(--panel); }
  header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 18px; }
  h1 { font-size: 22px; margin: 0; letter-spacing: -0.01em; }
  .sub { color: var(--muted); font-size: 13px; }
  /* ---- cockpit navigation tabs ---- */
  .cockpit-tabs { display: flex; gap: 6px; border-bottom: 1px solid var(--border); margin: 18px 0 20px; overflow-x: auto; }
  .cockpit-tab-btn { display: inline-flex; align-items: center; gap: 8px; background: none; border: none; border-bottom: 2px solid transparent; padding: 10px 16px; font-size: 14px; font-weight: 500; color: var(--muted); cursor: pointer; font-family: inherit; transition: all 0.15s ease; white-space: nowrap; margin-bottom: -1px; }
  .cockpit-tab-btn:hover { color: var(--text); }
  .cockpit-tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }

  /* ---- plan-usage health bars ---- */
  .usage-bars { display: flex; flex-direction: column; gap: 8px; margin: 18px 0 0;
    background: var(--usage-bg); border: 1px solid var(--usage-border); border-radius: 10px;
    padding: 12px 16px; }
  .usage-bars:empty { display: none; }
  .usage-caption { color: var(--muted); font-size: 11px; text-transform: uppercase;
    letter-spacing: 0.05em; font-weight: 600; margin-bottom: 2px; }
  .usage-card { display: flex; align-items: center; gap: 16px;
    max-width: 100%; background: var(--panel);
    border: 1px solid var(--border); border-radius: 8px; padding: 8px 14px; font-size: 12px; }
  .usage-card.offline { color: var(--muted); }
  .usage-card .uname { font-weight: 600; color: var(--text); min-width: 90px; display: inline-flex; align-items: center; gap: 6px; }
  .meter { display: flex; align-items: center; gap: 8px; min-width: 260px; }
  .meter .mlabel { color: var(--muted); font-weight: 600; min-width: 18px; }
  .meter .mval { font-variant-numeric: tabular-nums; min-width: 5em; white-space: nowrap; }
  .meter .mval.muted { color: var(--muted); }
  .meter .mval .reset { color: var(--muted); font-weight: 400; font-size: 11px; }
  .bar-track { width: 80px; height: 7px; border-radius: 4px; background: var(--raise);
    overflow: hidden; flex-shrink: 0; }
  .bar-fill { display: block; height: 100%; border-radius: 4px; background: var(--up); transition: width 0.3s ease; }
  .bar-fill.warn { background: #f0883e !important; }
  .bar-fill.down { background: var(--down); }
  @media (max-width: 640px) {
    .usage-bars { padding: 10px 12px; }
    .usage-card { flex-wrap: wrap; gap: 8px; }
    .meter { min-width: 100%; }
  }

  /* ---- unified session chip ---- */
  .session-chip { display: inline-flex; align-items: center; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; font-size: 13px; }
  .session-chip:hover { border-color: var(--muted); }
  .session-chip .session-main { display: inline-flex; align-items: center; gap: 7px; padding: 7px 12px; font-weight: 600; color: var(--text); background: var(--raise); border-right: 1px solid var(--border); cursor: default; }
  .session-chip .sub-btn { display: inline-flex; align-items: center; gap: 5px; padding: 7px 11px; color: var(--muted); text-decoration: none; font-size: 12px; font-weight: 500; border-right: 1px solid var(--border); transition: all 0.15s ease; }
  .session-chip .sub-btn:hover { color: var(--text); background: var(--panel); }
  .session-chip .sub-btn.active { color: var(--text); background: rgba(56, 139, 253, 0.12); font-weight: 600; }
  .session-chip .sub-btn.active .dot { margin-right: 2px; }

  /* ---- add repo form & subtle buttons ---- */
  .add-repo-form { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; margin-bottom: 14px; }
  .add-repo-form .form-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .add-repo-form input[type="text"] { background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text); padding: 6px 12px; font-size: 13px; font-family: inherit; outline: none; flex: 1 1 180px; }
  .add-repo-form input[type="text"]:focus { border-color: var(--accent); }
  .btn-subtle { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; color: var(--muted); padding: 5px 12px; font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all 0.15s ease; }
  .btn-subtle:hover { color: var(--text); border-color: var(--muted); background: var(--raise); }
  .btn-primary { background: var(--accent); color: #fff; border: none; border-radius: 6px; padding: 6px 14px; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit; }
  .btn-primary:hover { opacity: 0.9; }

  /* ---- remote control table ---- */
  .rc-table-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; margin-top: 12px; }
  .rc-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
  .rc-table th { background: var(--raise); color: var(--muted); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; padding: 10px 14px; border-bottom: 1px solid var(--border); white-space: nowrap; }
  .rc-table td { padding: 11px 14px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  .rc-table tr:last-child td { border-bottom: none; }
  .rc-table tbody tr:hover td { background: color-mix(in srgb, var(--raise) 50%, transparent); }
  .rc-session-name { font-weight: 600; color: var(--text); }
  .rc-unit-sub { font-size: 11px; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; display: block; margin-top: 2px; }
  .rc-scope-badge { display: inline-block; font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; padding: 1px 5px; border-radius: 4px; background: var(--raise); color: var(--muted); border: 1px solid var(--border); margin-left: 6px; vertical-align: middle; }
  .rc-status-cell { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; font-size: 12px; }
  .rc-cell { display: inline-flex; flex-wrap: wrap; gap: 6px; }
  .rc-pill { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
  .rc-config-text { font-size: 12px; color: var(--muted); white-space: nowrap; }
  .rc-table .acts { margin-top: 0; }

  /* ---- other services dedicated filter bar ---- */
  .services-filter-bar {
    background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px 14px; margin: 16px 0 12px; display: flex; flex-direction: column; gap: 10px;
  }
  .filter-bar-top {
    display: flex; justify-content: space-between; align-items: center;
    flex-wrap: wrap; gap: 10px;
  }
  .filter-bar-left {
    display: flex; align-items: center; flex-wrap: wrap; gap: 8px; flex: 1 1 auto;
  }
  .filter-bar-right {
    display: flex; align-items: center; gap: 10px; flex-shrink: 0;
  }
  .search-input-wrapper {
    position: relative; display: inline-flex; align-items: center; min-width: 200px; flex: 1 1 220px; max-width: 360px;
  }
  .search-input-wrapper .search-ico {
    position: absolute; left: 10px; width: 14px; height: 14px; color: var(--muted); pointer-events: none;
  }
  .filter-search-input {
    width: 100%; background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
    color: var(--text); padding: 6px 28px 6px 32px; font-size: 13px; font-family: inherit;
    outline: none; transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }
  .filter-search-input:focus {
    border-color: var(--accent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 25%, transparent);
  }
  .clear-search-btn {
    position: absolute; right: 6px; background: none; border: none; color: var(--muted);
    font-size: 13px; cursor: pointer; padding: 2px 6px; border-radius: 4px; line-height: 1;
  }
  .clear-search-btn:hover { color: var(--text); background: var(--raise); }
  .filter-select {
    background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
    color: var(--text); padding: 6px 10px; font-size: 12px; font-family: inherit;
    outline: none; cursor: pointer;
  }
  .filter-select:focus { border-color: var(--accent); }
  .filter-count-badge {
    font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; font-weight: 500;
  }
  .reset-filters-btn {
    font-size: 12px; padding: 4px 10px; color: var(--accent); border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
  }
  .reset-filters-btn:hover {
    background: color-mix(in srgb, var(--accent) 15%, transparent); color: #fff;
  }
  .filter-bar-groups {
    display: flex; flex-wrap: wrap; gap: 6px; align-items: center; border-top: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
    padding-top: 8px;
  }
  .group-filter-pill {
    background: var(--bg); border: 1px solid var(--border); border-radius: 999px;
    padding: 3px 10px; font-size: 12px; color: var(--muted); cursor: pointer;
    font-family: inherit; transition: all 0.15s ease; display: inline-flex; align-items: center; gap: 5px;
  }
  .group-filter-pill:hover {
    color: var(--text); border-color: var(--muted); background: var(--raise);
  }
  .group-filter-pill.active {
    background: color-mix(in srgb, var(--accent) 18%, var(--panel));
    border-color: var(--accent); color: var(--text); font-weight: 600;
  }
  .group-filter-pill .pill-count {
    font-size: 11px; opacity: 0.7; font-variant-numeric: tabular-nums;
  }
  .services-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
  .services-table th {
    background: var(--raise); color: var(--muted); font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.06em; padding: 10px 12px;
    border-bottom: 1px solid var(--border); white-space: nowrap;
  }
  .services-table td { padding: 9px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  .services-table tr:last-child td { border-bottom: none; }
  .services-table tbody tr:hover td { background: color-mix(in srgb, var(--raise) 50%, transparent); }
  .sort-header {
    background: none; border: none; font: inherit; color: inherit; text-transform: inherit;
    letter-spacing: inherit; cursor: pointer; padding: 0; display: inline-flex; align-items: center; gap: 4px;
  }
  .sort-header:hover { color: var(--text); }
  .service-cell { min-width: 150px; }
  .service-head { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; color: var(--text); }
  .service-table-link { color: var(--text); text-decoration: none; border-bottom: 1px solid var(--border); }
  .service-table-link:hover { border-bottom-color: var(--accent); color: var(--accent); }
  .service-table-name { color: var(--text); font-weight: 600; }
  .btn-group { display: inline-flex; flex-wrap: wrap; gap: 4px; align-items: center; }
  .btn-table-action {
    display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 500;
    text-decoration: none; border: 1px solid var(--border); border-radius: 5px;
    padding: 3px 8px; color: var(--text); background: var(--panel); white-space: nowrap;
    transition: all 0.15s ease; cursor: pointer; font-family: inherit; line-height: 1.2;
  }
  .btn-table-action:hover {
    background: var(--raise); border-color: var(--muted); color: var(--accent);
  }
  .btn-table-action.primary-link {
    color: var(--accent); border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  }
  .btn-table-action.primary-link:hover {
    background: color-mix(in srgb, var(--accent) 15%, transparent); border-color: var(--accent);
  }
  .muted-dash { color: var(--muted); opacity: 0.4; font-size: 13px; user-select: none; }
  .btn-toggle { background: none; font: inherit; cursor: pointer; font-size: 11px;
    border: 1px solid var(--border); border-radius: 5px; padding: 2px 7px;
    display: inline-flex; align-items: center; gap: 4px; transition: all 0.15s ease; white-space: nowrap; }
  .btn-toggle.on { color: var(--up); border-color: color-mix(in srgb, var(--up) 35%, var(--border)); }
  .btn-toggle.on:hover { background: color-mix(in srgb, var(--up) 12%, transparent); border-color: var(--up); }
  .btn-toggle.off { color: var(--muted); border-color: var(--border); }
  .btn-toggle.off:hover { color: var(--text); background: var(--raise); border-color: var(--muted); }

  .totals { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 14px 0 6px; }
  .pill { display: inline-flex; align-items: center; gap: 7px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px; font-size: 12px;
    color: inherit; text-decoration: none; font-family: inherit; }
  button.pill { cursor: pointer; }
  button.pill:hover, a.pill:hover { border-color: var(--muted); background: var(--raise); }
  button.pill.active { border-color: var(--fg, #e6edf3); background: var(--raise, #21262d); box-shadow: 0 0 0 1px var(--fg, #e6edf3); }
  .pill b { font-variant-numeric: tabular-nums; }
  .dot { width: 9px; height: 9px; border-radius: 50%; flex: none; background: var(--unknown); }
  .up .dot, .dot.up { background: var(--up); }
  .down .dot, .dot.down { background: var(--down); }
  .warn .dot, .dot.warn { background: var(--warn); }
  .unknown .dot, .dot.unknown { background: var(--unknown); }

  /* ---- group ---- */
  section.group { margin: 26px 0 0; }
  .ghead { display: flex; align-items: baseline; gap: 12px; margin-bottom: 10px; }
  .ghead h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--muted); margin: 0; font-weight: 600; }
  .gsum { display: flex; gap: 10px; font-size: 12px; color: var(--muted);
    font-variant-numeric: tabular-nums; }
  .gsum span { display: inline-flex; align-items: center; gap: 5px; }

  /* ---- always-visible operation row ---- */
  .quick { display: flex; flex-wrap: wrap; gap: 8px; }
  .quick:empty { display: none; }
  .chip { display: inline-flex; align-items: center; background: var(--panel);
    border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  .chip > a { display: inline-flex; align-items: center; gap: 7px; padding: 7px 12px;
    text-decoration: none; font-size: 14px; }
  .chip > a:hover { background: var(--raise); }
  .chip .alt { display: inline-flex; align-items: center; border-left: 1px solid var(--border);
    padding: 7px 11px; font-size: 12px; color: var(--muted); text-decoration: none; font-weight: 500; }
  .chip .alt:hover { color: var(--text); background: var(--raise); }
  .chip.term { border-color: var(--accent); }
  .chip.term > a { color: var(--accent); font-weight: 500; }
  .ico { width: 15px; height: 15px; flex: none; }
  .ico.claude { width: 14px; height: 14px; }
  /* Which box it runs on, riding along after the name. */
  .node { display: inline-flex; align-items: center; opacity: 0.75; }
  .node .ico { width: 12px; height: 12px; }
  .chip.term code { font: 12px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: var(--muted); }
  .chip.offline > a { color: var(--muted); }
  /* An endpoint-only chip: same shape as a link chip, but deliberately inert -
     there is no page behind it, so nothing here invites a click. */
  .chip > .plain { display: inline-flex; align-items: center; gap: 7px;
    padding: 7px 12px; font-size: 14px; color: var(--text); cursor: default; }
  .chip.offline > .plain { color: var(--muted); }
  .chip .alt.copy { background: none; border-top: 0; border-right: 0; border-bottom: 0;
    font: inherit; cursor: pointer; }
  .chip .alt.copied, .acts .copied { color: var(--ok); }
  .acts .copy { background: none; font: inherit; cursor: pointer; font-size: 12px;
    color: var(--muted); border: 1px solid var(--border); border-radius: 5px; padding: 1px 8px; }
  .acts .copy:hover { color: var(--text); border-color: var(--muted); }
  .meta code { font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: var(--muted); }

  /* ---- folded detail ---- */
  details.more { margin-top: 10px; }
  details.more > summary { cursor: pointer; color: var(--muted); font-size: 12px;
    list-style: none; display: inline-flex; align-items: center; gap: 6px;
    padding: 3px 9px; border: 1px solid var(--border); border-radius: 6px; }
  details.more > summary::-webkit-details-marker { display: none; }
  details.more > summary:hover { color: var(--text); border-color: var(--muted); }
  details.more > summary::before { content: "\\25B8"; font-size: 10px; }
  details.more[open] > summary::before { content: "\\25BE"; }
  .grid { display: grid; gap: 10px; margin-top: 10px;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }
  .card { display: flex; align-items: flex-start; gap: 12px; background: var(--panel);
    border: 1px solid var(--border); border-left-width: 3px; border-radius: 8px; padding: 12px 14px; }
  .card.up { border-left-color: var(--up); }
  .card.down { border-left-color: var(--down); }
  .card.warn { border-left-color: var(--warn); }
  .card.unknown { border-left-color: var(--unknown); }
  .card .dot { margin-top: 6px; }
  .body { min-width: 0; flex: 1; }
  .name { font-weight: 600; overflow-wrap: anywhere; display: flex; align-items: center; gap: 7px; }
  .name a { text-decoration: none; border-bottom: 1px solid var(--border); }
  .name a:hover { border-bottom-color: currentColor; }
  .detail { font-size: 13px; margin-top: 2px; overflow-wrap: anywhere; }
  .down .detail { color: var(--down); }
  .warn .detail { color: var(--warn); }
  .meta { color: var(--muted); font-size: 12px; margin-top: 3px; font-variant-numeric: tabular-nums; }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .acts a { font-size: 12px; color: var(--muted); text-decoration: none;
    border: 1px solid var(--border); border-radius: 5px; padding: 1px 8px; }
  .acts a:hover { color: var(--text); border-color: var(--muted); }
  .acts .btn-toggle { background: none; font: inherit; cursor: pointer; font-size: 11px;
    border: 1px solid var(--border); border-radius: 5px; padding: 1px 7px;
    display: inline-flex; align-items: center; gap: 4px; transition: all 0.15s ease; }
  .acts .btn-toggle.on { color: var(--up); border-color: color-mix(in srgb, var(--up) 35%, var(--border)); }
  .acts .btn-toggle.on:hover { background: color-mix(in srgb, var(--up) 12%, transparent); border-color: var(--up); }
  .acts .btn-toggle.off { color: var(--muted); border-color: var(--border); }
  .acts .btn-toggle.off:hover { color: var(--text); background: var(--raise); border-color: var(--muted); }
  .acts .btn-toggle:disabled { opacity: 0.5; cursor: wait; }
  footer { margin-top: 44px; color: var(--muted); font-size: 12px; }
  .stale { opacity: 0.45; transition: opacity 0.2s; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>__TITLE__</h1>
    <span class="sub" id="updated">loading…</span>
  </header>
  <nav class="cockpit-tabs" role="tablist">
    <button type="button" class="cockpit-tab-btn active" data-tab="ideas">
      <span>💡</span> Ideas
    </button>
    <button type="button" class="cockpit-tab-btn" data-tab="ai-sessions">
      <svg class="ico" viewBox="0 0 16 16"><path d="M5 2h6v2H5zm-2 4h10v2H3zm-1 4h12v2H2z" fill="currentColor"/></svg>
      AI Sessions
    </button>
    <button type="button" class="cockpit-tab-btn" data-tab="other-services">
      <svg class="ico" viewBox="0 0 16 16"><path d="M1 2.5A1.5 1.5 0 0 1 2.5 1h11A1.5 1.5 0 0 1 15 2.5v2A1.5 1.5 0 0 1 13.5 6h-11A1.5 1.5 0 0 1 1 4.5v-2zm0 7A1.5 1.5 0 0 1 2.5 8h11a1.5 1.5 0 0 1 1.5 1.5v2a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 11.5v-2z" fill="currentColor"/></svg>
      Other Services
    </button>
    <button type="button" class="cockpit-tab-btn" data-tab="projects">
      <span>🚀</span> Projects
    </button>
    <button type="button" class="cockpit-tab-btn" data-tab="tmux-sessions">
      <svg class="ico" viewBox="0 0 16 16"><rect x="1" y="2.5" width="14" height="11" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M4 6l2.5 2L4 10 M8.5 10.5h3.5" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>
      Tmux Sessions
    </button>
    <button type="button" class="cockpit-tab-btn" data-tab="cron">
      <span>⏰</span> Cron Jobs
    </button>
  </nav>

  <!-- TAB 1: AI Sessions -->
  <div class="cockpit-tab-pane" id="pane-ai-sessions">
    <section class="group" id="aiSessionsGroup">
      <div class="ghead" style="justify-content: space-between; align-items: center;">
        <h2>AI Sessions</h2>
        <div style="display:flex; gap:8px;">
          <a href="/claude-rc" class="btn-subtle" style="text-decoration:none;">Claude RC servers &rarr;</a>
          <a href="/antigravity-rc" class="btn-subtle" style="text-decoration:none;">Antigravity RC &rarr;</a>
          <button type="button" class="btn-subtle" id="btnToggleAddRepo">+ Add repo</button>
        </div>
      </div>
      <form id="formAddRepo" class="add-repo-form" style="display: none;">
        <div class="form-row">
          <input type="text" id="addRepoPath" placeholder="Directory / repo path (e.g. /home/zfadli/my_repos/...)" required>
          <input type="text" id="addRepoName" placeholder="Session name (auto-deduced from repo)" pattern="[a-zA-Z0-9_-]*">
          <input type="text" id="addRepoNote" placeholder="Optional note / description">
          <button type="submit" class="btn-primary">Add Session</button>
          <button type="button" class="btn-subtle" id="btnCancelAddRepo">Cancel</button>
        </div>
        <div id="addRepoMsg" style="font-size: 12px; margin-top: 6px; color: var(--accent);"></div>
      </form>
      <div class="rc-table-wrap">
        <table class="services-table">
          <thead><tr>
            <th>Session</th><th>Workspace</th><th>Note</th>
            <th>Remote Control</th>
            <th style="text-align:center;">Claude</th><th style="text-align:center;">Antigravity</th>
            <th style="text-align:center;">Shell</th><th></th>
          </tr></thead>
          <tbody id="aiSessionsQuick"></tbody>
        </table>
      </div>
      <div id="activeSessionsSection" style="margin-top: 16px; display: none;">
        <div class="ghead" style="justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <h2 style="font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin: 0; font-weight: 600;">Other Active Live Sessions</h2>
          <span id="activeSessionsCount" style="font-size: 12px; color: var(--muted);"></span>
        </div>
        <div class="rc-table-wrap">
          <table class="services-table">
            <thead><tr>
              <th>Session</th><th>Status</th><th style="text-align:center;"></th>
            </tr></thead>
            <tbody id="activeSessionsQuick"></tbody>
          </table>
        </div>
      </div>
      <div class="usage-bars" id="usageBars"></div>
      <div class="quick" style="margin-top: 14px;">
        <span class="chip term"><a href="/terminal?session=new" title="start direct terminal session in ~"><svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><rect x="0.75" y="2.25" width="14.5" height="11.5" rx="2" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M4 6.2 L6.4 8 L4 9.8 M8.4 10.4 H11.6" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>+ New terminal session</a></span>
        <span class="chip term"><a href="/tmux" title="manage all tmux sessions"><svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><rect x="0.75" y="2.25" width="14.5" height="11.5" rx="2" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M4 6.2 L6.4 8 L4 9.8 M8.4 10.4 H11.6" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>Tmux sessions</a></span>
      </div>
    </section>
  </div>

  <!-- TAB 3: Other Services -->
  <div class="cockpit-tab-pane" id="pane-other-services" style="display: none;">
    <div class="services-filter-bar">
      <div class="filter-bar-top">
        <div class="filter-bar-left">
          <div class="search-input-wrapper">
            <svg class="search-ico" viewBox="0 0 16 16" aria-hidden="true" fill="currentColor">
              <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>
            </svg>
            <input type="text" id="servicesSearchInput" class="filter-search-input" placeholder="Filter by name, port, note, URL…" autocomplete="off">
            <button type="button" id="clearSearchBtn" class="clear-search-btn" title="Clear search" style="display:none;">✕</button>
          </div>
          <div class="totals" id="totals"></div>
          <select id="servicesTypeFilter" class="filter-select" title="Filter by service type">
            <option value="">All Types</option>
            <option value="systemd">systemd</option>
            <option value="docker">docker</option>
            <option value="http">http</option>
            <option value="logfile">logfile</option>
            <option value="port">port</option>
          </select>
        </div>
        <div class="filter-bar-right">
          <button type="button" id="resetAllFiltersBtn" class="btn-subtle reset-filters-btn" style="display:none;" title="Reset all filters">✕ Reset filters</button>
          <span id="servicesCountBadge" class="filter-count-badge"></span>
        </div>
      </div>
      <div class="filter-bar-groups" id="servicesGroupPills"></div>
    </div>
    <main id="groups">
      <div class="rc-table-wrap">
        <table class="rc-table services-table">
          <thead>
            <tr>
              <th><button type="button" class="sort-header" data-sort="name">Service <span id="sort-arrow-name">↕</span></button></th>
              <th><button type="button" class="sort-header" data-sort="group">Group <span id="sort-arrow-group">↕</span></button></th>
              <th><button type="button" class="sort-header" data-sort="state">Status <span id="sort-arrow-state">↕</span></button></th>
              <th style="text-align: center;">Open</th>
              <th style="text-align: center;">Shell</th>
              <th style="text-align: center;">agy</th>
              <th style="text-align: center;">claude</th>
              <th style="text-align: center;">Logs</th>
              <th style="text-align: center;">Toggle</th>
            </tr>
          </thead>
          <tbody id="servicesTableBody">
            <tr><td colspan="9" style="text-align: center; color: var(--muted); padding: 24px;">Loading services…</td></tr>
          </tbody>
        </table>
      </div>
    </main>
  </div>

  <!-- TAB 4: Tmux Sessions -->
  <div class="cockpit-tab-pane" id="pane-tmux-sessions" style="display: none;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:10px;">
      <div>
        <h2 style="font-size:13px; text-transform:uppercase; letter-spacing:0.08em; color:var(--muted); margin:0; font-weight:600;">Active Tmux Sessions</h2>
        <span style="font-size:12px; color:var(--muted);">Persistent background terminals running in cockpit</span>
      </div>
      <div style="display:flex; gap:8px;">
        <button type="button" class="btn-subtle" id="btnToggleNewTmux">+ New session</button>
        <a href="/tmux" class="btn-subtle" style="text-decoration:none;">Advanced Tmux Manager &rarr;</a>
      </div>
    </div>
    <form id="formNewTmux" class="add-repo-form" style="display: none;">
      <div class="form-row">
        <input type="text" id="newTmuxName" placeholder="Session name (e.g. dev-worker)" required pattern="[a-zA-Z0-9_-]+">
        <button type="submit" class="btn-primary">Create &amp; Open</button>
        <button type="button" class="btn-subtle" id="btnCancelNewTmux">Cancel</button>
      </div>
      <div id="newTmuxMsg" style="font-size: 12px; margin-top: 6px; color: var(--accent);"></div>
    </form>
    <div id="tmuxSessionsContainer">
      <div style="color: var(--muted); font-size: 13px; padding: 20px 0;">Loading tmux sessions…</div>
    </div>
  </div>

  <!-- TAB 5: Ideas -->
  <div class="cockpit-tab-pane" id="pane-ideas" style="display: none;">
    <iframe id="ideasIframe" data-src="/idea?embedded=1"></iframe>
  </div>

  <!-- Projects: status + link per live project, editable -->
  <div class="cockpit-tab-pane" id="pane-projects" style="display: none;">
    <iframe id="projectsIframe" data-src="/projects?embedded=1"></iframe>
  </div>

  <!-- TAB 6: Cron Jobs -->
  <div class="cockpit-tab-pane" id="pane-cron" style="display: none;">
    <iframe id="cronIframe" data-src="/cron?embedded=1"></iframe>
  </div>
  <footer>Auto-refreshing every __REFRESH__s ·
    <a href="/api/status">JSON API</a> ·
    <a href="/projects">Projects</a> ·
    <a href="/claude-rc">Claude RC servers</a> ·
    <a href="/antigravity-rc">Antigravity RC server</a> ·
    <a href="/tmux">tmux sessions</a> ·
    <a href="/cron">Cron jobs</a> ·
    <a href="/idea">ideas</a> ·
    <a href="#" id="expand">expand all</a>__LOGOUT__</footer>
</div>
<script>
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const qs = encodeURIComponent;

// Which address family this browser reached us on decides which link we lead
// with: opened over a public hostname you want the tunnel URLs, opened over the
// LAN IP you want the LAN ones. The other is always one click away as "alt".
const PUBLIC_VIEW = !/^[\\d.]+$|^\\[|^localhost$|\\.local$/i.test(location.hostname);

function links(s) {
  if (s.alt_link) {
    const primary = (PUBLIC_VIEW && s.remote) || s.link || s.remote || "";
    return { primary, alt: s.alt_link, altLabel: s.alt_label || "servers" };
  }
  const lan = s.link, pub = s.remote;
  const primary = (PUBLIC_VIEW && pub) || lan || pub || "";
  const alt = primary === pub ? lan : pub;
  return { primary, alt, altLabel: primary === pub ? "LAN" : "WAN" };
}

// Folded by default: this page is for operating the homelab, not staring at it.
const isOpen = (g) => localStorage.getItem("fold:" + g) === "open";

// Inline so the page keeps working with no outbound access (xterm.js on the
// terminal page is the one exception in this service).
const ICONS = {
  // A shell: what you get is a prompt, so draw a prompt.
  terminal: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="0.75" y="2.25" width="14.5" height="11.5" rx="2"
      fill="none" stroke="currentColor" stroke-width="1.3"/>
    <path d="M4 6.2 L6.4 8 L4 9.8 M8.4 10.4 H11.6" fill="none" stroke="currentColor"
      stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  // The Claude mark: a burst of tapered rays.
  claude: `<svg class="ico claude" viewBox="0 0 16 16" aria-hidden="true">${
    Array.from({ length: 11 }, (_, i) => {
      const a = (i * 360) / 11;
      return `<rect x="7.35" y="0.9" width="1.3" height="7.1" rx="0.65"
        fill="#D97757" transform="rotate(${a} 8 8)"/>`;
    }).join("")}</svg>`,
  // Antigravity: a body breaking upward out of its orbit. Sits next to the
  // Claude mark on the session chips, so it has to read differently at 15px -
  // hence a ring plus an arrow rather than another radial burst.
  antigravity: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <ellipse cx="8" cy="11" rx="5.6" ry="2.4" fill="none" stroke="#4285F4"
      stroke-width="1.3" opacity=".55"/>
    <path d="M8 12.4 V3.2 M5.1 6 L8 3 L10.9 6" fill="none" stroke="#4285F4"
      stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  // Two sheets: the copy affordance on an address you paste elsewhere.
  copy: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="5.4" y="5.4" width="8.1" height="8.1" rx="1.6" fill="none"
      stroke="currentColor" stroke-width="1.3"/>
    <path d="M10.6 5.4V4a1.6 1.6 0 0 0-1.6-1.6H4a1.6 1.6 0 0 0-1.6 1.6v5a1.6 1.6 0 0 0 1.6 1.6h1.4"
      fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  // The Raspberry Pi berry: also used as the "runs on the Pi" badge.
  raspberry: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><g fill="#C51A4A">
    <path d="M7.6 5.1C6.7 3.6 5.1 2.9 3.6 3.2c0 1.6 1.1 3 2.6 3.4z"/>
    <path d="M8.4 5.1C9.3 3.6 10.9 2.9 12.4 3.2c0 1.6-1.1 3-2.6 3.4z"/>
    <circle cx="8" cy="7.1" r="1.7"/><circle cx="5.9" cy="8.6" r="1.7"/>
    <circle cx="10.1" cy="8.6" r="1.7"/><circle cx="6.9" cy="11" r="1.7"/>
    <circle cx="9.1" cy="11" r="1.7"/></g></svg>`,
  // Home Assistant: the blue house.
  "home-assistant": `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M8 1.3 15 7.9v6.1c0 .4-.3.7-.7.7H1.7c-.4 0-.7-.3-.7-.7V7.9z" fill="#18BCF2"/>
    <path d="M8 6.4v6.6M5.3 9.1v3.9M10.7 9.1v3.9" stroke="#fff" stroke-width="1.15"
      stroke-linecap="round"/></svg>`,
  // Jellyfin: the two-tone gradient jelly.
  jellyfin: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <defs><linearGradient id="jf" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#AA5CC3"/><stop offset="1" stop-color="#00A4DC"/>
    </linearGradient></defs>
    <path d="M8 1.4c1.5 0 5.9 7.3 5.2 8.7-.8 1.4-9.6 1.4-10.4 0C2.1 8.7 6.5 1.4 8 1.4z"
      fill="url(#jf)" opacity=".45"/>
    <path d="M8 6.3c.8 0 3.4 4.3 3 5-.4.8-5.6.8-6 0-.4-.7 2.2-5 3-5z" fill="url(#jf)"/></svg>`,
  // Docker: containers stacked on the hull of the whale.
  docker: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><g fill="#2496ED">
    <rect x="3" y="6.5" width="2.2" height="2.2" rx=".3"/>
    <rect x="5.6" y="6.5" width="2.2" height="2.2" rx=".3"/>
    <rect x="8.2" y="6.5" width="2.2" height="2.2" rx=".3"/>
    <rect x="5.6" y="3.9" width="2.2" height="2.2" rx=".3"/>
    <path d="M1 9.4h13.1c0 2.5-2 4.2-5 4.2-3.5 0-6.8-1.2-8.1-4.2z"/></g></svg>`,
  // The *arr suite: same silhouette family, told apart by what they hunt.
  sonarr: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="1.2" y="3.6" width="13.6" height="9" rx="1.6" fill="none" stroke="#35C5F4"
      stroke-width="1.4"/><path d="M5.4 14.4h5.2M6.6 1.6 8 3.4l1.4-1.8" fill="none"
      stroke="#35C5F4" stroke-width="1.4" stroke-linecap="round"/></svg>`,
  radarr: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="1.2" y="5.4" width="13.6" height="8.4" rx="1.4" fill="none" stroke="#FFC230"
      stroke-width="1.4"/><path d="M1.6 3.1 13.4 1.6l.3 2.2L1.9 5.3z" fill="#FFC230"/>
    <path d="M5.4 2.6 6.5 4.6M9 2.2l1.1 2" stroke="#0d1117" stroke-width="1"/></svg>`,
  readarr: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M1.6 2.4h4.2c1.2 0 2.2.7 2.2 1.6v9.6c0-.9-1-1.6-2.2-1.6H1.6z" fill="#C4392E"/>
    <path d="M14.4 2.4h-4.2c-1.2 0-2.2.7-2.2 1.6v9.6c0-.9 1-1.6 2.2-1.6h4.2z" fill="#E8654F"/>
    </svg>`,
  prowlarr: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="6.9" cy="6.9" r="4.7" fill="none" stroke="#E66000" stroke-width="1.5"/>
    <path d="M10.4 10.4 14.2 14.2" stroke="#E66000" stroke-width="1.8" stroke-linecap="round"/>
    </svg>`,
  // Transmission: a torrent client is a download, so draw the download.
  transmission: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="8" cy="8" r="6.7" fill="none" stroke="#D33A2C" stroke-width="1.4"/>
    <path d="M8 4.2v6M5.4 7.6 8 10.3l2.6-2.7" fill="none" stroke="#D33A2C"
      stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  // Karakeep: things you kept, so a bookmark.
  karakeep: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M3.6 1.9h8.8c.5 0 .9.4.9.9v11.3L8 11.2l-5.3 2.9V2.8c0-.5.4-.9.9-.9z"
      fill="#16A394"/></svg>`,
  // Meilisearch: the search box behind Karakeep.
  meilisearch: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <defs><linearGradient id="ms" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#FF5CAA"/><stop offset="1" stop-color="#7700FF"/>
    </linearGradient></defs>
    <circle cx="6.9" cy="6.9" r="4.7" fill="none" stroke="url(#ms)" stroke-width="1.5"/>
    <path d="M10.4 10.4 14.2 14.2" stroke="url(#ms)" stroke-width="1.8" stroke-linecap="round"/>
    </svg>`,
  // Headless Chrome: the four-colour wheel.
  chrome: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="8" cy="8" r="6.8" fill="#4285F4"/>
    <path d="M8 1.2a6.8 6.8 0 0 1 5.9 3.4H8a3.4 3.4 0 0 0-3 1.8L2.2 4.1A6.8 6.8 0 0 1 8 1.2z"
      fill="#EA4335"/>
    <path d="M2.2 4.1 5 6.4a3.4 3.4 0 0 0 .1 3.3l-2.9 5A6.8 6.8 0 0 1 2.2 4.1z" fill="#FBBC05"/>
    <path d="M13.9 4.6A6.8 6.8 0 0 1 8 14.8h-.4l2.9-5A3.4 3.4 0 0 0 8 4.6z" fill="#34A853"/>
    <circle cx="8" cy="8" r="2.9" fill="#fff"/><circle cx="8" cy="8" r="2.2" fill="#4285F4"/>
    </svg>`,
  // Hermes: the messenger, so the thing a message flies as.
  hermes: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M14.6 1.6 1.4 6.9l4.4 1.9z" fill="#D4A017"/>
    <path d="M14.6 1.6 5.8 8.8l.6 5.1 2.4-3.4z" fill="#A87C11"/></svg>`,
  // OpenHands: an agent that drives a computer for you.
  openhands: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M8 1.4v2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
    <rect x="2.1" y="3.6" width="11.8" height="9.4" rx="2.6" fill="none" stroke="currentColor"
      stroke-width="1.3"/>
    <circle cx="5.8" cy="8.3" r="1.15" fill="currentColor"/>
    <circle cx="10.2" cy="8.3" r="1.15" fill="currentColor"/></svg>`,
  // A protocol bridge (ACP, MCP): two links of a chain.
  bridge: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M6.6 9.4a2.8 2.8 0 0 1 0-3.9l2-2a2.8 2.8 0 0 1 3.9 3.9l-.9.9" fill="none"
      stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/>
    <path d="M9.4 6.6a2.8 2.8 0 0 1 0 3.9l-2 2a2.8 2.8 0 0 1-3.9-3.9l.9-.9" fill="none"
      stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/></svg>`,
  // A job hunt: the briefcase.
  briefcase: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="1.2" y="4.9" width="13.6" height="8.6" rx="1.4" fill="none" stroke="currentColor"
      stroke-width="1.3"/>
    <path d="M5.7 4.6V3.4c0-.6.5-1 1.1-1h2.4c.6 0 1.1.4 1.1 1v1.2M1.4 8.6h13.2" fill="none"
      stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  // The cockpit itself: a gauge.
  cockpit: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M1.8 12.4a6.9 6.9 0 1 1 12.4 0" fill="none" stroke="currentColor"
      stroke-width="1.4" stroke-linecap="round"/>
    <path d="M8 11.4 11.2 6.2" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round"/>
    <circle cx="8" cy="11.9" r="1.2" fill="currentColor"/></svg>`,
  // SSH: the key.
  ssh: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="5.1" cy="10.9" r="3.1" fill="none" stroke="currentColor" stroke-width="1.35"/>
    <path d="M7.3 8.7 13.6 2.4M11.4 4.6l1.6 1.6M9.8 6.2l1.6 1.6" fill="none"
      stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/></svg>`,
  // Upgrades: what lands on the box.
  upgrade: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M8 10.6V1.9M4.8 5.1 8 1.9l3.2 3.2" fill="none" stroke="currentColor"
      stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M1.9 10.4v2.6c0 .6.5 1.1 1.1 1.1h10c.6 0 1.1-.5 1.1-1.1v-2.6" fill="none"
      stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/></svg>`,
  // A log file on disk.
  logfile: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M3.1 1.6h6L13 5.4v9c0 .6-.5 1-1.1 1H3.1c-.6 0-1.1-.4-1.1-1V2.6c0-.6.5-1 1.1-1z"
      fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
    <path d="M8.9 1.8v3.6h3.7M4.6 8.6h6M4.6 11.1h6M4.6 13h3.6" fill="none"
      stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>`,
  // Obsidian: the faceted gem / crystal mark.
  obsidian: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M5.4 1.5 L10.6 1.5 L14 5.5 L8 14.5 L2 5.5 Z" fill="#7C3AED" opacity=".25"/>
    <path d="M5.4 1.5 L10.6 1.5 L14 5.5 L8 14.5 L2 5.5 Z M5.4 1.5 L8 6 L10.6 1.5 M8 6 L8 14.5 M8 6 L2 5.5 M8 6 L14 5.5"
      fill="none" stroke="#A78BFA" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
};

// Entries are named after what they are, so the icon usually needs no config:
// the name (or an alias of it) is the lookup key, and `icon = ...` overrides.
Object.assign(ICONS, {
  "jellyfin-web": ICONS.jellyfin,
  "karakeep-meilisearch": ICONS.meilisearch,
  "karakeep-chrome": ICONS.chrome,
  "raspberry-pi": ICONS.raspberry,
  "hermes-ai": ICONS.hermes,
  "openhands-ai": ICONS.openhands,
  "arr-mcp-backend": ICONS.bridge,
  "ai-job-search": ICONS.briefcase,
  "homelab-cockpit": ICONS.cockpit,
  "ai-services-upgrade": ICONS.upgrade,
  "unattended-upgrades": ICONS.upgrade,
  "obsidian-sync": ICONS.obsidian,
});

const icon = (name) => ICONS[name] || "";
const iconOf = (s) => icon(s.icon || String(s.name).trim().toLowerCase().replace(/[ _]+/g, "-"));
// Where it runs, when that is not this box. The service's own icon already says
// "Raspberry Pi" on the Pi entry itself, so it is not badged twice.
const nodeBadge = (s) => s.node === "pi" && s.icon !== "raspberry"
  ? `<span class="node" title="runs on the Raspberry Pi">${icon("raspberry")}</span>` : "";

function altSession(s) {
  const list = s.tmux_sessions || [];
  if (!list.length) return "";
  return list.map(name => {
    const live = s.attached_sessions && s.attached_sessions.includes(name);
    return `<a class="alt" href="/terminal?session=${qs(name)}"
      title="tmux session: ${esc(name)}">${icon("terminal")}<span class="dot ${live ? "up" : "warn"}"></span></a>`;
  }).join("");
}

// An address you paste into an agent's config, not a page you visit. Copying is
// the only thing you ever do with it, so that is the only button it gets.
const copyBtn = (value, cls) => `<button class="${cls}" data-copy="${esc(value)}"
  title="Copy ${esc(value)}">${cls === "alt copy" ? icon("copy") : "Copy"}</button>`;

function chip(s) {
  const { primary, alt, altLabel } = links(s);
  // No page behind it, but still worth a chip when it names an endpoint: you
  // come here to read its state and take the address away with you.
  if (!primary && !s.endpoint) return "";
  const cls = "chip" + (s.state === "up" ? "" : " offline");
  const head = `<span class="dot ${esc(s.state)}"></span>${iconOf(s)}${esc(s.name)}${nodeBadge(s)}`;
  const altList = (s.alt_links && s.alt_links.length)
    ? s.alt_links
    : (alt ? [{ href: alt, icon: s.alt_icon, label: altLabel }] : []);
  const altButtons = altList.map(a => `<a class="alt" href="${esc(a.href)}"${a.href.startsWith("/") ? "" : ' target="_blank" rel="noopener"'}
    title="${esc(a.label || a.icon || "alt")}: ${esc(a.href)}">${icon(a.icon) || esc(a.label || "alt")}</a>`).join("");
  return `<span class="${cls}">
    ${primary
      ? `<a href="${esc(primary)}" target="_blank" rel="noopener">${head}</a>`
      : `<span class="plain" title="${esc(s.endpoint)}">${head}</span>`}
    ${s.endpoint ? copyBtn(s.endpoint, "alt copy") : ""}
    ${altSession(s)}
    ${s.has_chip_shell ? `<a class="alt" href="/terminal?service=${qs(s.name)}"
      title="shell: ${esc(s.command)}">${icon("terminal")}</a>` : ""}
    ${altButtons}</span>`;
}

function launcher(l) {
  if (!l.enabled) return "";
  return `<span class="chip term">
    <a href="/terminal?service=${qs(l.name)}">${icon(l.icon)}${esc(l.name)}
      ${l.command ? `<code>${esc(l.command)}</code>` : ""}</a></span>`;
}

// The tmux sessions a preconfigured row owns: its claude, agy and Shell
// buttons (names as tmux_manager.session_name_for_check builds them, plus the
// unprefixed names older sessions still carry).
function presetSessionNames(l) {
  const n = l.service.replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  return {
    claude: [`cockpit-${n}-claude`, `${n}-claude`],
    agy: [`cockpit-${n}-agy`, `${n}-agy`],
    shell: [`cockpit-${n}`],
  };
}

// The Remote Control servers serving a workspace: a dot for the unit, the
// agent's mark opening its web console, and the unit's logs. A workspace with
// no Claude server gets a "+ RC" link to the create form, path filled in.
// A workspace locked in services.conf (`rc_locked`) shows a lock instead.
function rcCell(l) {
  if (l.rc_locked) {
    return `<span class="rc-cell"><span class="btn-table-action" style="cursor:default; opacity:0.7;" title="No Remote Control here: ${esc(l.rc_locked)}">🔒 no RC</span></span>`;
  }
  const rcs = (l.rc || []).map(r => `<span class="rc-pill" title="${esc(r.unit)}: ${esc(r.detail || r.state)}">
      <span class="dot ${esc(r.state)}"></span>
      <a class="btn-table-action${r.state === "up" ? " primary-link" : ""}" href="${esc(r.web)}" target="_blank" rel="noopener"
        title="Open the ${r.agent === "claude" ? "Claude" : "Antigravity"} web console">${icon(r.agent)} web</a>
      <a class="btn-table-action" href="${esc(r.logs)}" title="Logs of ${esc(r.unit)}">logs</a>
    </span>`).join("");
  const hasClaude = (l.rc || []).some(r => r.agent === "claude");
  const add = !hasClaude && l.dir
    ? `<a class="btn-table-action" href="/claude-rc?workspace=${qs(l.dir)}" title="Start an always-on Claude Remote Control server in ${esc(l.dir)}">+ RC</a>`
    : "";
  return `<span class="rc-cell">${rcs}${add}</span>`;
}

// One row per AI workspace: where it opens, the Remote Control servers running
// there, and a button per local way in.
// A button whose tmux session already runs reads "attach", with a dot (green:
// someone is attached, amber: it runs in the background) - those sessions are
// left out of the Other Active Live Sessions table below, so each shows once.
function sessionRow(l, tmux) {
  const sessions = (tmux && tmux.sessions) || [];
  const names = presetSessionNames(l);
  const live = kind => sessions.find(t => names[kind].includes(t.name));
  const button = (kind, href, iconName, label, launchTitle) => {
    const t = live(kind);
    const dot = t ? `<span class="dot ${t.attached ? "up" : "warn"}"></span>` : "";
    const title = t
      ? `Running (${t.attached ? "attached" : "background"}): attach to ${t.name}`
      : launchTitle;
    return `<a class="btn-table-action${t ? " primary-link" : ""}" href="${href}" title="${esc(title)}">${dot}${icon(iconName)} ${t ? "attach" : label}</a>`;
  };
  const dash = `<span class="muted-dash">—</span>`;
  const launch = (cmd, iconName, label) => l.terminal ? button(cmd,
    `/terminal?service=${qs(l.service)}&cmd=${cmd}`, iconName, cmd,
    `Launch ${label} in ${l.name}: ${l[`${cmd}_command`] || cmd}`) : dash;
  const shell = l.terminal && l.command
    ? button("shell", `/terminal?service=${qs(l.service)}`, "terminal", "Shell", `Shell, runs: ${l.command}`)
    : `<span class="muted-dash">—</span>`;
  const del = l.custom
    ? `<button type="button" class="btn-table-action" data-delete-session="${esc(l.name)}" title="Remove session ${esc(l.name)}">×</button>`
    : "";
  const home = "/home/zfadli";
  const dir = (l.dir || "").startsWith(home) ? "~" + l.dir.slice(home.length) : (l.dir || "");
  return `<tr>
    <td class="service-cell"><span class="service-head">${icon(l.icon || "briefcase")}<span class="service-table-name">${esc(l.name)}</span></span></td>
    <td><code title="${esc(l.dir || "")}">${esc(dir)}</code></td>
    <td style="color:var(--muted);">${esc(l.note || "")}</td>
    <td>${rcCell(l)}</td>
    <td style="text-align:center;">${launch("claude", "claude", "Claude Code")}</td>
    <td style="text-align:center;">${launch("agy", "antigravity", "Antigravity")}</td>
    <td style="text-align:center;">${shell}</td>
    <td style="text-align:center;">${del}</td>
  </tr>`;
}

function card(s) {
  const { primary, alt, altLabel } = links(s);
  const named = (href, label) =>
    `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(label)}</a>`;
  const altList = (s.alt_links && s.alt_links.length)
    ? s.alt_links
    : (s.alt_link ? [{ href: s.alt_link, icon: s.alt_icon, label: s.alt_label }] : []);
  const consoles = altList.map(a => named(a.href, a.label || a.icon || "alt")).join("");
  const toggleBtn = s.can_toggle
    ? `<button class="btn-toggle ${s.unit_enabled ? "on" : "off"}" data-toggle-service="${esc(s.name)}" data-enabled="${s.unit_enabled ? "true" : "false"}" title="${s.unit_enabled ? "Click to disable (systemctl disable)" : "Click to enable (systemctl enable)"}"><span class="dot ${s.unit_enabled ? "up" : "down"}"></span>${s.unit_enabled ? "Enabled" : "Disabled"}</button>`
    : "";
  const acts = [
    toggleBtn,
    s.has_logs ? `<a href="/logs?service=${qs(s.name)}">Logs</a>` : "",
    s.has_terminal ? `<a href="/terminal?service=${qs(s.name)}">Shell</a>` : "",
    s.has_terminal ? `<a href="/terminal?service=${qs(s.name)}&cmd=agy">agy</a>` : "",
    s.has_terminal ? `<a href="/terminal?service=${qs(s.name)}&cmd=claude">claude</a>` : "",
    s.has_host_shell ? `<a href="/terminal?service=${qs(s.name)}&where=host">Compose</a>` : "",
    alt ? `<a href="${esc(alt)}" target="_blank" rel="noopener">${altLabel}</a>` : "",
    consoles,
    s.endpoint ? copyBtn(s.endpoint, "copy") : "",
  ].join("");
  return `<div class="card ${esc(s.state)}">
    <span class="dot"></span>
    <div class="body">
      <div class="name">${iconOf(s)}${primary
        ? `<a href="${esc(primary)}" target="_blank" rel="noopener">${esc(s.name)}</a>`
        : esc(s.name)}${nodeBadge(s)}</div>
      <div class="detail">${esc(s.detail)}</div>
      <div class="meta">${[s.meta, s.note].filter(Boolean).map(esc).join(" · ")}</div>
      ${s.endpoint ? `<div class="meta"><code>${esc(s.endpoint)}</code></div>` : ""}
      <div class="acts">${acts}</div>
    </div>
  </div>`;
}

let servicesSortColumn = "group";
let servicesSortAsc = true;
let servicesSearchQuery = "";
let servicesSelectedGroup = "";
let servicesSelectedType = "";
let cachedOtherServices = [];

function serviceTableRow(s) {
  const { primary, alt, altLabel } = links(s);
  const altList = (s.alt_links && s.alt_links.length)
    ? s.alt_links
    : (s.alt_link ? [{ href: s.alt_link, icon: s.alt_icon, label: s.alt_label }] : []);

  // 1. Service column
  const nameEl = primary
    ? `<a href="${esc(primary)}" target="_blank" rel="noopener" class="service-table-link">${esc(s.name)}</a>`
    : `<span class="service-table-name">${esc(s.name)}</span>`;
  const nodeEl = nodeBadge(s);
  const noteText = s.note || s.detail || "";
  const serviceCell = `
    <div class="service-cell">
      <div class="service-head">${iconOf(s)}${nameEl}${nodeEl}</div>
      ${noteText ? `<div class="rc-unit-sub" title="${esc(noteText)}">${esc(noteText)}</div>` : ""}
      ${s.endpoint ? `<div class="meta" style="margin-top:2px;"><code>${esc(s.endpoint)}</code></div>` : ""}
    </div>`;

  // 2. Group column
  const groupCell = `<span class="rc-scope-badge" style="margin-left:0;">${esc(s.group)}</span>`;

  // 3. Status column
  const statusCell = `
    <div class="status-cell">
      <span class="rc-status-cell"><span class="dot ${esc(s.state)}"></span><b style="text-transform:capitalize;">${esc(s.state)}</b></span>
      ${s.detail && s.state !== "up" ? `<span class="rc-unit-sub" style="color:var(--${esc(s.state)});" title="${esc(s.detail)}">${esc(s.detail)}</span>` : ""}
    </div>`;

  // 4. Open / Web column
  const openBtns = [];
  if (primary) {
    openBtns.push(`<a class="btn-table-action primary-link" href="${esc(primary)}" target="_blank" rel="noopener" title="Open ${esc(primary)}">Open ↗</a>`);
  }
  if (alt) {
    openBtns.push(`<a class="btn-table-action" href="${esc(alt)}" target="_blank" rel="noopener" title="${esc(altLabel)}: ${esc(alt)}">${esc(altLabel)}</a>`);
  }
  altList.forEach(a => {
    if (a.href !== primary && a.href !== alt) {
      openBtns.push(`<a class="btn-table-action" href="${esc(a.href)}" target="_blank" rel="noopener" title="${esc(a.label || a.icon || 'alt')}">${esc(a.label || a.icon || 'alt')}</a>`);
    }
  });
  if (s.endpoint) {
    openBtns.push(copyBtn(s.endpoint, "btn-table-action copy"));
  }
  const openCell = openBtns.length ? `<div class="btn-group" style="justify-content:center;">${openBtns.join("")}</div>` : `<span class="muted-dash">—</span>`;

  // 5. Shell column
  const shellBtns = [];
  if (s.has_terminal) {
    shellBtns.push(`<a class="btn-table-action" href="/terminal?service=${qs(s.name)}" title="Shell in ${esc(s.name)}">${icon("terminal")} Shell</a>`);
  }
  if (s.has_host_shell) {
    shellBtns.push(`<a class="btn-table-action" href="/terminal?service=${qs(s.name)}&where=host" title="Host compose shell">${icon("docker")} Compose</a>`);
  }
  const shellCell = shellBtns.length ? `<div class="btn-group" style="justify-content:center;">${shellBtns.join("")}</div>` : `<span class="muted-dash">—</span>`;

  // 6. agy column
  const agyCell = s.has_terminal
    ? `<a class="btn-table-action" href="/terminal?service=${qs(s.name)}&cmd=agy" title="Antigravity in ${esc(s.name)}">${icon("antigravity")} agy</a>`
    : `<span class="muted-dash">—</span>`;

  // 7. claude column
  const claudeCell = s.has_terminal
    ? `<a class="btn-table-action" href="/terminal?service=${qs(s.name)}&cmd=claude" title="Claude Code in ${esc(s.name)}">${icon("claude")} claude</a>`
    : `<span class="muted-dash">—</span>`;

  // 8. Logs column
  const logsCell = s.has_logs
    ? `<a class="btn-table-action" href="/logs?service=${qs(s.name)}" title="Logs for ${esc(s.name)}">Logs</a>`
    : `<span class="muted-dash">—</span>`;

  // 9. Toggle column
  let toggleCell = `<span class="muted-dash">—</span>`;
  if (s.can_toggle) {
    toggleCell = `<button type="button" class="btn-toggle ${s.unit_enabled ? "on" : "off"}" data-toggle-service="${esc(s.name)}" data-enabled="${s.unit_enabled ? "true" : "false"}" title="${s.unit_enabled ? "Click to disable (systemctl disable)" : "Click to enable (systemctl enable)"}"><span class="dot ${s.unit_enabled ? "up" : "down"}"></span>${s.unit_enabled ? "Enabled" : "Disabled"}</button>`;
  } else if (s.unit_file_state) {
    toggleCell = `<span class="rc-scope-badge" style="margin:0;" title="Unit file state">${esc(s.unit_file_state)}</span>`;
  }

  return `<tr>
    <td>${serviceCell}</td>
    <td>${groupCell}</td>
    <td>${statusCell}</td>
    <td style="text-align: center;">${openCell}</td>
    <td style="text-align: center;">${shellCell}</td>
    <td style="text-align: center;">${agyCell}</td>
    <td style="text-align: center;">${claudeCell}</td>
    <td style="text-align: center;">${logsCell}</td>
    <td style="text-align: center;">${toggleCell}</td>
  </tr>`;
}

function renderOtherServicesTable(otherGroups) {
  const allServices = [];
  otherGroups.forEach(g => {
    (g.services || []).forEach(s => {
      allServices.push(s);
    });
    (g.launchers || []).forEach(l => {
      allServices.push({
        name: l.name,
        group: g.name,
        state: "up",
        detail: l.note || l.command || "",
        note: l.note || "",
        icon: l.icon || "terminal",
        command: l.command || "",
        has_terminal: l.enabled,
        has_chip_shell: l.enabled && Boolean(l.command),
        has_logs: false,
        has_host_shell: false,
        can_toggle: false,
        is_launcher: true,
      });
    });
  });

  cachedOtherServices = allServices;

  // Populate Quick Group Filter Pills in Filter Bar
  const pillsContainer = document.getElementById("servicesGroupPills");
  if (pillsContainer) {
    const groupNames = Array.from(new Set(allServices.map(s => s.group))).filter(Boolean).sort();
    const allActive = !servicesSelectedGroup ? " active" : "";
    let pillsHtml = `<button type="button" class="group-filter-pill${allActive}" data-group-pill="">All <span class="pill-count">(${allServices.length})</span></button>`;
    groupNames.forEach(gn => {
      const count = allServices.filter(s => s.group === gn).length;
      const active = servicesSelectedGroup === gn ? " active" : "";
      pillsHtml += `<button type="button" class="group-filter-pill${active}" data-group-pill="${esc(gn)}">${esc(gn)} <span class="pill-count">(${count})</span></button>`;
    });
    pillsContainer.innerHTML = pillsHtml;
  }

  updateServicesTableRows();
}

function updateServicesTableRows() {
  const tbody = document.getElementById("servicesTableBody");
  if (!tbody) return;

  const q = (servicesSearchQuery || "").trim().toLowerCase();
  let filtered = cachedOtherServices.filter(s => {
    // 1. State filter
    if (activeStateFilter !== null && s.state !== activeStateFilter) {
      return false;
    }
    // 2. Group filter
    if (servicesSelectedGroup && s.group !== servicesSelectedGroup) {
      return false;
    }
    // 3. Type filter
    if (servicesSelectedType) {
      const st = String(s.type || s.meta || "").toLowerCase();
      if (!st.includes(servicesSelectedType.toLowerCase())) {
        return false;
      }
    }
    // 4. Search query
    if (q) {
      const match = (s.name && s.name.toLowerCase().includes(q)) ||
        (s.group && s.group.toLowerCase().includes(q)) ||
        (s.detail && s.detail.toLowerCase().includes(q)) ||
        (s.note && s.note.toLowerCase().includes(q)) ||
        (s.endpoint && s.endpoint.toLowerCase().includes(q)) ||
        (s.link && s.link.toLowerCase().includes(q)) ||
        (s.remote && s.remote.toLowerCase().includes(q));
      if (!match) return false;
    }
    return true;
  });

  // Sorting
  filtered.sort((a, b) => {
    let cmp = 0;
    if (servicesSortColumn === "name") {
      cmp = (a.name || "").localeCompare(b.name || "");
    } else if (servicesSortColumn === "group") {
      cmp = (a.group || "").localeCompare(b.group || "");
      if (cmp === 0) cmp = (a.name || "").localeCompare(b.name || "");
    } else if (servicesSortColumn === "state") {
      const rank = { down: 0, warn: 1, unknown: 2, up: 3 };
      const ra = rank[a.state] ?? 9;
      const rb = rank[b.state] ?? 9;
      cmp = ra - rb;
      if (cmp === 0) cmp = (a.name || "").localeCompare(b.name || "");
    }
    return servicesSortAsc ? cmp : -cmp;
  });

  // Update sort arrow indicators
  ["name", "group", "state"].forEach(col => {
    const el = document.getElementById(`sort-arrow-${col}`);
    if (el) {
      el.textContent = servicesSortColumn === col ? (servicesSortAsc ? "▲" : "▼") : "↕";
    }
  });

  // Update count badge
  const countBadge = document.getElementById("servicesCountBadge");
  if (countBadge) {
    if (filtered.length === cachedOtherServices.length) {
      countBadge.textContent = `${filtered.length} services`;
    } else {
      countBadge.textContent = `${filtered.length} / ${cachedOtherServices.length} services`;
    }
  }

  // Update Reset button visibility in filter bar
  const resetBtn = document.getElementById("resetAllFiltersBtn");
  const hasActiveFilters = Boolean(q || servicesSelectedGroup || servicesSelectedType || activeStateFilter !== null);
  if (resetBtn) {
    resetBtn.style.display = hasActiveFilters ? "" : "none";
  }

  // Update clear search button
  const clearSearchBtn = document.getElementById("clearSearchBtn");
  if (clearSearchBtn) {
    clearSearchBtn.style.display = q ? "" : "none";
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--muted); padding: 32px 14px;">No services matching current filter</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(serviceTableRow).join("");
}

const RANK = { claude: 0, antigravity: 0, terminal: 1 };
const rank = (item) => RANK[item.icon] ?? 2;

function group(g, tmux) {
  // The quick row is the operating surface: it holds the launchers plus
  // whatever is up and has somewhere to click through to. Ordered by what the
  // chip opens - Claude sessions, then local shells, then plain links - so the
  // two kinds of "somewhere to work" lead. Sorting is stable, so config order
  // still decides within each kind.

  const tmuxCount = tmux ? tmux.count : 0;
  const tmuxBadge = tmuxCount > 0 ? ` (${tmuxCount})` : "";
  const infraLaunchers = g.name === "Infra" ? [
    { icon: "terminal", html: `<span class="chip term"><a href="/tmux" title="manage and open active tmux sessions">${icon("terminal")}Tmux sessions${tmuxBadge}</a></span>` },
  ] : [];
  const launchers = g.launchers.filter(l => l.enabled).map(l => ({ icon: l.icon, html: launcher(l) }));

  // Services are filtered by activeStateFilter:
  // - When null, all services in the group are shown.
  // - When "up", "warn", "down", "unknown", only services matching that state are shown.
  let matchingServices = g.services;
  if (activeStateFilter !== null) {
    matchingServices = g.services.filter(s => s.state === activeStateFilter);
  }

  const eligible = matchingServices.filter(s => !s.headline)
    .filter(s => s.pinned || (s.state === "up" && (s.link || s.remote || s.endpoint)) || s.state === "warn" || s.state === "down");

  const quick = [
    ...infraLaunchers,
    ...launchers,
    ...eligible.map(s => ({ icon: s.icon, html: chip(s) })),
  ].sort((a, b) => rank(a) - rank(b)).map(item => item.html).join("");

  // If there are no launchers and no matching services, don't show the group
  if (!quick && matchingServices.length === 0) {
    return "";
  }

  const counts = ["down", "warn", "unknown", "up"]
    .map(state => [state, matchingServices.filter(s => s.state === state).length])
    .filter(([, n]) => n > 0)
    .map(([state, n]) => `<span><span class="dot ${state}"></span>${n} ${state}</span>`)
    .join("");

  const hasDegraded = matchingServices.some(s => s.state === "warn" || s.state === "down");
  const details = matchingServices.length ? `
    <details class="more" data-group="${esc(g.name)}"${hasDegraded || activeStateFilter !== null || isOpen(g.name) ? " open" : ""}>
      <summary>${matchingServices.length} ${matchingServices.length > 1 ? "Services" : "Service"} · Logs &amp; shells</summary>
      <div class="grid">${matchingServices.map(card).join("")}</div>
    </details>` : "";

  return `<section class="group">
    <div class="ghead"><h2>${esc(g.name)}</h2>${counts ? `<span class="gsum">${counts}</span>` : ""}</div>
    <div class="quick">${quick}</div>
    ${details}
  </section>`;
}

// Plan-usage health bars: how close the Claude and Antigravity accounts
// running this homelab are to their 5-hour and weekly limits. Refreshed on
// its own slow timer server-side (usage.py) and polled asynchronously via /api/usage.
function usageLevel(pct) {
  if (pct >= 85) return "down";
  if (pct >= 50) return "warn";
  return "up";
}

function parseResetDate(raw) {
  if (!raw) return null;
  let d = new Date(raw);
  if (!isNaN(d.getTime())) return d;

  // Claude format: "Aug 31, 6:59pm (Europe/Paris)" or "Aug 31, 1:09am"
  const m = String(raw).match(/^([A-Za-z]+)\\s+(\\d+),\\s*(\\d+)(?::(\\d+))?\\s*(am|pm)?/i);
  if (m) {
    const monthNames = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];
    const monthIdx = monthNames.indexOf(m[1].toLowerCase().slice(0, 3));
    if (monthIdx !== -1) {
      const day = parseInt(m[2], 10);
      let hour = parseInt(m[3], 10);
      const min = m[4] ? parseInt(m[4], 10) : 0;
      const ampm = m[5] ? m[5].toLowerCase() : null;
      if (ampm === "pm" && hour < 12) hour += 12;
      if (ampm === "am" && hour === 12) hour = 0;

      const now = new Date();
      let year = now.getFullYear();
      d = new Date(year, monthIdx, day, hour, min, 0);
      if (d.getTime() < now.getTime() - 180 * 86400 * 1000) {
        d = new Date(year + 1, monthIdx, day, hour, min, 0);
      }
      if (!isNaN(d.getTime())) return d;
    }
  }
  return null;
}

// A 5-hour window is short enough that "when" only matters as a countdown; a
// weekly one is long enough that a countdown stops being legible ("in 4290
// minutes") and the day it lands on is what you actually want to know. Both
// CLIs' reset strings parse as a Date - agy prints ISO, and claude's
// "Aug 25, 6:10am (Europe/Paris)" is parsed by parseResetDate.
function formatReset(reset, period) {
  if (!reset) return "";
  const d = parseResetDate(reset);
  if (!d) return reset;  // could not parse - show the CLI's own text verbatim
  if (period === "five_hour") {
    const ms = d.getTime() - Date.now();
    if (ms <= 0) return "any moment";
    const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000);
    return h > 0 ? `in ${h}h ${m}m` : `in ${m}m`;
  }
  return d.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" });
}

function usageMeter(label, bar, period) {
  if (!bar) {
    return `<span class="meter"><span class="mlabel">${label}</span><span class="mval muted">n/a</span></span>`;
  }
  const pct = Math.min(Math.max(bar.pct, 0), 100);
  const reset = formatReset(bar.reset, period);
  const title = `${label}: ${bar.pct}% of the limit used` + (reset ? ` · resets ${reset}` : "");
  return `<span class="meter" title="${esc(title)}">
    <span class="mlabel">${label}</span>
    <span class="bar-track"><span class="bar-fill ${usageLevel(bar.pct)}" style="width:${pct}%"></span></span>
    <span class="mval">${bar.pct}% used${reset ? ` <span class="reset">· resets ${esc(reset)}</span>` : ""}</span></span>`;
}

function usageCard(name, iconKey, entry) {
  if (!entry) return "";
  if (entry.state !== "ok") {
    return `<span class="usage-card offline" title="${esc(entry.detail || "unavailable")}">
      ${icon(iconKey)}<span class="uname">${esc(name)}</span><span class="mval muted">n/a</span></span>`;
  }
  return `<span class="usage-card">
    ${icon(iconKey)}<span class="uname">${esc(name)}</span>
    ${usageMeter("5h", entry.bars.five_hour, "five_hour")}
    ${usageMeter("wk", entry.bars.weekly, "weekly")}</span>`;
}

let usageLoaded = false;

function renderUsage(usage) {
  // Both cards render the same metric the same way - "% of the limit used",
  // rising and turning red as a period runs out - so this caption only needs
  // to say it once, not have every meter repeat it.
  document.getElementById("usageBars").innerHTML = usage
    ? `<span class="usage-caption">plan limits · % used</span>`
      + usageCard("Claude", "claude", usage.claude) + usageCard("Antigravity", "antigravity", usage.agy)
    : "";
}

async function pollUsage() {
  try {
    const response = await fetch("/api/usage", { cache: "no-store" });
    if (response.ok) {
      const u = await response.json();
      if (u) {
        usageLoaded = true;
        renderUsage(u);
      } else if (!usageLoaded) {
        setTimeout(pollUsage, 2500);
      }
    }
  } catch (err) {
    // ignore
  }
}

let activeStateFilter = null;
let lastData = null;
let lastSignature = "";

function render(data) {
  lastData = data;
  const t = data.totals;
  const lead = (data.headline || []).map(chip).join("");
  const tmuxCount = data.tmux ? data.tmux.count : 0;
  const tmuxBadge = tmuxCount > 0 ? ` (${tmuxCount})` : "";

  const newSessionChip = `<span class="chip term"><a href="/terminal?session=new" title="start direct terminal session in ~">${icon("terminal")}+ New session</a></span>`;
  const lastActive = data.tmux ? (data.tmux.last_active || (data.tmux.sessions && data.tmux.sessions[0])) : null;
  const lastActivePill = lastActive ? (() => {
    const raw = lastActive.name;
    const shortName = raw.startsWith("cockpit-") ? raw.slice(8) : raw;
    const cls = lastActive.attached ? "up" : "warn";
    return `<a class="pill ${cls}" href="/terminal?session=${qs(raw)}" title="resume last active session (${esc(raw)})"><span class="dot"></span><b>${esc(shortName)}</b></a>`;
  })() : "";
  const allTmuxChip = `<span class="chip term"><a href="/tmux" title="manage all tmux sessions">${icon("terminal")}Tmux sessions${tmuxBadge}</a></span>`;
  const ideasChip = `<span class="chip" style="border-color: rgba(88,166,255,0.3);"><a href="/idea" title="Obsidian project ideas bucket, kanban & waterfall">💡 Ideas</a></span>`;

  const statePills = [
    ["up", "Up", t.up], ["warn", "Degraded", t.warn],
    ["down", "Down", t.down], ["unknown", "Unknown", t.unknown],
  ].filter(([, , n]) => n > 0).map(([cls, label, n]) => {
    const active = activeStateFilter === cls ? " active" : "";
    return `<button type="button" class="pill ${cls}${active}" data-state-filter="${cls}" title="${active ? "Click to clear filter" : "Click to view " + label + " services"}"><span class="dot"></span><b>${n}</b> ${label}</button>`;
  }).join("");

  const hideBtn = activeStateFilter
    ? `<button type="button" class="pill" data-state-filter="clear" title="Show all services" style="opacity: 0.8; font-weight: 500;">✕ Clear filter</button>`
    : "";

  document.getElementById("totals").innerHTML = statePills + hideBtn;

  const aiGroup = data.groups.find(g => g.name === "AI Sessions" || g.name === "Preconfigured AI Sessions");
  const otherGroups = data.groups.filter(g => g !== aiGroup);

  const aiGroupEl = document.getElementById("aiSessionsGroup");
  const workspaces = data.workspaces || [];
  if (workspaces.length) {
    if (aiGroupEl) aiGroupEl.style.display = "";
    const aiLaunchers = workspaces.map(l => sessionRow(l, data.tmux)).join("");
    const aiQuickEl = document.getElementById("aiSessionsQuick");
    if (aiQuickEl) aiQuickEl.innerHTML = aiLaunchers;
  } else if (aiGroupEl) {
    aiGroupEl.style.display = "none";
  }

  // Other Active Live Sessions section in Tab 1
  const activeSecEl = document.getElementById("activeSessionsSection");
  const activeQuickEl = document.getElementById("activeSessionsQuick");
  const activeCountEl = document.getElementById("activeSessionsCount");
  const presetNames = new Set(workspaces
    .filter(l => l.service)
    .flatMap(l => Object.values(presetSessionNames(l)).flat()));
  const tmuxSessions = ((data.tmux && data.tmux.sessions) || [])
    .filter(t => !presetNames.has(t.name));
  if (activeSecEl && activeQuickEl) {
    if (tmuxSessions.length > 0) {
      activeSecEl.style.display = "";
      if (activeCountEl) activeCountEl.textContent = `${tmuxSessions.length} active`;
      activeQuickEl.innerHTML = tmuxSessions.map(s => {
        const live = s.attached;
        const isCockpit = s.name.startsWith("cockpit-");
        const shortName = isCockpit ? s.name.slice(8) : s.name;
        let toolIcon = "terminal";
        if (s.name.endsWith("-claude") || s.name.includes("claude")) toolIcon = "claude";
        else if (s.name.endsWith("-agy") || s.name.includes("agy") || s.name.includes("antigravity")) toolIcon = "antigravity";
        const dot = `<span class="dot ${live ? "up" : "warn"}"></span>`;
        return `<tr>
          <td class="service-cell"><span class="service-head" title="${esc(s.name)}">${icon(toolIcon)}<span class="service-table-name">${esc(shortName)}</span></span></td>
          <td style="color:var(--muted);"><span class="service-head" style="font-weight:400;">${dot}${live ? `attached (${s.attached_count})` : "background"}</span></td>
          <td style="text-align:center;"><a class="btn-table-action primary-link" href="/terminal?session=${qs(s.name)}" title="Attach to session ${esc(s.name)}">attach</a></td>
        </tr>`;
      }).join("");
    } else {
      activeSecEl.style.display = "none";
      activeQuickEl.innerHTML = "";
    }
  }

  // Update tab button count badge
  const tmuxTabBtn = document.querySelector('[data-tab="tmux-sessions"]');
  if (tmuxTabBtn) {
    const count = (data.tmux && data.tmux.count) || 0;
    tmuxTabBtn.innerHTML = `<svg class="ico" viewBox="0 0 16 16"><rect x="1" y="2.5" width="14" height="11" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M4 6l2.5 2L4 10 M8.5 10.5h3.5" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Tmux Sessions${count > 0 ? ` (${count})` : ""}`;
  }

  // Render Other Services Table
  renderOtherServicesTable(otherGroups);

  document.getElementById("updated").textContent = "updated " + data.generated_at;
  document.body.classList.remove("stale");

  const activeTab = localStorage.getItem("cockpit_active_tab");
  if (activeTab === "tmux-sessions") {
    loadTmuxSessions();
  }
}

document.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-state-filter]");
  if (!btn) return;
  event.preventDefault();
  const filter = btn.dataset.stateFilter;
  if (filter === "clear" || activeStateFilter === filter) {
    activeStateFilter = null;
  } else {
    activeStateFilter = filter;
  }
  if (lastData) {
    lastSignature = "";
    render(lastData);
  }
});

// Other services filter bar & sorting listeners
document.addEventListener("input", (e) => {
  if (e.target && e.target.id === "servicesSearchInput") {
    servicesSearchQuery = e.target.value;
    updateServicesTableRows();
  }
});

document.addEventListener("change", (e) => {
  if (e.target && e.target.id === "servicesTypeFilter") {
    servicesSelectedType = e.target.value;
    updateServicesTableRows();
  }
});

document.addEventListener("click", (e) => {
  if (e.target && e.target.id === "clearSearchBtn") {
    e.preventDefault();
    servicesSearchQuery = "";
    const inp = document.getElementById("servicesSearchInput");
    if (inp) { inp.value = ""; inp.focus(); }
    updateServicesTableRows();
    return;
  }

  const groupPill = e.target.closest("[data-group-pill]");
  if (groupPill) {
    e.preventDefault();
    servicesSelectedGroup = groupPill.dataset.groupPill || "";
    document.querySelectorAll(".group-filter-pill").forEach(p => {
      p.classList.toggle("active", p.dataset.groupPill === servicesSelectedGroup);
    });
    updateServicesTableRows();
    return;
  }

  if (e.target && e.target.id === "resetAllFiltersBtn") {
    e.preventDefault();
    servicesSearchQuery = "";
    servicesSelectedGroup = "";
    servicesSelectedType = "";
    activeStateFilter = null;
    const inp = document.getElementById("servicesSearchInput");
    if (inp) inp.value = "";
    const typeSel = document.getElementById("servicesTypeFilter");
    if (typeSel) typeSel.value = "";
    document.querySelectorAll(".group-filter-pill").forEach(p => {
      p.classList.toggle("active", p.dataset.groupPill === "");
    });
    if (lastData) {
      render(lastData);
    } else {
      updateServicesTableRows();
    }
    return;
  }

  const sortBtn = e.target.closest(".sort-header");
  if (sortBtn && sortBtn.dataset.sort) {
    e.preventDefault();
    const col = sortBtn.dataset.sort;
    if (servicesSortColumn === col) {
      servicesSortAsc = !servicesSortAsc;
    } else {
      servicesSortColumn = col;
      servicesSortAsc = true;
    }
    updateServicesTableRows();
  }
});

// Delegated: every poll that changes something rebuilds the cards wholesale,
// so a listener bound to a button would not survive the next refresh.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  event.preventDefault();
  const value = button.dataset.copy;
  try {
    // Only available over HTTPS or on localhost; the LAN view is plain HTTP,
    // so fall back to the old execCommand path rather than silently doing
    // nothing on exactly the address you reach this page from most often.
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
    } else {
      const scratch = document.createElement("textarea");
      scratch.value = value;
      scratch.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(scratch);
      scratch.select();
      document.execCommand("copy");
      scratch.remove();
    }
    button.classList.add("copied");
    setTimeout(() => button.classList.remove("copied"), 1200);
  } catch (err) {
    button.title = "copy failed - " + value;
  }
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-toggle-service]");
  if (!button) return;
  event.preventDefault();
  const service = button.dataset.toggleService;
  const currentEnabled = button.dataset.enabled === "true";
  const targetEnabled = !currentEnabled;

  button.disabled = true;
  const originalText = button.innerHTML;
  button.textContent = "…";

  try {
    const res = await fetch("/api/service/toggle-enable", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service: service, enabled: targetEnabled })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      alert("Toggle failed: " + (data.message || "error"));
    }
  } catch (err) {
    alert("Toggle failed: " + err);
  } finally {
    await poll();
  }
});

document.getElementById("expand").addEventListener("click", (event) => {
  event.preventDefault();
  const details = document.querySelectorAll("details.more");
  if (!details.length) return;
  const opening = [...details].some(el => !el.open);
  details.forEach(el => { el.open = opening; });
  event.target.textContent = opening ? "Collapse all" : "Expand all";
});

async function poll() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    render(await response.json());
  } catch (err) {
    document.body.classList.add("stale");
    document.getElementById("updated").textContent = "unreachable — retrying…";
  }
}

function switchTab(tabId) {
  document.querySelectorAll(".cockpit-tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabId);
  });
  document.querySelectorAll(".cockpit-tab-pane").forEach(pane => {
    pane.style.display = pane.id === "pane-" + tabId ? "" : "none";
  });
  localStorage.setItem("cockpit_active_tab", tabId);
  if (tabId === "ideas") {
    const iframe = document.getElementById("ideasIframe");
    if (iframe && !iframe.src) iframe.src = iframe.dataset.src;
  } else if (tabId === "projects") {
    const iframe = document.getElementById("projectsIframe");
    if (iframe && !iframe.src) iframe.src = iframe.dataset.src;
  } else if (tabId === "cron") {
    const iframe = document.getElementById("cronIframe");
    if (iframe && !iframe.src) iframe.src = iframe.dataset.src;
  } else if (tabId === "tmux-sessions") {
    loadTmuxSessions();
  }
}

let tmuxLoaded = false;
async function loadTmuxSessions() {
  const container = document.getElementById("tmuxSessionsContainer");
  if (!container) return;
  try {
    const res = await fetch("/api/tmux", { cache: "no-store" });
    const data = await res.json();
    const sessions = data.sessions || [];

    if (sessions.length === 0) {
      container.innerHTML = `<div style="text-align:center; color:var(--muted); padding:36px; background:var(--panel); border:1px solid var(--border); border-radius:8px;">
        No active tmux sessions right now. Use <b>+ New session</b> above or start a terminal session.
      </div>`;
      tmuxLoaded = true;
      return;
    }

    let rowsHtml = sessions.map(s => {
      const live = s.attached;
      const statusHtml = `<span class="rc-status-cell"><span class="dot ${live ? "up" : "warn"}"></span>${live ? `attached (${s.attached_count})` : "detached"}</span>`;
      const isCockpit = s.name.startsWith("cockpit-");
      const shortName = isCockpit ? s.name.slice(8) : s.name;
      const badge = isCockpit ? `<span class="rc-scope-badge">cockpit</span>` : `<span class="rc-scope-badge">tmux</span>`;
      const nameHtml = `<span class="rc-session-name">${esc(shortName)}</span>${badge}<span class="rc-unit-sub">${esc(s.name)}</span>`;
      const windowsHtml = `<span class="rc-config-text">${esc(s.windows)} window${s.windows === 1 ? "" : "s"}</span>`;
      const createdHtml = `<span class="rc-config-text">${esc(s.created_human || "")}</span>`;
      const actsHtml = `<div class="acts">
        <a href="/terminal?session=${qs(s.name)}">Attach</a>
        <button type="button" class="btn-subtle" data-rename-tmux="${esc(s.name)}" style="font-size:12px; padding:1px 8px;">Rename</button>
        <button type="button" class="btn-subtle" data-kill-tmux="${esc(s.name)}" style="font-size:12px; padding:1px 8px; color:var(--down); border-color:rgba(248,81,73,0.3);">Kill</button>
      </div>`;

      return `<tr>
        <td>${nameHtml}</td>
        <td>${statusHtml}</td>
        <td>${windowsHtml}</td>
        <td>${createdHtml}</td>
        <td>${actsHtml}</td>
      </tr>`;
    }).join("");

    container.innerHTML = `<div class="rc-table-wrap">
      <table class="rc-table">
        <thead>
          <tr>
            <th>Session</th>
            <th>Status</th>
            <th>Windows</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    </div>`;
    tmuxLoaded = true;
  } catch (err) {
    container.innerHTML = `<div class="card down"><div class="body"><div class="detail">Failed loading tmux sessions: ${esc(err)}</div></div></div>`;
  }
}

document.addEventListener("click", async (e) => {
  const killBtn = e.target.closest("[data-kill-tmux]");
  if (killBtn) {
    e.preventDefault();
    const name = killBtn.dataset.killTmux;
    if (!confirm(`Terminate tmux session "${name}" and all processes in it?`)) return;
    killBtn.disabled = true;
    try {
      const res = await fetch("/api/tmux/kill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session: name }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        alert(data.message || "Failed to kill tmux session");
      }
      await loadTmuxSessions();
      await poll();
    } catch (err) {
      alert("Error: " + err);
    }
    return;
  }

  const renameBtn = e.target.closest("[data-rename-tmux]");
  if (renameBtn) {
    e.preventDefault();
    const oldName = renameBtn.dataset.renameTmux;
    const currentShort = oldName.startsWith("cockpit-") ? oldName.slice(8) : oldName;
    const newName = prompt(`Enter new name for tmux session "${oldName}":`, currentShort);
    if (!newName || newName.trim() === currentShort || newName.trim() === oldName) return;
    renameBtn.disabled = true;
    try {
      const res = await fetch("/api/tmux/rename", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session: oldName, name: newName.trim() }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        alert(data.message || "Failed to rename tmux session");
      }
      await loadTmuxSessions();
      await poll();
    } catch (err) {
      alert("Error: " + err);
    }
    return;
  }

  if (e.target && e.target.id === "btnToggleNewTmux") {
    const form = document.getElementById("formNewTmux");
    if (form) {
      const isHidden = form.style.display === "none";
      form.style.display = isHidden ? "block" : "none";
      if (isHidden) {
        const inp = document.getElementById("newTmuxName");
        if (inp) inp.focus();
      }
    }
  } else if (e.target && e.target.id === "btnCancelNewTmux") {
    const form = document.getElementById("formNewTmux");
    if (form) form.style.display = "none";
  }
});

document.addEventListener("submit", async (e) => {
  if (e.target && e.target.id === "formNewTmux") {
    e.preventDefault();
    const nameInp = document.getElementById("newTmuxName");
    const msgEl = document.getElementById("newTmuxMsg");
    const rawName = nameInp.value.trim();
    if (!rawName) return;
    if (msgEl) msgEl.textContent = "Creating session…";
    try {
      const res = await fetch("/api/tmux/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: rawName, cwd: "~" }),
      });
      const data = await res.json();
      if (res.ok && data.ok && data.session) {
        if (msgEl) msgEl.textContent = "Redirecting…";
        location.href = "/terminal?session=" + qs(data.session);
      } else {
        if (msgEl) msgEl.textContent = "Error: " + (data.message || "Failed to create session");
      }
    } catch (err) {
      if (msgEl) msgEl.textContent = "Error: " + err;
    }
  }
});

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-tab]");
  if (btn) {
    e.preventDefault();
    switchTab(btn.dataset.tab);
  }
});

document.addEventListener("click", (e) => {
  if (e.target && e.target.id === "btnToggleAddRepo") {
    const form = document.getElementById("formAddRepo");
    if (form) {
      const isHidden = form.style.display === "none";
      form.style.display = isHidden ? "block" : "none";
      if (isHidden) {
        const inp = document.getElementById("addRepoPath");
        if (inp) inp.focus();
      }
    }
  } else if (e.target && e.target.id === "btnCancelAddRepo") {
    const form = document.getElementById("formAddRepo");
    if (form) form.style.display = "none";
  }
});

document.addEventListener("input", (e) => {
  if (e.target && e.target.id === "addRepoPath") {
    const nameInp = document.getElementById("addRepoName");
    if (nameInp && (!nameInp.value.trim() || nameInp.dataset.autofilled)) {
      const parts = e.target.value.trim().replace(/[\\/]+$/, "").split("/");
      const base = parts[parts.length - 1] || "";
      const deduced = base.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
      if (deduced) {
        nameInp.value = deduced;
        nameInp.dataset.autofilled = "true";
      }
    }
  }
  if (e.target && e.target.id === "addRepoName") {
    delete e.target.dataset.autofilled;
  }
});

document.addEventListener("submit", async (e) => {
  if (e.target && e.target.id === "formAddRepo") {
    e.preventDefault();
    let name = document.getElementById("addRepoName").value.trim();
    const path = document.getElementById("addRepoPath").value.trim();
    if (!name && path) {
      const parts = path.replace(/[\\/]+$/, "").split("/");
      name = (parts[parts.length - 1] || "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
    }
    const note = document.getElementById("addRepoNote").value.trim();
    const msgEl = document.getElementById("addRepoMsg");
    if (msgEl) msgEl.textContent = "Adding and committing to git…";
    try {
      const res = await fetch("/api/ai-sessions/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, path, note })
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        if (msgEl) msgEl.textContent = "Error: " + (data.message || "Failed");
        return;
      }
      if (msgEl) msgEl.textContent = "✓ Added and committed to git!";
      e.target.reset();
      setTimeout(() => {
        document.getElementById("formAddRepo").style.display = "none";
        if (msgEl) msgEl.textContent = "";
      }, 1200);
      await poll();
    } catch (err) {
      if (msgEl) msgEl.textContent = "Error: " + err;
    }
  }
});

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-delete-session]");
  if (!btn) return;
  e.preventDefault();
  const name = btn.dataset.deleteSession;
  if (!confirm(`Remove preconfigured session "${name}" from services.conf and commit?`)) return;
  try {
    const res = await fetch("/api/ai-sessions/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      alert("Error: " + (data.message || "Failed"));
      return;
    }
    await poll();
  } catch (err) {
    alert("Error: " + err);
  }
});

// The cockpit always opens on Ideas, whatever tab was open last time.
switchTab("ideas");
poll();
pollUsage();
setInterval(poll, __REFRESH__ * 1000);
setInterval(pollUsage, Math.max(__REFRESH__, 60) * 1000);
</script>
</body>
</html>
"""
