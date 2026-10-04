"""HTML template and frontend client for the Idea Bucket Kanban dashboard."""

IDEAS_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=5">
<title>Idea Bucket &amp; Projects · __TITLE__</title>
<!-- Libraries via CDN: SortableJS (Kanban Drag & Drop), Marked (Obsidian Markdown) -->
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js"></script>
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

  /* Embedded mode inside cockpit */
  body.embedded header { display: none !important; }
  body.embedded .wrap { padding: 10px 16px 30px !important; max-width: 100% !important; width: 100% !important; }

  /* Project Subtabs */
  .project-subtabs-bar {
    display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; align-items: center;
  }
  .subtab-btn {
    display: inline-flex; align-items: center; gap: 6px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 999px; padding: 5px 14px; font-size: 13px;
    color: var(--muted); cursor: pointer; font-family: inherit; font-weight: 500;
    transition: all 0.15s ease;
  }
  .subtab-btn:hover { color: var(--text); background: var(--raise); border-color: var(--muted); }
  .subtab-btn.active { color: var(--accent); background: var(--raise); border-color: var(--accent); font-weight: 600; box-shadow: 0 0 0 1px var(--accent); }

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
  .bucket-modal .bucket-box {
    width: 100%;
    max-width: 760px;
    max-height: 90vh;
    overflow-y: auto;
    margin: 0;
  }
  .bucket-close {
    background: none;
    border: none;
    color: var(--muted);
    font-size: 20px;
    line-height: 1;
    cursor: pointer;
    padding: 0 4px;
  }
  .bucket-close:hover { color: var(--text); }
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
  .filter-controls {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
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
    .filter-controls {
      flex-direction: column;
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
  /* Labels (orthogonal to the status column) */
  .tag-pill.tag-owned {
    color: #fff;
    background: #b7791f;
    border-color: #975a16;
    font-weight: 700;
    letter-spacing: 0.03em;
  }
  .tag-pill.tag-challenged {
    color: #fff;
    background: #dd6b20;
    border-color: #c05621;
    font-weight: 700;
    letter-spacing: 0.03em;
    animation: challenge-pulse 1.8s ease-in-out infinite;
  }
  .tag-pill.tag-answered {
    color: #fff;
    background: var(--up);
    border-color: var(--up);
    font-weight: 700;
    letter-spacing: 0.03em;
  }
  @keyframes challenge-pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(221, 107, 32, 0.55); }
    50% { box-shadow: 0 0 0 4px rgba(221, 107, 32, 0); }
  }
  @media (prefers-reduced-motion: reduce) {
    .tag-pill.tag-challenged { animation: none; }
  }
  .card-tags { margin-top: 0; margin-bottom: 6px; }

  /* Obsidian callouts (> [!info]- Title) folded into <details> */
  .idea-callout {
    margin-top: 8px;
    background: var(--notes-bg);
    border-left: 3px solid #3b82f6;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
    line-height: 1.45;
  }
  .idea-callout summary {
    cursor: pointer;
    font-weight: 600;
    color: var(--accent);
    user-select: none;
  }
  .idea-callout[open] summary { margin-bottom: 6px; }
  .idea-callout-body { max-height: 320px; overflow-y: auto; word-break: break-word; }
  .idea-callout-body ul { padding-left: 18px; margin: 4px 0; }
  .idea-callout-body p { margin: 4px 0; }

  /* Challenge / Feasibility answer audit trail */
  .audit-trail { margin-top: 8px; display: flex; flex-direction: column; gap: 6px; }
  .audit-entry {
    font-size: 12px;
    line-height: 1.45;
    border-radius: 6px;
    padding: 6px 10px;
    border: 1px solid var(--border);
    background: var(--notes-bg);
    word-break: break-word;
  }
  .audit-entry p { margin: 2px 0; }
  .audit-head { font-size: 11px; font-weight: 600; color: var(--muted); margin-bottom: 2px; }
  .audit-challenge { border-left: 3px solid #dd6b20; }
  .audit-answer { border-left: 3px solid var(--muted); }
  .audit-answer.audit-accepted { border-left-color: var(--up); }
  .audit-answer.audit-upheld { border-left-color: var(--down); }
  .verdict { text-transform: uppercase; font-weight: 700; }
  .audit-accepted .verdict { color: var(--up); }
  .audit-upheld .verdict { color: var(--down); }

  .card-actions { flex-wrap: wrap; justify-content: flex-end; }
  .btn-card.btn-challenge { color: #dd6b20; border-color: rgba(221, 107, 32, 0.5); }
  .btn-card.btn-challenge:hover { background: rgba(221, 107, 32, 0.1); color: #dd6b20; }
  .challenge-reason {
    font-size: 12px;
    line-height: 1.45;
    background: var(--notes-bg);
    border-left: 3px solid var(--down);
    border-radius: 4px;
    padding: 8px 10px;
    margin-bottom: 12px;
    max-height: 140px;
    overflow-y: auto;
    word-break: break-word;
  }
  .challenge-reason p { margin: 0; }
  .modal-label { font-size: 12px; color: var(--muted); display: block; margin-bottom: 4px; }
  .owned-toggle { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; color: var(--muted); }
  .owned-toggle input { margin: 0; }
  .input-labels {
    background: var(--input-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 5px 8px;
    color: var(--text);
    font-size: 12px;
    width: 180px;
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

  <!-- Idea Bucket Capture popup, opened by the "New idea" button -->
  <div id="bucketModal" class="modal-backdrop bucket-modal" style="display:none;">
  <section class="bucket-box" id="bucketBox" role="dialog" aria-modal="true" aria-labelledby="bucketTitle">
    <div class="bucket-header">
      <div class="bucket-title">
        <span id="bucketTitle">⚡ Quick Idea Bucket</span>
      </div>
      <span class="bucket-desc">Dumps directly into Obsidian notes &amp; syncs automatically</span>
      <button type="button" class="bucket-close" onclick="closeBucketModal();" title="Close (Esc)" aria-label="Close">×</button>
    </div>
    <form class="bucket-form" id="bucketForm" onsubmit="return handleAddIdea(event);">
      <div class="main-row">
        <input type="text" id="ideaTitle" class="input-title" placeholder="Drop an idea concept into the bucket... (e.g., 'Autonomous PR test triager')" required autocomplete="off">
        
        <div class="select-grid">
          <select id="ideaFile" class="select-custom" onchange="populateCategoryOptions();" title="Target Obsidian Note">
            <option value="Money making.md" selected>Money making.md</option>
            <option value="FOSS projects.md">FOSS projects.md</option>
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
          <span class="status-chip" data-status="next">#status/next</span>
          <span class="status-chip" data-status="ongoing">#status/ongoing</span>
        </div>

        <label class="owned-toggle" title="Founder mandate: the Idea Feasibility Agent skips viability kill gates and goes straight to design (#owned)">
          <input type="checkbox" id="ideaOwned"> 🔒 Owned / no auto-eval
        </label>
        <input type="text" id="ideaTags" class="input-labels" placeholder="Labels: #saas #hardware" autocomplete="off" title="Labels, separated by spaces or commas">

        <button type="button" class="toggle-notes-btn" onclick="toggleNotesInput();" id="toggleNotesBtn">
          + Add Details / Notes / Links
        </button>
      </div>

      <textarea id="ideaNotes" class="notes-textarea" placeholder="Optional notes, customer pain point, tech stack, or links (indented markdown bullet items under this idea)..."></textarea>
    </form>
  </section>
  </div>

  <!-- Project Boards Subtabs -->
  <div class="project-subtabs-bar" id="projectSubtabsBar">
    <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 600; margin-right: 4px;">Project Boards:</span>
    <div id="projectSubtabs" style="display: flex; gap: 6px; flex-wrap: wrap;"></div>
  </div>

  <!-- Controls & Switcher Toolbar -->
  <div class="toolbar">
    <button type="button" class="btn-primary" id="openBucketBtn" onclick="openBucketModal();" title="Drop a new idea (n)">
      <span>💡 New idea</span>
    </button>

    <div class="filter-controls">

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


<!-- Reject Modal -->
<div id="rejectModal" class="modal-backdrop" style="display:none;">
  <div class="modal-dialog">
    <h2 id="rejectModalTitle">Reject idea</h2>
    <p style="color:var(--muted); font-size:13px; margin-bottom:12px;">
      The card gets <code>#status/rejected</code> and your reason as a note. It stays on its board until <code>ideas_manager.py archive</code> moves it to <code>&lt;board&gt; [REJECTED].md</code>.
    </p>
    <label style="font-size:12px; color:var(--muted); display:block; margin-bottom:4px;">Rejection Rationale / Economic Kill Condition:</label>
    <textarea id="rejectReasonInput" rows="4" placeholder="Explain why this fails (e.g. fails SO-4 capital ceiling, legal EU compliance, empty batch economics)..."></textarea>
    
    <div class="modal-buttons">
      <button type="button" class="btn-secondary" onclick="closeRejectModal();">Cancel</button>
      <button type="button" class="btn-danger" id="confirmRejectBtn">Reject</button>
    </div>
  </div>
</div>

<!-- Edit Idea Details Modal -->
<div id="editIdeaModal" class="modal-backdrop" style="display:none;">
  <div class="modal-dialog">
    <h2 id="editIdeaModalTitle">Edit Idea Details</h2>
    <p style="color:var(--muted); font-size:13px; margin-bottom:12px;">
      Update title, labels, notes/rejection reason, category, and status.
    </p>
    <label style="font-size:12px; color:var(--muted); display:block; margin-bottom:4px;">Title:</label>
    <input type="text" id="editIdeaTitleInput" style="width:100%; box-sizing:border-box; margin-bottom:12px; font-size:13px; padding:6px 8px; border-radius:4px; border:1px solid var(--border); background:var(--input-bg); color:var(--text);">
    
    <div style="display:flex; gap:12px; margin-bottom:12px;">
      <div style="flex:1;">
        <label style="font-size:12px; color:var(--muted); display:block; margin-bottom:4px;">Category:</label>
        <input type="text" id="editIdeaCategoryInput" style="width:100%; box-sizing:border-box; font-size:13px; padding:6px 8px; border-radius:4px; border:1px solid var(--border); background:var(--input-bg); color:var(--text);">
      </div>
      <div style="flex:1;">
        <label style="font-size:12px; color:var(--muted); display:block; margin-bottom:4px;">Status:</label>
        <select id="editIdeaStatusSelect" style="width:100%; box-sizing:border-box; font-size:13px; padding:6px 8px; border-radius:4px; border:1px solid var(--border); background:var(--input-bg); color:var(--text);">
          <option value="untagged">Untagged</option>
          <option value="next">Next up (#status/next)</option>
          <option value="ongoing">Ongoing (#status/ongoing)</option>
          <option value="shelved">Shelved (#status/shelved)</option>
          <option value="rejected">Rejected (#status/rejected)</option>
        </select>
      </div>
    </div>

    <label for="editIdeaTagsInput" style="font-size:12px; color:var(--muted); display:block; margin-bottom:4px;">Labels (independent of status, e.g. <code>#owned #saas</code>):</label>
    <input type="text" id="editIdeaTagsInput" autocomplete="off" placeholder="#owned #hardware" style="width:100%; box-sizing:border-box; margin-bottom:12px; font-size:13px; padding:6px 8px; border-radius:4px; border:1px solid var(--border); background:var(--input-bg); color:var(--text);">

    <label style="font-size:12px; color:var(--muted); display:block; margin-bottom:4px;">Notes / Details / Decision Summary:</label>
    <textarea id="editIdeaNotesInput" rows="7" style="width:100%; box-sizing:border-box; font-size:12px; line-height:1.45; font-family:ui-monospace, monospace; padding:8px 10px; border-radius:4px; border:1px solid var(--border); background:var(--input-bg); color:var(--text);" placeholder="Detailed specifications, rejection rationale, or requirements..."></textarea>
    
    <div class="modal-buttons" style="margin-top:12px;">
      <button type="button" class="btn-secondary" onclick="closeEditModal();">Cancel</button>
      <button type="button" class="btn-primary" id="confirmEditIdeaBtn">Save Changes</button>
    </div>
  </div>
</div>

<!-- Rejection Challenge Modal -->
<div id="challengeModal" class="modal-backdrop" style="display:none;">
  <div class="modal-dialog">
    <h2 id="challengeModalTitle">⚖️ Challenge Rejection</h2>
    <p style="color:var(--muted); font-size:13px; margin-bottom:12px;">
      The card is tagged <code>#rejection_challenged</code>. On its next heartbeat the Idea Feasibility Agent re-reads the rejection with your argument,
      writes an answer on the card, and either moves the idea back to Next or upholds the rejection with evidence.
    </p>
    <span class="modal-label">Why it was rejected:</span>
    <div id="challengeReason" class="challenge-reason"></div>
    <label class="modal-label" for="challengeInput">What premise did the Idea Feasibility Agent get wrong?</label>
    <textarea id="challengeInput" rows="5" placeholder="e.g. a unique edge, a committed customer, a revised scope, new cost numbers..."></textarea>
    <div class="modal-buttons">
      <button type="button" class="btn-secondary" onclick="closeChallengeModal();">Cancel</button>
      <button type="button" class="btn-primary" id="confirmChallengeBtn">Submit Challenge</button>
    </div>
  </div>
</div>

<!-- New Project Board Modal -->
<div id="newBoardModal" class="modal-backdrop" style="display:none;">
  <div class="modal-dialog">
    <h2>📋 New project board</h2>
    <p id="newBoardHint" style="color:var(--muted); font-size:13px; margin-bottom:12px;"></p>
    <label class="modal-label" for="newBoardNameInput">Project name:</label>
    <input type="text" id="newBoardNameInput" autocomplete="off" placeholder="e.g. FARAH ERP">
    <label class="modal-label" for="newBoardSectionsInput">Sections (comma-separated headings cards are filed under):</label>
    <input type="text" id="newBoardSectionsInput" autocomplete="off" placeholder="Backlog, Features, Bugs">
    <div class="modal-buttons">
      <button type="button" class="btn-secondary" onclick="closeNewBoardModal();">Cancel</button>
      <button type="button" class="btn-primary" id="confirmNewBoardBtn">Create board</button>
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
let currentTheme = localStorage.getItem("idea_theme") || "light"; // LIGHT BY DEFAULT
let currentFileFilter = "all";
let selectedBucketStatus = "untagged";
let currentMobileCol = "untagged";
// Rejected & shelved ideas are hidden everywhere until this toggle is turned on.
let showRejected = localStorage.getItem("idea_show_rejected") === "1";

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

function openBucketModal() {
  // Drop into the board on screen, when it is one you can add to.
  const fileSel = document.getElementById("ideaFile");
  if (currentFileFilter !== "all" && Array.from(fileSel.options).some(o => o.value === currentFileFilter)) {
    fileSel.value = currentFileFilter;
    populateCategoryOptions();
  }
  document.getElementById("bucketModal").style.display = "flex";
  document.getElementById("ideaTitle").focus();
}

function closeBucketModal() {
  document.getElementById("bucketModal").style.display = "none";
}

document.getElementById("bucketModal").addEventListener("click", (e) => {
  if (e.target.id === "bucketModal") closeBucketModal();
});

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

function isRejectedIdea(item) {
  return item.status === "rejected" || item.status === "shelved";
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
    if (currentMobileCol === "rejected") currentMobileCol = "untagged";
  }
  renderCurrentView();
}

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
  } else if (e.key === "n" && !e.metaKey && !e.ctrlKey && !e.altKey
             && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)
             && !Array.from(document.querySelectorAll(".modal-backdrop")).some(m => m.style.display !== "none")) {
    e.preventDefault();
    openBucketModal();
  } else if (e.key === "Escape") {
    closeBucketModal();
    closeRejectModal();
    closeChallengeModal();
    closeNewBoardModal();
  }
});

async function loadData() {
  try {
    const res = await fetch("/api/ideas", { cache: "no-store" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.message || "Failed loading ideas");

    allIdeas = data.ideas || [];
    allCategories = data.categories || {};
    allBackends = data.backends || [];
    populateBackendSelects(data.backends);
    refreshRejectedToggleBtn();
    populateProjectSubtabs();
    populateCategoryOptions();
    renderCurrentView();
  } catch (err) {
    showToast("Error: " + err.message, true);
  }
}

function populateProjectSubtabs() {
  const container = document.getElementById("projectSubtabs");
  if (!container) return;
  // Boards come from the server's list, so a new empty board still gets a tab.
  // Top-level files first, then per-project boards.
  const seen = new Set(allBackends.concat(allIdeas.map(i => i.file)).filter(Boolean));
  const rank = f => f.includes("/") ? 1 : 0;
  const files = Array.from(seen).sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
  const subtabs = [
    { id: "all", label: "All Projects", count: allIdeas.filter(i => showRejected || !isRejectedIdea(i)).length },
    ...files.map(f => {
      const count = allIdeas.filter(i => i.file === f && (showRejected || !isRejectedIdea(i))).length;
      return { id: f, label: boardLabel(f), count };
    })
  ];

  container.innerHTML = subtabs.map(tab => {
    const active = currentFileFilter === tab.id ? " active" : "";
    return `<button type="button" class="subtab-btn${active}" data-subtab-file="${escapeHtml(tab.id)}">${escapeHtml(tab.label)} <span style="opacity: 0.6; font-size: 11px;">(${tab.count})</span></button>`;
  }).join("") + `<button type="button" class="subtab-btn" onclick="openNewBoardModal('', null);" title="Create a board for a project (PROJECTS/<name>.md)">+ New board</button>`;
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

function getFilteredIdeas() {
  return allIdeas.filter(item => {
    // Rejected & shelved ideas stay out of every view until the toggle is on.
    if (!showRejected && isRejectedIdea(item)) return false;
    // Board (project subtab)
    if (currentFileFilter !== "all" && item.file !== currentFileFilter) return false;
    return true;
  });
}

function renderCurrentView() {
  destroyInstances();
  renderKanban(document.getElementById("viewContent"), getFilteredIdeas());
}

function destroyInstances() {
  sortableInstances.forEach(s => s.destroy());
  sortableInstances = [];
}

// Render Card HTML
function createCardHtml(item) {
  const parts = splitNotes(item.notes);
  const notesHtml = parts.md
    ? `<div class="card-notes">${renderWikilinks(mdToHtml(parts.md))}</div>`
    : "";
  const tagsHtml = renderTagBadges(item.tags);
  const titleDisplay = renderWikilinks(escapeHtml(item.title));
  const isChecked = item.checked ? "checked" : "";

  return `
    <div class="idea-card" data-id="${item.id}" data-file="${escapeHtml(item.file)}">
      <div class="card-top">
        <span class="cat-tag" title="Category: ${escapeHtml(item.category)}">${escapeHtml(item.category)}</span>
        <span class="file-tag">${escapeHtml(item.file.replace('.md',''))}</span>
      </div>
      <div class="card-title">
        <input type="checkbox" class="check-box" ${isChecked} onchange="toggleCheck('${item.id}');" title="Toggle checkbox">
        <span>${titleDisplay}</span>
      </div>
      ${tagsHtml ? `<div class="card-tags">${tagsHtml}</div>` : ""}
      ${notesHtml}
      ${renderCallouts(parts.callouts)}
      ${renderAuditTrail(parts.audit)}
      <div class="card-footer">
        <span style="color:var(--muted)">#${item.id}</span>
        <div class="card-actions">
          <button class="btn-card" onclick="openEditModal('${item.id}');" title="Edit details, title, labels &amp; notes">Edit</button>
          ${!isRejectedIdea(item) && !item.file.includes("/") ? `<button class="btn-card" onclick="projectBoard('${item.id}');" title="${item.board ? "Open this project's board" : "Create a board for this project"}">${item.board ? "📋 Board" : "+ Board"}</button>` : ""}
          ${canChallenge(item) ? `<button class="btn-card btn-challenge" onclick="openChallengeModal('${item.id}');" title="Ask the Idea Feasibility Agent to re-evaluate with your counter-argument">⚖️ Challenge Rejection</button>` : ""}
          ${item.status !== "ongoing" ? `<button class="btn-card" onclick="quickStatus('${item.id}', 'ongoing');" title="Move to Ongoing">Ongoing</button>` : ""}
          ${item.status !== "next" ? `<button class="btn-card" onclick="quickStatus('${item.id}', 'next');" title="Move to Next">Next</button>` : ""}
          ${item.status !== "untagged" ? `<button class="btn-card" onclick="quickStatus('${item.id}', 'untagged');" title="Move to Untagged">Untag</button>` : ""}
          ${item.status !== "rejected" && item.status !== "shelved" ? `<button class="btn-card" onclick="openRejectModal('${item.id}');" title="Mark as rejected, with a reason">Reject</button>` : ""}
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
    { id: "next", title: "Next Up (#status/next)", dot: "dot-next", short: "Next" },
    { id: "ongoing", title: "Ongoing (#status/ongoing)", dot: "dot-ongoing", short: "Ongoing" },
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
  const tags = parseTagInput(document.getElementById("ideaTags").value);
  const is_owned = document.getElementById("ideaOwned").checked;

  try {
    const res = await fetch("/api/ideas/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, target_file: file, category, notes, status, tags, is_owned }),
    });
    const result = await res.json();
    if (!result.ok) throw new Error(result.message || "Failed to add idea");

    showToast(`✓ Dropped into '${file}' [${category}]!`);
    const titleInput = document.getElementById("ideaTitle");
    titleInput.value = "";
    document.getElementById("ideaNotes").value = "";
    document.getElementById("ideaTags").value = "";
    document.getElementById("ideaOwned").checked = false;
    closeBucketModal();
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
function openRejectModal(id) {
  const item = allIdeas.find(i => i.id === id);
  const title = item ? item.title : id;
  pendingRejectId = id;
  document.getElementById("rejectModalTitle").textContent = `Reject '${title}'`;
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
    showToast("✓ Marked as rejected");
    await loadData();
  } catch (err) {
    showToast("Error rejecting: " + err.message, true);
  }
});

let currentEditIdeaId = null;
function openEditModal(id) {
  const item = allIdeas.find(i => i.id === id);
  if (!item) return;
  currentEditIdeaId = id;
  document.getElementById("editIdeaModalTitle").textContent = `Edit '${item.title}'`;
  document.getElementById("editIdeaTitleInput").value = item.title;
  document.getElementById("editIdeaCategoryInput").value = item.category || "General";
  document.getElementById("editIdeaStatusSelect").value = item.status || "untagged";
  document.getElementById("editIdeaNotesInput").value = item.notes || "";
  document.getElementById("editIdeaTagsInput").value = (item.tags || []).map(t => "#" + t).join(" ");
  document.getElementById("editIdeaModal").style.display = "flex";
  document.getElementById("editIdeaTitleInput").focus();
}

function closeEditModal() {
  currentEditIdeaId = null;
  document.getElementById("editIdeaModal").style.display = "none";
}

document.getElementById("confirmEditIdeaBtn").addEventListener("click", async () => {
  if (!currentEditIdeaId) return;
  const id = currentEditIdeaId;
  const title = document.getElementById("editIdeaTitleInput").value.trim();
  const category = document.getElementById("editIdeaCategoryInput").value.trim();
  const status = document.getElementById("editIdeaStatusSelect").value;
  const notes = document.getElementById("editIdeaNotesInput").value.trim();
  const tags = parseTagInput(document.getElementById("editIdeaTagsInput").value);

  if (!title) {
    showToast("Title cannot be empty", true);
    return;
  }

  closeEditModal();

  try {
    const res = await fetch("/api/ideas/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, title, category, status, notes, tags }),
    });
    const result = await res.json();
    if (!result.ok) throw new Error(result.message);
    showToast("✓ Idea updated");
    await loadData();
  } catch (err) {
    showToast("Error updating idea: " + err.message, true);
  }
});

// ---- Labels, callouts and the challenge audit trail -----------------------
// Labels (#owned, #saas...) are orthogonal to the status column. These three
// carry meaning for the Idea Feasibility Agent and get their own badge.
const SPECIAL_TAGS = {
  owned: { cls: "tag-owned", label: "OWNED · MANDATED", title: "#owned - founder mandate: the Idea Feasibility Agent skips Stage 0 kill gates and goes straight to design" },
  rejection_challenged: { cls: "tag-challenged", label: "CHALLENGE PENDING", title: "#rejection_challenged - waiting for the Idea Feasibility Agent to answer" },
  rejection_answered: { cls: "tag-answered", label: "CHALLENGE ANSWERED", title: "#rejection_answered - the Idea Feasibility Agent has ruled on the challenge" },
};

function renderTagBadges(tags) {
  const list = tags || [];
  const special = list.filter(t => SPECIAL_TAGS[t]).map(t => {
    const s = SPECIAL_TAGS[t];
    return `<span class="tag-pill ${s.cls}" title="${escapeHtml(s.title)}">${escapeHtml(s.label)}</span>`;
  });
  const plain = list.filter(t => !SPECIAL_TAGS[t]).map(t => `<span class="tag-pill">#${escapeHtml(t)}</span>`);
  return special.concat(plain).join("");
}

function mdToHtml(text) {
  if (typeof marked !== "undefined") return marked.parse(text);
  return escapeHtml(text).replace(/\\n/g, "<br>");
}

const CALLOUT_HEAD = /^>\\s*\\[!([\\w-]+)\\]([+-]?)\\s*(.*)$/;
const AUDIT_HEAD = /^[-*]\\s+\\*\\*(Challenge|Feasibility Answer)\\s*\\(([^)]*)\\)\\*\\*:?\\s*(.*)$/;
const AUDIT_TAG_TOKENS = /(^|\\s)#(rejection_challenged|rejection_answered)\\b/g;

// Split card notes into plain markdown, Obsidian callouts (rendered as
// <details>) and challenge / Feasibility answer entries (rendered as an audit trail).
function splitNotes(notes) {
  const lines = (notes || "").split("\\n");
  const md = [], callouts = [], audit = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const c = line.match(CALLOUT_HEAD);
    if (c) {
      const body = [];
      i++;
      while (i < lines.length && /^>/.test(lines[i])) {
        body.push(lines[i].replace(/^> ?/, ""));
        i++;
      }
      callouts.push({ kind: c[1].toLowerCase(), open: c[2] === "+", title: c[3].trim(), body: body.join("\\n") });
      continue;
    }
    const a = line.match(AUDIT_HEAD);
    if (a) {
      const text = [a[3]];
      i++;
      while (i < lines.length && /^\\s+\\S/.test(lines[i]) && !/^\\s*[-*]\\s+\\*\\*/.test(lines[i])) {
        text.push(lines[i].trim());
        i++;
      }
      audit.push({ kind: a[1], date: a[2], text: text.join("\\n").replace(AUDIT_TAG_TOKENS, "$1").trim() });
      continue;
    }
    md.push(line);
    i++;
  }
  return { md: md.join("\\n").trim(), callouts, audit };
}

function renderCallouts(callouts) {
  return callouts.map(c => `
    <details class="idea-callout"${c.open ? " open" : ""}>
      <summary><span class="callout-icon">📊</span> ${escapeHtml(c.title || "Detailed Analysis")}</summary>
      <div class="idea-callout-body">${renderWikilinks(mdToHtml(c.body))}</div>
    </details>`).join("");
}

function renderAuditTrail(entries) {
  if (!entries.length) return "";
  return `<div class="audit-trail">${entries.map(e => {
    if (e.kind === "Challenge") {
      return `<div class="audit-entry audit-challenge"><div class="audit-head">⚖️ Founder challenge · ${escapeHtml(e.date)}</div>${renderWikilinks(mdToHtml(e.text))}</div>`;
    }
    const m = e.text.match(/^\\[(accepted|upheld)\\]\\s*/i);
    const verdict = m ? m[1].toLowerCase() : "";
    const text = m ? e.text.slice(m[0].length) : e.text;
    const verdictHtml = verdict ? ` · <span class="verdict">${verdict}</span>` : "";
    return `<div class="audit-entry audit-answer${verdict ? " audit-" + verdict : ""}"><div class="audit-head">🤖 Feasibility answer · ${escapeHtml(e.date)}${verdictHtml}</div>${renderWikilinks(mdToHtml(text))}</div>`;
  }).join("")}</div>`;
}

function canChallenge(item) {
  return (item.status === "rejected" || item.status === "shelved")
    && !(item.tags || []).includes("rejection_challenged");
}

// Tags typed as "#owned, saas hardware" -> ["owned", "saas", "hardware"]
function parseTagInput(text) {
  return Array.from(new Set((text || "").split(/[\\s,]+/).map(t => t.replace(/^#/, "").toLowerCase()).filter(Boolean)));
}

// The backend files come from the server (notes tagged myJira/backend), so a
// new board appears here without a code change.
function populateBackendSelects(backends) {
  const files = backends && backends.length ? backends : Object.keys(allCategories);
  const fileSel = document.getElementById("ideaFile");
  const prevFile = fileSel.value;
  fileSel.innerHTML = files.map(f => `<option value="${escapeHtml(f)}">${escapeHtml(f)}</option>`).join("");
  if (files.includes(prevFile)) fileSel.value = prevFile;
}

let pendingChallengeId = null;
function openChallengeModal(id) {
  const item = allIdeas.find(i => i.id === id);
  if (!item) return;
  pendingChallengeId = id;
  document.getElementById("challengeModalTitle").textContent = `⚖️ Challenge Rejection: ${item.title}`;
  const reason = item.rejection_reason || (item.notes || "").slice(0, 400) || "No reason was recorded.";
  document.getElementById("challengeReason").innerHTML = renderWikilinks(mdToHtml(reason));
  document.getElementById("challengeInput").value = "";
  document.getElementById("challengeModal").style.display = "flex";
  document.getElementById("challengeInput").focus();
}

function closeChallengeModal() {
  pendingChallengeId = null;
  document.getElementById("challengeModal").style.display = "none";
}

document.getElementById("confirmChallengeBtn").addEventListener("click", async () => {
  if (!pendingChallengeId) return;
  const id = pendingChallengeId;
  const challenge = document.getElementById("challengeInput").value.trim();
  if (!challenge) {
    showToast("Write the counter-argument first", true);
    return;
  }
  closeChallengeModal();
  try {
    const res = await fetch("/api/ideas/challenge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, challenge }),
    });
    const result = await res.json();
    if (!result.ok) throw new Error(result.message);
    showToast("⚖️ Challenge filed - the Idea Feasibility Agent answers on its next heartbeat");
    await loadData();
  } catch (err) {
    showToast("Error filing challenge: " + err.message, true);
  }
});

// ---- Per-project boards ----------------------------------------------------
// Any note tagged myJira/backend is a board; project boards live in PROJECTS/.
let allBackends = [];
let pendingBoardParent = null;

function boardLabel(file) {
  const name = file.replace(/\\.md$/, "");
  return file.includes("/") ? "📋 " + name.split("/").pop() : name;
}

function openBoard(file) {
  currentFileFilter = file;
  populateProjectSubtabs();
  renderCurrentView();
  const bar = document.getElementById("projectSubtabsBar");
  if (bar) bar.scrollIntoView({ behavior: "smooth", block: "start" });
}

function openNewBoardModal(title, parentFile) {
  pendingBoardParent = parentFile || null;
  document.getElementById("newBoardNameInput").value = title || "";
  document.getElementById("newBoardSectionsInput").value = "Backlog";
  document.getElementById("newBoardHint").textContent = parentFile
    ? `Creates PROJECTS/<name>.md, linked back to its ticket in ${parentFile}.`
    : "Creates PROJECTS/<name>.md in the vault, tagged myJira/backend.";
  document.getElementById("newBoardModal").style.display = "flex";
  document.getElementById("newBoardNameInput").focus();
}

function closeNewBoardModal() {
  pendingBoardParent = null;
  document.getElementById("newBoardModal").style.display = "none";
}

// Card button: open the project's board, or create it from the card.
function projectBoard(id) {
  const item = allIdeas.find(i => i.id === id);
  if (!item) return;
  if (item.board) openBoard(item.board);
  else openNewBoardModal(item.title, item.file);
}

document.getElementById("confirmNewBoardBtn").addEventListener("click", async () => {
  const name = document.getElementById("newBoardNameInput").value.trim();
  const sections = document.getElementById("newBoardSectionsInput").value.split(",").map(s => s.trim()).filter(Boolean);
  if (!name) {
    showToast("Give the board a name", true);
    return;
  }
  const parent = pendingBoardParent;
  closeNewBoardModal();
  try {
    const res = await fetch("/api/ideas/boards/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, sections, parent }),
    });
    const result = await res.json();
    if (!result.ok && !result.exists) throw new Error(result.message);
    showToast(result.exists ? `Board ${result.file} already exists - opening it` : `📋 ${result.message}`);
    await loadData();
    if (result.file) openBoard(result.file);
  } catch (err) {
    showToast("Error creating board: " + err.message, true);
  }
});

document.getElementById("refreshBtn").addEventListener("click", (e) => {
  e.preventDefault();
  loadData();
  showToast("Vault synchronized with disk");
});

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-subtab-file]");
  if (!btn) return;
  e.preventDefault();
  const file = btn.dataset.subtabFile;
  currentFileFilter = file;
  populateProjectSubtabs();
  renderCurrentView();
});

// Embedded mode detection (e.g. inside homelab cockpit tab)
if (new URLSearchParams(window.location.search).get("embedded") === "1" || window.self !== window.top) {
  document.body.classList.add("embedded");
}

// Initial boot
refreshRejectedToggleBtn();
loadData();
</script>
</body>
</html>
"""
