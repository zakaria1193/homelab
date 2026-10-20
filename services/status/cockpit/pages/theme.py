"""The one shared theme every cockpit page draws its base styles from.

Tokens and base components follow the `apple-ui-skills` skill installed at
`.claude/skills/apple-ui-skills/` (see its `SOURCE.md`): light mode only,
a system-font stack standing in for Inter (no outbound font download), a 4px
spacing grid, and the skill's accent/surface colours. Status colours
(`--up`/`--down`/`--warn`/`--unknown`) are the cockpit's own addition — the
skill has no opinion on them — and keep the meanings the cockpit already
relies on (AGENTS.md / homelab-0005).

A page embeds this by putting `{THEME}` inside its own `<style>` block
(before its page-specific rules) and declaring nothing else in `:root`.
"""

TOKENS = """
  :root {
    color-scheme: light;
    --bg: #ffffff; --panel: #ffffff; --raise: #f5f5f7; --border: #d8d8dc;
    --text: #1d1d1f; --muted: #6e6e73; --faint: #86868b;
    --accent: #155bd0; --accent-contrast: #ffffff;
    --up: #1a9c4b; --down: #d53f3f; --warn: #b9770e; --unknown: #86868b;
    --usage-bg: rgba(21, 91, 208, 0.06); --usage-border: rgba(21, 91, 208, 0.22);
    --radius-sm: 6px; --radius: 10px; --radius-lg: 16px; --radius-pill: 999px;
    --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
    --space-5: 20px; --space-6: 24px; --space-8: 32px;
    --font: -apple-system, system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
"""

BASE = """
  * { box-sizing: border-box; }
  html { color-scheme: light; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 var(--font); }
  a { color: inherit; }
  button, input, select, textarea { font-family: var(--font); }

  .card { background: var(--panel); border: 1px solid var(--border);
    border-radius: var(--radius); padding: var(--space-4); }

  .btn { display: inline-flex; align-items: center; gap: var(--space-2);
    background: var(--accent); color: var(--accent-contrast); border: none;
    border-radius: var(--radius-sm); padding: 8px 14px; font: inherit; font-weight: 600;
    cursor: pointer; }
  .btn:hover { filter: brightness(1.08); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn.secondary { background: var(--raise); color: var(--text); border: 1px solid var(--border); }

  input[type=text], input[type=password], input[type=search], textarea, select {
    width: 100%; background: var(--bg); color: var(--text); font: inherit;
    border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 10px; }
  input:focus, textarea:focus, select:focus, button:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px; }

  .tabs { display: flex; gap: var(--space-2); border-bottom: 1px solid var(--border);
    margin: var(--space-5) 0; overflow-x: auto; }
  .tab-btn { display: inline-flex; align-items: center; gap: var(--space-2); background: none;
    border: none; border-bottom: 2px solid transparent; padding: 10px var(--space-4);
    font: inherit; font-size: 14px; font-weight: 500; color: var(--muted); cursor: pointer;
    white-space: nowrap; margin-bottom: -1px; transition: color 0.15s ease, border-color 0.15s ease; }
  .tab-btn:hover { color: var(--text); }
  .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }

  .status-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; }
  .status-up { background: var(--up); }
  .status-down { background: var(--down); }
  .status-warn { background: var(--warn); }
  .status-unknown { background: var(--unknown); }
"""

THEME = TOKENS + BASE
