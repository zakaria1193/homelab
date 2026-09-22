"""HTML template and frontend client for the Idea Bucket, Kanban, and Waterfall dashboard."""

IDEAS_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=5">
<title>Idea Bucket &amp; Projects · __TITLE__</title>
<!-- Libraries via CDN: SortableJS (Kanban Drag & Drop), Masonry (Waterfall layout), Tabulator (Waterfall Table), Marked (Obsidian Markdown) -->
<link rel="stylesheet" href="https://unpkg.com/tabulator-tables@5.5.0/dist/css/tabulator.min.css">
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js"></script>
<script src="https://unpkg.com/masonry-layout@4/dist/masonry.pkgd.min.js"></script>
<script src="https://unpkg.com/tabulator-tables@5.5.0/dist/js/tabulator.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>

<style>
  :root {
    /* Light theme by default */
    --bg: #f6f8fa;
    --panel: #ffffff;
    --raise: #f0f2f5;
    --raise-hover: #e4e7eb;
    --border: #d0d7de;
    --text: #1f2328;
    --muted: #656d76;
    --up: #1a7f37;
    --down: #cf222e;
    --warn: #9a6700;
    --unknown: #6e7681;
    --accent: #0969da;
    --purple: #8250df;
    --teal: #0e7886;
    --card-bg: #ffffff;
    --notes-bg: #f6f8fa;
    --input-bg: #ffffff;
    --shadow: 0 1px 3px rgba(31, 35, 40, 0.12), 0 8px 24px rgba(66, 74, 83, 0.08);
    --card-shadow: 0 1px 3px rgba(31, 35, 40, 0.08);
    --card-hover-shadow: 0 4px 14px rgba(31, 35, 40, 0.14);
  }

  [data-theme="dark"] {
    --bg: #0d1117;
    --panel: #161b22;
    --raise: #1c2430;
    --raise-hover: #263344;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --up: #3fb950;
    --down: #f85149;
    --warn: #d29922;
    --unknown: #6e7681;
    --accent: #58a6ff;
    --purple: #bc8cff;
    --teal: #39c5bb;
    --card-bg: #0d1117;
    --notes-bg: #161b22;
    --input-bg: #0d1117;
    --shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
    --card-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
    --card-hover-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    transition: background 0.15s, color 0.15s;
    -webkit-font-smoothing: antialiased;
  }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }

  .wrap {
    max-width: 1600px;
    margin: 0 auto;
    padding: 20px 24px 60px;
  }

  /* Header */
  header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 20px;
  }
  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
  h1 {
    font-size: 20px;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
  }
  .vault-badge {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 11px;
    color: var(--muted);
    font-family: ui-monospace, monospace;
    max-width: 400px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .nav-links {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 13px;
  }
  .nav-links a, .nav-links button {
    color: var(--muted);
    padding: 5px 9px;
    border-radius: 6px;
    transition: all 0.15s;
    text-decoration: none;
  }
  .nav-links a:hover, .nav-links button:hover {
    color: var(--text);
    background: var(--raise);
  }
  .theme-toggle-btn {
    background: var(--panel);
    border: 1px solid var(--border);
    cursor: pointer;
    font-size: 12px;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: inherit;
  }

  /* Stats row */
  .stats-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 20px;
  }
  .stat-pill {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 6px 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
    user-select: none;
  }
  .stat-pill:hover, .stat-pill.active {
    border-color: var(--accent);
    background: var(--raise);
  }
  .stat-pill .num {
    font-weight: 700;
    font-size: 14px;
  }
  .stat-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }
  .dot-ongoing { background: var(--up); box-shadow: 0 0 6px var(--up); }
  .dot-next { background: var(--warn); }
  .dot-untagged { background: var(--accent); }
  .dot-shelved { background: var(--purple); }
  .dot-rejected { background: var(--down); }

  /* Idea Bucket capture box */
  .bucket-box {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 24px;
    box-shadow: var(--shadow);
  }
  .bucket-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }
  .bucket-title {
    font-size: 15px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .bucket-desc {
    color: var(--muted);
    font-size: 12px;
  }
  .bucket-form {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .main-row {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
  }
  .input-title {
    flex: 1;
    min-width: 280px;
    background: var(--input-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 14px;
    color: var(--text);
    font-size: 14px;
    outline: none;
    transition: border-color 0.15s;
  }
  .input-title:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px rgba(9, 105, 218, 0.2);
  }
  .select-grid {
    display: contents; /* Inline siblings on desktop */
  }
  .select-custom {
    background: var(--input-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 12px;
    color: var(--text);
    font-size: 13px;
    outline: none;
    cursor: pointer;
  }
  .select-custom:focus {
    border-color: var(--accent);
  }
  .btn-primary {
    background: #1f883d;
    border: 1px solid rgba(31, 35, 40, 0.15);
    color: #fff;
    padding: 10px 18px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 13px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: background 0.15s;
    white-space: nowrap;
    touch-action: manipulation;
  }
  .btn-primary:hover { background: #1a7f37; }
  .btn-primary:active { transform: scale(0.98); }
  .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

  .bucket-options {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    font-size: 12px;
  }
  .status-radios {
    display: inline-flex;
    gap: 6px;
    align-items: center;
  }
  .status-chip {
    padding: 5px 12px;
    border-radius: 6px;
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--muted);
    cursor: pointer;
    user-select: none;
    font-size: 12px;
    transition: all 0.15s;
    touch-action: manipulation;
  }
  .status-chip.selected {
    border-color: var(--accent);
    color: var(--text);
    background: var(--raise);
    font-weight: 600;
  }
  .toggle-notes-btn {
    background: none;
    border: none;
    color: var(--accent);
    cursor: pointer;
    font-size: 12px;
    padding: 4px 0;
  }
  .notes-textarea {
    width: 100%;
    min-height: 80px;
    background: var(--input-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 12px;
    color: var(--text);
    font-family: inherit;
    font-size: 13px;
    resize: vertical;
    outline: none;
    display: none;
  }
  .notes-textarea:focus { border-color: var(--accent); }

  /* Controls & View Switcher Bar */
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    margin-bottom: 20px;
  }
  .view-switcher {
    display: inline-flex;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 3px;
    gap: 2px;
  }
  .view-btn {
    background: none;
    border: none;
    padding: 6px 14px;
    border-radius: 6px;
    color: var(--muted);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s;
    touch-action: manipulation;
  }
  .view-btn:hover { color: var(--text); }
  .view-btn.active {
    background: var(--raise);
    color: var(--text);
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }

  .filter-controls {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .search-box {
    position: relative;
    min-width: 220px;
  }
  .search-input {
    width: 100%;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 12px 6px 30px;
    color: var(--text);
    font-size: 13px;
    outline: none;
  }
  .search-input:focus { border-color: var(--accent); }
  .search-icon {
    position: absolute;
    left: 9px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--muted);
    font-size: 12px;
    pointer-events: none;
  }

  /* View Containers */
  .view-content {
    min-height: 400px;
  }

  /* KANBAN BOARD VIEW */
  .mobile-kanban-tabs {
    display: none;
  }
  .kanban-board {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 18px;
    align-items: flex-start;
  }
  .kanban-col {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    max-height: 85vh;
  }
  .kanban-col-header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-weight: 600;
    font-size: 14px;
  }
  .col-title {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .col-badge {
    background: var(--raise);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1px 8px;
    font-size: 11px;
    color: var(--muted);
    font-weight: 500;
  }
  .kanban-cards {
    padding: 12px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 120px;
    flex: 1;
  }

  /* Idea Card */
  .idea-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 14px;
    cursor: grab;
    transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s;
    position: relative;
    box-shadow: var(--card-shadow);
  }
  .idea-card:active { cursor: grabbing; }
  .idea-card:hover {
    border-color: var(--accent);
    box-shadow: var(--card-hover-shadow);
  }
  .idea-card.sortable-ghost {
    opacity: 0.4;
    background: var(--raise);
    border: 2px dashed var(--accent);
  }
  .card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 6px;
  }
  .cat-tag {
    font-size: 11px;
    font-weight: 500;
    background: var(--raise);
    color: var(--accent);
    padding: 2px 7px;
    border-radius: 4px;
    border: 1px solid rgba(9, 105, 218, 0.2);
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .file-tag {
    font-size: 10px;
    color: var(--muted);
    font-family: ui-monospace, monospace;
  }
  .card-title {
    font-size: 13px;
    font-weight: 600;
    line-height: 1.4;
    margin-bottom: 6px;
    word-break: break-word;
  }
  .card-title .check-box {
    margin-right: 6px;
    cursor: pointer;
  }
  .card-notes {
    font-size: 12px;
    color: var(--text);
    line-height: 1.45;
    background: var(--notes-bg);
    border-radius: 6px;
    padding: 8px 10px;
    margin-top: 8px;
    word-break: break-word;
    border-left: 2px solid var(--accent);
    max-height: 180px;
    overflow-y: auto;
  }
  .card-notes pre, .card-notes code {
    font-family: ui-monospace, monospace;
    font-size: 11px;
    background: var(--raise);
    padding: 2px 4px;
    border-radius: 3px;
  }
  .card-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 8px;
  }
  .tag-pill {
    font-size: 10px;
    color: var(--teal);
    background: rgba(14, 120, 134, 0.1);
    border: 1px solid rgba(14, 120, 134, 0.2);
    border-radius: 4px;
    padding: 1px 5px;
  }
  .card-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
    font-size: 11px;
  }
  .card-actions {
    display: flex;
    gap: 4px;
  }
  .btn-card {
    background: var(--raise);
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 11px;
    border-radius: 4px;
    padding: 3px 7px;
    cursor: pointer;
    transition: all 0.12s;
    touch-action: manipulation;
  }
  .btn-card:hover {
    color: var(--text);
    border-color: var(--muted);
    background: var(--raise-hover);
  }
  .btn-card.active {
    color: var(--text);
    border-color: var(--accent);
    background: var(--raise);
    font-weight: 600;
  }

  /* WATERFALL / MASONRY GRID VIEW */
  .waterfall-grid {
    margin: 0 auto;
  }
  .waterfall-item {
    width: calc(33.333% - 14px);
    margin-bottom: 18px;
    float: left;
  }
  @media (max-width: 1200px) {
    .waterfall-item { width: calc(50% - 12px); }
  }

  /* TABLE VIEW (Tabulator Container) */
  .table-container {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    overflow: hidden;
  }
  #tabulator-table {
    background: transparent;
    font-size: 13px;
  }
  .tabulator {
    background-color: var(--panel) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
  }
  .tabulator .tabulator-header {
    background-color: var(--raise) !important;
    border-bottom: 1px solid var(--border) !important;
    color: var(--muted) !important;
  }
  .tabulator .tabulator-row {
    background-color: var(--panel) !important;
    color: var(--text) !important;
    border-bottom: 1px solid var(--border) !important;
  }
  .tabulator .tabulator-row:hover {
    background-color: var(--raise-hover) !important;
  }
  .tabulator .tabulator-row.tabulator-group {
    background-color: var(--raise) !important;
    border-bottom: 1px solid var(--border) !important;
    color: var(--text) !important;
  }
  .tabulator .tabulator-footer {
    background-color: var(--raise) !important;
    border-top: 1px solid var(--border) !important;
    color: var(--muted) !important;
  }
  .tabulator .tabulator-footer .tabulator-page {
    background-color: var(--panel) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
  }

  /* Toast Notification */
  #toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: var(--panel);
    border: 1px solid var(--accent);
    color: var(--text);
    padding: 12px 18px;
    border-radius: 8px;
    box-shadow: var(--shadow);
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 10px;
    z-index: 2000;
    transform: translateY(100px);
    opacity: 0;
    transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    pointer-events: none;
  }
  #toast.show {
    transform: translateY(0);
    opacity: 1;
  }

  /* Modals */
  .modal-backdrop {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 2000;
    padding: 16px;
  }
  .modal-dialog {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    width: 100%;
    max-width: 560px;
    padding: 20px 24px;
    box-shadow: var(--shadow);
  }
  .modal-dialog h2 { margin-top: 0; font-size: 17px; }
  .modal-dialog textarea, .modal-dialog input {
    width: 100%;
    background: var(--input-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px;
    color: var(--text);
    font-size: 13px;
    margin-bottom: 12px;
  }
  .modal-buttons {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    margin-top: 16px;
  }
  .btn-secondary {
    background: var(--raise);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 14px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
  }
  .btn-danger {
    background: #cf222e;
    border: 1px solid rgba(31, 35, 40, 0.15);
    color: #fff;
    padding: 8px 14px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
  }

  .mobile-fab {
    display: none;
  }

  /* MOBILE SPECIFIC TUNING & OPTIMIZATION FOR DROPPING IDEAS */
  @media (max-width: 768px) {
    .wrap {
      padding: 12px 14px 80px;
    }
    header {
      flex-direction: column;
      align-items: flex-start;
      gap: 10px;
      padding-bottom: 12px;
      margin-bottom: 14px;
    }
    .header-left {
      width: 100%;
      justify-content: space-between;
    }
    h1 {
      font-size: 18px;
    }
    .vault-badge {
      font-size: 10px;
      max-width: 100%;
    }
    .nav-links {
      width: 100%;
      overflow-x: auto;
      padding-bottom: 4px;
      white-space: nowrap;
      -webkit-overflow-scrolling: touch;
    }
    .stats-bar {
      overflow-x: auto;
      flex-wrap: nowrap;
      padding-bottom: 6px;
      -webkit-overflow-scrolling: touch;
      margin-bottom: 14px;
    }
    .stat-pill {
      flex: none;
      white-space: nowrap;
    }

    /* Bucket Box on Mobile */
    .bucket-box {
      padding: 14px 16px;
      border-radius: 12px;
      margin-bottom: 18px;
      border: 1.5px solid var(--accent);
      background: var(--panel);
      box-shadow: 0 4px 14px rgba(9, 105, 218, 0.08);
    }
    .bucket-header {
      margin-bottom: 10px;
    }
    .bucket-title {
      font-size: 16px;
    }
    .bucket-desc {
      display: none; /* Keep clean and uncluttered */
    }
    .main-row {
      flex-direction: column;
      gap: 10px;
    }
    .input-title {
      min-width: unset;
      width: 100%;
      font-size: 16px !important; /* Prevents auto-zoom on iOS */
      padding: 12px 14px;
      border-radius: 8px;
    }
    .select-grid {
      display: grid !important;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      width: 100%;
    }
    .select-custom {
      width: 100%;
      padding: 10px 8px;
      font-size: 13px;
      border-radius: 8px;
    }
    .status-radios {
      width: 100%;
      justify-content: space-between;
      gap: 4px;
    }
    .status-chip {
      flex: 1;
      text-align: center;
      padding: 8px 4px;
      font-size: 11px;
    }
    .btn-primary {
      width: 100%;
      min-height: 48px;
      font-size: 16px;
      justify-content: center;
      border-radius: 8px;
      margin-top: 4px;
    }
    .bucket-options {
      flex-direction: column;
      align-items: flex-start;
      gap: 8px;
    }

    /* Toolbar on Mobile */
    .toolbar {
      flex-direction: column;
      align-items: stretch;
      gap: 10px;
      margin-bottom: 16px;
    }
    .view-switcher {
      width: 100%;
      display: flex;
    }
    .view-btn {
      flex: 1;
      justify-content: center;
      padding: 8px 6px;
      font-size: 12px;
    }
    .filter-controls {
      flex-direction: column;
      width: 100%;
    }
    .search-box {
      width: 100%;
    }
    .search-input {
      font-size: 14px;
      padding: 8px 12px 8px 30px;
    }
    .filter-controls select {
      width: 100%;
    }

    .waterfall-item {
      width: 100%;
    }

    /* Kanban on Mobile: Column Tabs */
    .mobile-kanban-tabs {
      display: flex !important;
      overflow-x: auto;
      gap: 6px;
      margin-bottom: 12px;
      padding-bottom: 4px;
      -webkit-overflow-scrolling: touch;
    }
    .mobile-col-tab {
      flex: 1;
      white-space: nowrap;
      text-align: center;
      padding: 8px 10px;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 12px;
      font-weight: 500;
      color: var(--muted);
      cursor: pointer;
      touch-action: manipulation;
    }
    .mobile-col-tab.active {
      background: var(--raise);
      color: var(--text);
      border-color: var(--accent);
      font-weight: 600;
    }
    .kanban-board.mobile-mode {
      display: flex;
      flex-direction: column;
      gap: 0;
    }
    .kanban-board.mobile-mode .kanban-col {
      display: none;
      width: 100%;
    }
    .kanban-board.mobile-mode .kanban-col.mobile-active {
      display: flex;
    }

    /* Floating Action Button (FAB) */
    .mobile-fab {
      display: flex !important;
      position: fixed;
      bottom: 20px;
      right: 20px;
      background: #1f883d;
      color: #fff;
      border: none;
      border-radius: 30px;
      padding: 12px 18px;
      font-size: 14px;
      font-weight: 600;
      box-shadow: 0 4px 16px rgba(0,0,0,0.25);
      z-index: 1500;
      cursor: pointer;
      align-items: center;
      gap: 6px;
      touch-action: manipulation;
      transition: transform 0.15s;
    }
    .mobile-fab:active {
      transform: scale(0.95);
    }

    #toast {
      top: 16px;
      bottom: auto;
      left: 16px;
      right: 16px;
      transform: translateY(-80px);
    }
    #toast.show {
      transform: translateY(0);
    }
  }
</style>
</head>
<body>

<div class="wrap">
  <!-- Header -->
  <header>
    <div class="header-left">
      <h1>💡 Idea Bucket &amp; Projects</h1>
      <span class="vault-badge" title="Obsidian Vault Path">__VAULT_PATH__</span>
    </div>
    <div class="nav-links">
      <a href="/">← Homelab Status</a>
      <a href="/claude-rc">Claude RC</a>
      <a href="/antigravity-rc">Antigravity RC</a>
      <a href="/tmux">tmux</a>
      <a href="#" id="refreshBtn" title="Reload from disk">↻ Sync</a>
      <button type="button" id="themeToggleBtn" class="theme-toggle-btn" onclick="toggleTheme();">🌙 Dark</button>
      __LOGOUT__
    </div>
  </header>

  <!-- Stats Pills -->
  <div class="stats-bar" id="statsBar">
    <div class="stat-pill active" data-filter="all">
      <span class="num" id="statTotal">0</span> Total Ideas
    </div>
    <div class="stat-pill" data-filter="ongoing">
      <span class="stat-dot dot-ongoing"></span>
      <span class="num" id="statOngoing">0</span> Ongoing
    </div>
    <div class="stat-pill" data-filter="next">
      <span class="stat-dot dot-next"></span>
      <span class="num" id="statNext">0</span> Next Up
    </div>
    <div class="stat-pill" data-filter="untagged">
      <span class="stat-dot dot-untagged"></span>
      <span class="num" id="statUntagged">0</span> Untagged Backlog
    </div>
    <div class="stat-pill" data-filter="rejected">
      <span class="stat-dot dot-rejected"></span>
      <span class="num" id="statRejected">0</span> Shelved &amp; Rejected
    </div>
  </div>

  <!-- Idea Bucket Capture Area -->
  <section class="bucket-box" id="bucketBox">
    <div class="bucket-header">
      <div class="bucket-title">
        <span>⚡ Quick Idea Bucket</span>
      </div>
      <span class="bucket-desc">Dumps directly into Obsidian notes &amp; syncs automatically</span>
    </div>
    <form class="bucket-form" id="bucketForm" onsubmit="return handleAddIdea(event);">
      <div class="main-row">
        <input type="text" id="ideaTitle" class="input-title" placeholder="Drop an idea concept into the bucket... (e.g., 'Autonomous PR test triager')" required autocomplete="off">
        
        <div class="select-grid">
          <select id="ideaFile" class="select-custom" onchange="populateCategoryOptions();" title="Target Obsidian Note">
            <option value="2 - Money making.md" selected>2 - Money making.md</option>
            <option value="3 - FOSS projects.md">3 - FOSS projects.md</option>
          </select>

          <select id="ideaCategory" class="select-custom" title="Category Section">
            <!-- Populated dynamically -->
          </select>
        </div>

        <button type="submit" class="btn-primary" id="btnSubmitIdea">
          <span>➕ Drop in Bucket</span>
        </button>
      </div>

      <div class="bucket-options">
        <div class="status-radios" id="statusRadios">
          <span style="color:var(--muted); margin-right:4px;">Status:</span>
          <span class="status-chip selected" data-status="untagged">Untagged</span>
          <span class="status-chip" data-status="next">#board/next</span>
          <span class="status-chip" data-status="ongoing">[ONGOING]</span>
        </div>

        <button type="button" class="toggle-notes-btn" onclick="toggleNotesInput();" id="toggleNotesBtn">
          + Add Details / Notes / Links
        </button>
      </div>

      <textarea id="ideaNotes" class="notes-textarea" placeholder="Optional notes, customer pain point, tech stack, or links (indented markdown bullet items under this idea)..."></textarea>
    </form>
  </section>

  <!-- Controls & Switcher Toolbar -->
  <div class="toolbar">
    <div class="view-switcher" id="viewSwitcher">
      <button class="view-btn active" data-view="kanban" onclick="switchView('kanban');">
        📋 Kanban Board
      </button>
      <button class="view-btn" data-view="waterfall" onclick="switchView('waterfall');">
        🌊 Waterfall Grid
      </button>
      <button class="view-btn" data-view="table" onclick="switchView('table');">
        📊 Table View
      </button>
    </div>

    <div class="filter-controls">
      <div class="search-box">
        <span class="search-icon">🔍</span>
        <input type="text" id="searchInput" class="search-input" placeholder="Filter ideas... (/)" oninput="handleSearch();">
      </div>

      <select id="filterCategory" class="select-custom" onchange="handleCategoryFilter();" style="padding:6px 10px; font-size:12px;">
        <option value="all">All Categories</option>
      </select>

      <select id="filterFile" class="select-custom" onchange="handleFileFilter();" style="padding:6px 10px; font-size:12px;">
        <option value="all">All Files</option>
        <option value="2 - Money making.md">2 - Money making.md</option>
        <option value="3 - FOSS projects.md">3 - FOSS projects.md</option>
        <option value="rejected/rejected.md">rejected.md</option>
      </select>

      <button type="button" id="toggleRejectedBtn" class="btn-card" onclick="toggleShowRejected();"
              style="padding:6px 10px; font-size:12px;" title="Show or hide shelved &amp; rejected ideas">
        👁 Show Rejected (0)
      </button>
    </div>
  </div>

  <!-- Dynamic Views Content -->
  <main class="view-content" id="viewContent">
    <!-- View will be rendered here -->
  </main>
</div>

<!-- Floating Action Button for Mobile -->
<button type="button" id="mobileFab" class="mobile-fab" onclick="scrollToBucket();" title="Quick Drop an Idea">
  <span>⚡ Drop Idea</span>
</button>

<!-- Rejection Dossier Modal -->
<div id="rejectModal" class="modal-backdrop" style="display:none;">
  <div class="modal-dialog">
    <h2 id="rejectModalTitle">Move to Rejected Dossier</h2>
    <p style="color:var(--muted); font-size:13px; margin-bottom:12px;">
      As required by doctrine, rejected projects are archived in <code>rejected/rejected.md</code> with an economic/viability dossier.
    </p>
    <label style="font-size:12px; color:var(--muted); display:block; margin-bottom:4px;">Rejection Rationale / Economic Kill Condition:</label>
    <textarea id="rejectReasonInput" rows="4" placeholder="Explain why this fails (e.g. fails SO-4 capital ceiling, legal EU compliance, empty batch economics)..."></textarea>
    
    <div class="modal-buttons">
      <button type="button" class="btn-secondary" onclick="closeRejectModal();">Cancel</button>
      <button type="button" class="btn-danger" id="confirmRejectBtn">Archive as Rejected</button>
    </div>
  </div>
</div>

<!-- Toast notification banner -->
<div id="toast">
  <span id="toastIcon">✓</span>
  <span id="toastMessage">Idea captured</span>
</div>

<script>
let allIdeas = [];
let allCategories = {};
let currentView = localStorage.getItem("idea_view") || "kanban";
let currentTheme = localStorage.getItem("idea_theme") || "light"; // LIGHT BY DEFAULT
let currentStatusFilter = "all";
let currentCategoryFilter = "all";
let currentFileFilter = "all";
let currentSearch = "";
let selectedBucketStatus = "untagged";
let currentMobileCol = "untagged";
// Rejected & shelved ideas are hidden everywhere until this toggle is turned on.
let showRejected = localStorage.getItem("idea_show_rejected") === "1";

let masonryInstance = null;
let tabulatorInstance = null;
let sortableInstances = [];

// Apply theme (Light is default)
function applyTheme(theme) {
  currentTheme = theme;
  localStorage.setItem("idea_theme", theme);
  const btn = document.getElementById("themeToggleBtn");
  if (theme === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
    if (btn) btn.textContent = "☀️ Light";
  } else {
    document.documentElement.removeAttribute("data-theme");
    if (btn) btn.textContent = "🌙 Dark";
  }
}

function toggleTheme() {
  applyTheme(currentTheme === "light" ? "dark" : "light");
}

// Initial theme application
applyTheme(currentTheme);

function scrollToBucket() {
  const box = document.getElementById("bucketBox");
  const input = document.getElementById("ideaTitle");
  if (box) box.scrollIntoView({ behavior: "smooth", block: "start" });
  if (input) setTimeout(() => input.focus(), 350);
}

// Wikilink converter for Obsidian format [[note|display]]
function renderWikilinks(text) {
  if (!text) return "";
  return text.replace(/\\[\\[([^\\]|]+)(?:\\|([^\\]]+))?\\]\\]/g, (match, note, title) => {
    const label = title || note;
    return `<span class="vault-badge" title="Obsidian link: ${note}">📄 ${label}</span>`;
  });
}

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function showToast(msg, isError = false) {
  const t = document.getElementById("toast");
  document.getElementById("toastMessage").textContent = msg;
  document.getElementById("toastIcon").textContent = isError ? "⚠️" : "✓";
  t.style.borderColor = isError ? "var(--down)" : "var(--accent)";
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 3500);
}

// Status selection chips
document.querySelectorAll("#statusRadios .status-chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.querySelectorAll("#statusRadios .status-chip").forEach(c => c.classList.remove("selected"));
    chip.classList.add("selected");
    selectedBucketStatus = chip.dataset.status;
  });
});

// An idea counts as rejected if it is tagged rejected/shelved or lives in the dossier file.
function isRejectedIdea(item) {
  return item.status === "rejected"
      || item.status === "shelved"
      || item.file === "rejected/rejected.md";
}

function rejectedCount() {
  return allIdeas.filter(isRejectedIdea).length;
}

function refreshRejectedToggleBtn() {
  const btn = document.getElementById("toggleRejectedBtn");
  if (!btn) return;
  const n = rejectedCount();
  btn.classList.toggle("active", showRejected);
  btn.textContent = (showRejected ? "🙈 Hide Rejected (" : "👁 Show Rejected (") + n + ")";
  btn.title = showRejected
    ? "Hide shelved & rejected ideas again"
    : "Shelved & rejected ideas are hidden - click to reveal them";
}

function setShowRejected(on) {
  showRejected = !!on;
  localStorage.setItem("idea_show_rejected", showRejected ? "1" : "0");
  refreshRejectedToggleBtn();
}

function toggleShowRejected() {
  setShowRejected(!showRejected);
  if (!showRejected) {
    // Do not leave the page filtered on a bucket that is now hidden.
    if (currentStatusFilter === "rejected") setStatusFilter("all");
    if (currentFileFilter === "rejected/rejected.md") {
      currentFileFilter = "all";
      const sel = document.getElementById("filterFile");
      if (sel) sel.value = "all";
    }
    if (currentMobileCol === "rejected") currentMobileCol = "untagged";
  }
  updateStats();
  renderCurrentView();
}

function setStatusFilter(filter) {
  currentStatusFilter = filter;
  document.querySelectorAll(".stat-pill").forEach(p => {
    p.classList.toggle("active", p.dataset.filter === filter);
  });
}

// Stats pill clicking
document.querySelectorAll(".stat-pill").forEach(pill => {
  pill.addEventListener("click", () => {
    setStatusFilter(pill.dataset.filter);
    // Asking for the rejected bucket implies you want to see it.
    if (currentStatusFilter === "rejected" && !showRejected) setShowRejected(true);
    updateStats();
    renderCurrentView();
  });
});

function toggleNotesInput() {
  const el = document.getElementById("ideaNotes");
  const btn = document.getElementById("toggleNotesBtn");
  if (el.style.display === "block") {
    el.style.display = "none";
    btn.textContent = "+ Add Details / Notes / Links";
  } else {
    el.style.display = "block";
    btn.textContent = "- Hide Notes / Details";
    el.focus();
  }
}

// Keyboard shortcuts
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    const active = document.activeElement;
    if (active && (active.id === "ideaTitle" || active.id === "ideaNotes")) {
      e.preventDefault();
      document.getElementById("bucketForm").requestSubmit();
    }
  } else if (e.key === "/" && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") {
    e.preventDefault();
    document.getElementById("searchInput").focus();
  } else if (e.key === "Escape") {
    closeRejectModal();
  }
});

async function loadData() {
  try {
    const res = await fetch("/api/ideas", { cache: "no-store" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.message || "Failed loading ideas");

    allIdeas = data.ideas || [];
    allCategories = data.categories || {};
    if (!showRejected && currentStatusFilter === "rejected") setStatusFilter("all");
    updateStats();
    populateCategoryOptions();
    populateFilterCategories();
    renderCurrentView();
  } catch (err) {
    showToast("Error: " + err.message, true);
  }
}

// Counts are computed from what the page is actually willing to show, so the
// pills never advertise ideas the rejected toggle is currently hiding.
function updateStats() {
  const visible = allIdeas.filter(i => showRejected || !isRejectedIdea(i));
  const countBy = st => visible.filter(i => i.status === st).length;

  document.getElementById("statTotal").textContent = visible.length;
  document.getElementById("statOngoing").textContent = countBy("ongoing");
  document.getElementById("statNext").textContent = countBy("next");
  document.getElementById("statUntagged").textContent = countBy("untagged");

  const rejPill = document.querySelector('.stat-pill[data-filter="rejected"]');
  document.getElementById("statRejected").textContent = showRejected ? rejectedCount() : 0;
  if (rejPill) {
    rejPill.style.opacity = showRejected ? "" : "0.55";
    rejPill.title = showRejected
      ? "Shelved & rejected ideas"
      : rejectedCount() + " shelved & rejected ideas are hidden - click to show them";
  }
  refreshRejectedToggleBtn();
}

function populateCategoryOptions() {
  const file = document.getElementById("ideaFile").value;
  const select = document.getElementById("ideaCategory");
  select.innerHTML = "";

  const cats = allCategories[file] || [];
  if (cats.length === 0) {
    const opt = document.createElement("option");
    opt.value = "Next up";
    opt.textContent = "Next up";
    select.appendChild(opt);
  } else {
    cats.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      select.appendChild(opt);
    });
  }
}

function populateFilterCategories() {
  const select = document.getElementById("filterCategory");
  const prev = select.value;
  select.innerHTML = '<option value="all">All Categories</option>';

  const set = new Set();
  allIdeas.forEach(i => { if (i.category) set.add(i.category); });
  Array.from(set).sort().forEach(c => {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    select.appendChild(opt);
  });
  if (set.has(prev)) select.value = prev;
}

function handleSearch() {
  currentSearch = document.getElementById("searchInput").value.trim().toLowerCase();
  renderCurrentView();
}
function handleCategoryFilter() {
  currentCategoryFilter = document.getElementById("filterCategory").value;
  renderCurrentView();
}
function handleFileFilter() {
  currentFileFilter = document.getElementById("filterFile").value;
  // Picking the dossier file explicitly implies you want to see its contents.
  if (currentFileFilter === "rejected/rejected.md" && !showRejected) setShowRejected(true);
  updateStats();
  renderCurrentView();
}

function getFilteredIdeas() {
  return allIdeas.filter(item => {
    // Rejected & shelved ideas stay out of every view until the toggle is on.
    if (!showRejected && isRejectedIdea(item)) return false;
    // Status filter
    if (currentStatusFilter !== "all") {
      if (currentStatusFilter === "rejected") {
        if (item.status !== "rejected" && item.status !== "shelved") return false;
      } else if (item.status !== currentStatusFilter) {
        return false;
      }
    }
    // File filter
    if (currentFileFilter !== "all" && item.file !== currentFileFilter) return false;
    // Category filter
    if (currentCategoryFilter !== "all" && item.category !== currentCategoryFilter) return false;
    // Search
    if (currentSearch) {
      const q = currentSearch;
      const mTitle = item.title.toLowerCase().includes(q);
      const mCat = item.category.toLowerCase().includes(q);
      const mNotes = (item.notes || "").toLowerCase().includes(q);
      const mTags = (item.tags || []).some(t => t.toLowerCase().includes(q));
      if (!mTitle && !mCat && !mNotes && !mTags) return false;
    }
    return true;
  });
}

function switchView(viewName) {
  currentView = viewName;
  localStorage.setItem("idea_view", viewName);
  document.querySelectorAll("#viewSwitcher .view-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.view === viewName);
  });
  renderCurrentView();
}

function renderCurrentView() {
  destroyInstances();
  const container = document.getElementById("viewContent");
  const filtered = getFilteredIdeas();

  if (currentView === "kanban") {
    renderKanban(container, filtered);
  } else if (currentView === "waterfall") {
    renderWaterfall(container, filtered);
  } else if (currentView === "table") {
    renderTable(container, filtered);
  }
}

function destroyInstances() {
  sortableInstances.forEach(s => s.destroy());
  sortableInstances = [];
  if (masonryInstance) {
    masonryInstance.destroy();
    masonryInstance = null;
  }
  if (tabulatorInstance) {
    tabulatorInstance.destroy();
    tabulatorInstance = null;
  }
}

// Render Card HTML
function createCardHtml(item) {
  let notesHtml = "";
  if (item.notes) {
    const parsedNotes = typeof marked !== "undefined" ? marked.parse(item.notes) : escapeHtml(item.notes);
    notesHtml = `<div class="card-notes">${renderWikilinks(parsedNotes)}</div>`;
  }

  const tagsHtml = (item.tags || []).map(t => `<span class="tag-pill">#${escapeHtml(t)}</span>`).join("");
  const titleDisplay = renderWikilinks(escapeHtml(item.title));
  const isChecked = item.checked ? "checked" : "";

  return `
    <div class="idea-card" data-id="${item.id}" data-file="${item.file}">
      <div class="card-top">
        <span class="cat-tag" title="Category: ${escapeHtml(item.category)}">${escapeHtml(item.category)}</span>
        <span class="file-tag">${escapeHtml(item.file.replace('.md',''))}</span>
      </div>
      <div class="card-title">
        <input type="checkbox" class="check-box" ${isChecked} onchange="toggleCheck('${item.id}');" title="Toggle checkbox">
        <span>${titleDisplay}</span>
      </div>
      ${notesHtml}
      ${tagsHtml ? `<div class="card-tags">${tagsHtml}</div>` : ""}
      <div class="card-footer">
        <span style="color:var(--muted)">#${item.id}</span>
        <div class="card-actions">
          ${item.status !== "ongoing" ? `<button class="btn-card" onclick="quickStatus('${item.id}', 'ongoing');" title="Move to Ongoing">Ongoing</button>` : ""}
          ${item.status !== "next" ? `<button class="btn-card" onclick="quickStatus('${item.id}', 'next');" title="Move to Next">Next</button>` : ""}
          ${item.status !== "untagged" ? `<button class="btn-card" onclick="quickStatus('${item.id}', 'untagged');" title="Move to Untagged">Untag</button>` : ""}
          ${item.status !== "rejected" ? `<button class="btn-card" onclick="openRejectModal('${item.id}', '${escapeHtml(item.title)}');" title="Move to Rejected Dossier">Reject</button>` : ""}
        </div>
      </div>
    </div>
  `;
}

window.switchMobileCol = function(colId) {
  currentMobileCol = colId;
  document.querySelectorAll(".mobile-col-tab").forEach(tab => {
    tab.classList.toggle("active", tab.dataset.col === colId);
  });
  document.querySelectorAll(".kanban-board .kanban-col").forEach(col => {
    col.classList.toggle("mobile-active", col.dataset.col === colId);
  });
};

// 1. KANBAN BOARD VIEW
function renderKanban(container, items) {
  const columns = [
    { id: "untagged", title: "Untagged Backlog", dot: "dot-untagged", short: "Untagged" },
    { id: "next", title: "Next Up (#board/next)", dot: "dot-next", short: "Next" },
    { id: "ongoing", title: "Ongoing (#board/ongoing)", dot: "dot-ongoing", short: "Ongoing" },
  ];
  // The rejected column only exists while the toggle is on.
  if (showRejected) {
    columns.push({ id: "rejected", title: "Shelved &amp; Rejected", dot: "dot-rejected", short: "Rejected" });
  }

  const colGroups = { untagged: [], next: [], ongoing: [], rejected: [] };
  items.forEach(i => {
    if (isRejectedIdea(i)) {
      colGroups.rejected.push(i);
    } else if (colGroups[i.status]) {
      colGroups[i.status].push(i);
    } else {
      colGroups.untagged.push(i);
    }
  });

  if (!columns.some(c => c.id === currentMobileCol)) currentMobileCol = "untagged";

  // Mobile column tabs switcher
  let tabsHtml = `<div class="mobile-kanban-tabs">`;
  columns.forEach(col => {
    const colItems = colGroups[col.id];
    const active = col.id === currentMobileCol ? " active" : "";
    tabsHtml += `
      <button type="button" class="mobile-col-tab${active}" data-col="${col.id}" onclick="switchMobileCol('${col.id}');">
        <span class="stat-dot ${col.dot}"></span>
        <span>${col.short} (${colItems.length})</span>
      </button>
    `;
  });
  tabsHtml += `</div>`;

  let html = tabsHtml + `<div class="kanban-board mobile-mode">`;
  columns.forEach(col => {
    const colItems = colGroups[col.id];
    const mobileActive = col.id === currentMobileCol ? " mobile-active" : "";
    html += `
      <div class="kanban-col${mobileActive}" data-col="${col.id}">
        <div class="kanban-col-header">
          <div class="col-title">
            <span class="stat-dot ${col.dot}"></span>
            <span>${col.title}</span>
          </div>
          <span class="col-badge">${colItems.length}</span>
        </div>
        <div class="kanban-cards" id="col-${col.id}" data-status="${col.id}">
          ${colItems.map(createCardHtml).join("")}
        </div>
      </div>
    `;
  });
  html += `</div>`;
  container.innerHTML = html;

  // Initialize SortableJS drag and drop
  if (typeof Sortable !== "undefined") {
    columns.forEach(col => {
      const el = document.getElementById("col-" + col.id);
      if (!el) return;
      const s = new Sortable(el, {
        group: "ideas-kanban",
        animation: 150,
        ghostClass: "sortable-ghost",
        onEnd: async function(evt) {
          const itemEl = evt.item;
          const targetCol = evt.to;
          const newStatus = targetCol.dataset.status;
          const ideaId = itemEl.dataset.id;
          if (evt.from !== evt.to) {
            await quickStatus(ideaId, newStatus);
          }
        }
      });
      sortableInstances.push(s);
    });
  }
}

// 2. WATERFALL / MASONRY VIEW
function renderWaterfall(container, items) {
  let html = `<div class="waterfall-grid" id="waterfallContainer">`;
  items.forEach(item => {
    html += `
      <div class="waterfall-item">
        ${createCardHtml(item)}
      </div>
    `;
  });
  html += `</div><div style="clear:both;"></div>`;
  container.innerHTML = html;

  if (typeof Masonry !== "undefined") {
    const grid = document.getElementById("waterfallContainer");
    setTimeout(() => {
      masonryInstance = new Masonry(grid, {
        itemSelector: ".waterfall-item",
        columnWidth: ".waterfall-item",
        percentPosition: true,
        gutter: 14,
      });
    }, 50);
  }
}

// 3. TABLE VIEW (TABULATOR)
function renderTable(container, items) {
  container.innerHTML = `<div class="table-container"><div id="tabulator-table"></div></div>`;

  if (typeof Tabulator === "undefined") {
    container.innerHTML = "<p>Tabulator library loading failed</p>";
    return;
  }

  const tableData = items.map(i => ({
    id: i.id,
    checked: i.checked,
    status: i.status,
    title: i.title,
    category: i.category,
    file: i.file,
    notes: i.notes,
    tags: (i.tags || []).join(", "),
  }));

  tabulatorInstance = new Tabulator("#tabulator-table", {
    data: tableData,
    layout: "fitColumns",
    responsiveLayout: "collapse",
    pagination: "local",
    paginationSize: 25,
    groupBy: "category",
    groupHeader: function(value, count) {
      return `<span style="color:var(--accent); font-weight:600;">${value}</span> <span style="color:var(--muted); font-size:11px;">(${count} ideas)</span>`;
    },
    columns: [
      {
        title: "✓",
        field: "checked",
        width: 45,
        hozAlign: "center",
        formatter: "tickCross",
        cellClick: function(e, cell) {
          const row = cell.getRow().getData();
          toggleCheck(row.id);
        }
      },
      {
        title: "Status",
        field: "status",
        width: 110,
        formatter: function(cell) {
          const val = cell.getValue();
          let color = "var(--muted)";
          if (val === "ongoing") color = "var(--up)";
          else if (val === "next") color = "var(--warn)";
          else if (val === "untagged") color = "var(--accent)";
          else if (val === "rejected" || val === "shelved") color = "var(--down)";
          return `<span style="font-weight:600; color:${color}; text-transform:uppercase; font-size:11px;">${val}</span>`;
        }
      },
      {
        title: "Idea Concept",
        field: "title",
        formatter: function(cell) {
          return `<b>${escapeHtml(cell.getValue())}</b>`;
        }
      },
      { title: "Category", field: "category", width: 160 },
      { title: "Note File", field: "file", width: 140 },
      { title: "Tags", field: "tags", width: 120 },
      {
        title: "Actions",
        width: 140,
        formatter: function() {
          return `<button class="btn-card">Quick Status ▾</button>`;
        },
        cellClick: function(e, cell) {
          const row = cell.getRow().getData();
          const target = prompt("Set status: untagged, next, ongoing, or rejected:", row.status);
          if (target && target !== row.status) {
            quickStatus(row.id, target.trim().toLowerCase());
          }
        }
      }
    ]
  });
}

// Action Handlers
async function handleAddIdea(e) {
  e.preventDefault();
  const btn = document.getElementById("btnSubmitIdea");
  btn.disabled = true;

  const title = document.getElementById("ideaTitle").value.trim();
  const file = document.getElementById("ideaFile").value;
  const category = document.getElementById("ideaCategory").value || "Next up";
  const notes = document.getElementById("ideaNotes").value.trim();
  const status = selectedBucketStatus;

  try {
    const res = await fetch("/api/ideas/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, target_file: file, category, notes, status }),
    });
    const result = await res.json();
    if (!result.ok) throw new Error(result.message || "Failed to add idea");

    showToast(`✓ Dropped into '${file}' [${category}]!`);
    const titleInput = document.getElementById("ideaTitle");
    titleInput.value = "";
    document.getElementById("ideaNotes").value = "";
    titleInput.focus();
    await loadData();
  } catch (err) {
    showToast("Error adding idea: " + err.message, true);
  } finally {
    btn.disabled = false;
  }
  return false;
}

async function quickStatus(ideaId, newStatus) {
  try {
    const res = await fetch("/api/ideas/update-status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: ideaId, status: newStatus }),
    });
    const result = await res.json();
    if (!result.ok) throw new Error(result.message || "Failed to update status");

    showToast(`✓ Updated status to ${newStatus}`);
    await loadData();
  } catch (err) {
    showToast("Error updating status: " + err.message, true);
  }
}

async function toggleCheck(ideaId) {
  try {
    const res = await fetch("/api/ideas/toggle-check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: ideaId }),
    });
    const result = await res.json();
    if (!result.ok) throw new Error(result.message);
    const item = allIdeas.find(i => i.id === ideaId);
    if (item) item.checked = result.checked;
  } catch (err) {
    showToast("Error toggling checkbox: " + err.message, true);
  }
}

let pendingRejectId = null;
function openRejectModal(id, title) {
  pendingRejectId = id;
  document.getElementById("rejectModalTitle").textContent = `Archive '${title}' to Rejected Dossier`;
  document.getElementById("rejectReasonInput").value = "";
  document.getElementById("rejectModal").style.display = "flex";
  document.getElementById("rejectReasonInput").focus();
}

function closeRejectModal() {
  pendingRejectId = null;
  document.getElementById("rejectModal").style.display = "none";
}

document.getElementById("confirmRejectBtn").addEventListener("click", async () => {
  if (!pendingRejectId) return;
  const rejectId = pendingRejectId;
  const reason = document.getElementById("rejectReasonInput").value.trim();
  closeRejectModal();

  try {
    const res = await fetch("/api/ideas/update-status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: rejectId, status: "rejected", reason }),
    });
    const result = await res.json();
    if (!result.ok) throw new Error(result.message);
    showToast("✓ Moved to rejected/rejected.md dossier");
    await loadData();
  } catch (err) {
    showToast("Error moving to rejected: " + err.message, true);
  }
});

document.getElementById("refreshBtn").addEventListener("click", (e) => {
  e.preventDefault();
  loadData();
  showToast("Vault synchronized with disk");
});

// Initial boot
refreshRejectedToggleBtn();
loadData();
</script>
</body>
</html>
"""
