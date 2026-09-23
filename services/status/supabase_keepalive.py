"""The Supabase keepalive roster, driven from the cockpit.

A project that is not worth keeping awake - an archived side project, a demo
whose free tier can lapse - should not make the weekly run look like it failed.
This module is the cockpit's side of that switch: it reads the roster, and it
pauses and resumes one project at a time.

`keepalive.py` stays the only thing that knows what a project is. This module
shells out to it rather than re-reading `.env`, so the page cannot drift from
what the timer actually does, and the anon keys never enter this process: the
`list --json` it parses does not carry them.

Nothing here builds a command out of client text. The browser sends a project
ref, which is looked up in this module's own inventory before `pause` or
`resume` is run with it - the same rule claude_rc.py follows.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
# `or` rather than a get() default: systemd hands the key over with an empty
# value when the .env leaves it blank, and empty means "use the default".
KEEPALIVE_DIR = os.environ.get("STATUS_SUPABASE_DIR") or os.path.join(
    REPO_ROOT, "services", "supabase-keepalive"
)
SCRIPT = os.path.join(KEEPALIVE_DIR, "keepalive.py")
# Listing is local when the projects are listed by hand in .env, but a
# SUPABASE_ACCESS_TOKEN makes it a Management API round trip, so allow for one.
TIMEOUT = float(os.environ.get("STATUS_SUPABASE_TIMEOUT") or "45")


def _run(*argv):
    """Run keepalive.py. Returns (ok, stdout, message)."""
    if not os.path.exists(SCRIPT):
        return False, "", f"keepalive.py not found at {SCRIPT}"
    try:
        done = subprocess.run(
            [sys.executable, SCRIPT, *argv],
            cwd=KEEPALIVE_DIR, capture_output=True, text=True, timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False, "", f"keepalive.py {' '.join(argv)} timed out after {TIMEOUT:.0f}s"
    except OSError as err:
        return False, "", str(err)
    if done.returncode != 0:
        # `list` exits non-zero when nothing is configured, which is a real
        # answer rather than a crash, so hand the stderr back either way.
        return False, done.stdout, (done.stderr or done.stdout).strip()
    return True, done.stdout, ""


def roster():
    """Every configured project, each flagged paused or not."""
    ok, out, message = _run("list", "--json")
    if not ok and not out:
        return {"ok": False, "projects": [], "problems": [], "message": message}
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return {"ok": False, "projects": [], "problems": [],
                "message": message or "keepalive.py list --json returned nothing usable"}
    payload.setdefault("projects", [])
    payload.setdefault("problems", [])
    payload["ok"] = True
    return payload


def known(ref):
    return any(p.get("ref") == ref for p in roster().get("projects", []))


def set_paused(ref, paused):
    """Pause or resume one project, by the ref the page was rendered with."""
    ref = (ref or "").strip()
    if not known(ref):
        # Covers both a stale page and anything the browser made up.
        return {"ok": False, "message": f"no configured project with ref {ref!r}"}
    ok, out, message = _run("pause" if paused else "resume", ref)
    if not ok:
        return {"ok": False, "message": message}
    return {"ok": True, "ref": ref, "paused": paused, "message": out.strip()}


SUPABASE_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Supabase projects · __TITLE__</title>
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
  a { color: inherit; }
  .wrap { max-width: 960px; margin: 0 auto; padding: 24px 18px 64px; }
  header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 16px; }
  h1 { font-size: 22px; margin: 0; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .lede { color: var(--muted); font-size: 13px; margin: 10px 0 0; max-width: 70ch; }
  .dot { width: 9px; height: 9px; border-radius: 50%; flex: none; background: var(--up); }
  .dot.paused { background: var(--unknown); }
  .card { background: var(--panel); border: 1px solid var(--border); border-left-width: 3px;
    border-left-color: var(--up); border-radius: 8px; padding: 13px 15px; margin-top: 10px; }
  .card.paused { border-left-color: var(--unknown); }
  .card.paused .who { color: var(--muted); }
  .top { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
  .who { font-weight: 600; font-size: 15px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  .badge { font-size: 11px; padding: 2px 7px; border-radius: 999px; background: var(--raise);
    border: 1px solid var(--border); color: var(--muted); }
  .badge.live { color: var(--up); border-color: var(--up); }
  .facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 2px 16px; margin-top: 8px; font-size: 12px; color: var(--muted); }
  .facts b { color: var(--text); font-weight: 500; }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  button { background: var(--panel); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 4px 11px; font-size: 12px; cursor: pointer;
    display: inline-flex; align-items: center; gap: 5px; }
  button:hover { border-color: var(--muted); background: var(--raise); }
  button:disabled { opacity: 0.45; cursor: default; }
  .empty { color: var(--muted); font-size: 13px; padding: 16px; background: var(--panel);
    border: 1px dashed var(--border); border-radius: 8px; margin-top: 10px; }
  .problem { border-left-color: var(--warn); }
  .msg { font-size: 12px; color: var(--muted); margin-top: 14px; min-height: 18px; }
  .msg.bad { color: var(--down); }
  footer { margin-top: 40px; color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Supabase projects</h1>
    <a class="back" href="/">&larr; All services</a>
  </header>
  <p class="lede">A free Supabase project pauses itself after about a week idle, so
  <code>supabase-keepalive</code> pings each one every Sunday. Pause the ones you no longer
  care about: they are skipped rather than reported as unreachable, and the weekly run stays
  green. Pausing here does <em>not</em> pause the project at Supabase - it only stops this
  homelab from keeping it awake.</p>

  <div id="list"><div class="empty">Loading…</div></div>
  <div class="msg" id="msg"></div>

  <footer>Roster and pause state come from
    <code>services/supabase-keepalive/keepalive.py</code>; pauses are recorded in
    <code>paused.json</code> next to it.</footer>
</div>
<script>
const listEl = document.getElementById('list');
const msgEl = document.getElementById('msg');

function say(text, bad) {
  msgEl.textContent = text || '';
  msgEl.className = bad ? 'msg bad' : 'msg';
}

function when(iso) {
  if (!iso) return 'never';
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString();
}

function card(p) {
  const el = document.createElement('div');
  el.className = 'card' + (p.paused ? ' paused' : '');
  const top = document.createElement('div');
  top.className = 'top';
  const dot = document.createElement('span');
  dot.className = 'dot' + (p.paused ? ' paused' : '');
  const who = document.createElement('span');
  who.className = 'who';
  who.textContent = p.name;
  const badge = document.createElement('span');
  badge.className = 'badge' + (p.paused ? '' : ' live');
  badge.textContent = p.paused ? 'paused' : 'pinged weekly';
  top.append(dot, who, badge);

  const facts = document.createElement('div');
  facts.className = 'facts';
  const rows = [['ref', p.ref], ['table', p.table || 'PostgREST root'],
                ['last reached', when(p.last_ok)],
                [p.paused ? 'paused since' : 'last result',
                 p.paused ? when(p.paused_since) : (p.last_detail || '-')]];
  for (const [k, v] of rows) {
    const d = document.createElement('div');
    d.append(k + ': ');
    const b = document.createElement('b');
    b.textContent = v;
    d.append(b);
    facts.append(d);
  }

  const acts = document.createElement('div');
  acts.className = 'acts';
  const btn = document.createElement('button');
  btn.textContent = p.paused ? 'Resume pinging' : 'Pause';
  btn.onclick = () => toggle(p.ref, !p.paused, btn);
  acts.append(btn);

  el.append(top, facts, acts);
  return el;
}

async function load() {
  let data;
  try {
    data = await (await fetch('/api/supabase', {headers: {'Accept': 'application/json'}})).json();
  } catch (err) {
    listEl.innerHTML = '';
    listEl.append(Object.assign(document.createElement('div'),
      {className: 'empty', textContent: 'Could not reach the cockpit API: ' + err}));
    return;
  }
  listEl.innerHTML = '';
  if (!data.ok) {
    listEl.append(Object.assign(document.createElement('div'),
      {className: 'empty', textContent: data.message || 'keepalive.py could not be read'}));
    return;
  }
  if (!data.projects.length) {
    listEl.append(Object.assign(document.createElement('div'), {className: 'empty',
      textContent: 'No projects configured — set SUPABASE_ACCESS_TOKEN or SUPABASE_PROJECTS in the service .env'}));
  }
  for (const p of data.projects) listEl.append(card(p));
  for (const problem of (data.problems || [])) {
    const el = document.createElement('div');
    el.className = 'card problem';
    el.textContent = problem;
    listEl.append(el);
  }
}

async function toggle(ref, paused, btn) {
  btn.disabled = true;
  say(paused ? 'Pausing…' : 'Resuming…');
  try {
    const res = await fetch('/api/supabase/toggle', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ref: ref, paused: paused}),
    });
    const data = await res.json();
    say(data.message || (data.ok ? 'Done' : 'Failed'), !data.ok);
  } catch (err) {
    say('' + err, true);
  }
  await load();
}

load();
</script>
</body>
</html>
"""
