"""The media autopilot's hopping-show list, edited from the cockpit's Media tab.

A "hopping" show is one watched out of order, so the autopilot must not delete
its watched episodes or guess which episodes come next. `autopilot.py` stays the
only thing that knows how the list is stored: this module shells out to its
`hopping` and `shows` commands, the same way supabase_keepalive.py drives
keepalive.py, so the page cannot drift from what the timer actually reads.

Nothing here builds a command out of client text beyond one argv element: the
title the browser sends is passed as a single argument, never through a shell.
"""

import json
import os
import subprocess
import sys

from cockpit.pages.theme import THEME

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
# `or` rather than a get() default: an empty value in the .env means "default".
AUTOPILOT_DIR = os.environ.get("STATUS_AUTOPILOT_DIR") or os.path.join(
    REPO_ROOT, "services", "media-autopilot"
)
SCRIPT = os.path.join(AUTOPILOT_DIR, "autopilot.py")
TIMEOUT = float(os.environ.get("STATUS_AUTOPILOT_TIMEOUT") or "20")


def _run(*argv):
    """Run autopilot.py. Returns (ok, stdout, message)."""
    if not os.path.exists(SCRIPT):
        return False, "", f"autopilot.py not found at {SCRIPT}"
    try:
        done = subprocess.run(
            [sys.executable, SCRIPT, *argv],
            cwd=AUTOPILOT_DIR, capture_output=True, text=True, timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False, "", f"autopilot.py {argv[0]} timed out after {TIMEOUT:.0f}s"
    except OSError as err:
        return False, "", str(err)
    if done.returncode != 0:
        return False, done.stdout, (done.stderr or done.stdout).strip()
    return True, done.stdout, ""


def _json(*argv):
    ok, out, message = _run(*argv)
    if not ok:
        return None, message
    try:
        return json.loads(out), ""
    except json.JSONDecodeError:
        return None, f"autopilot.py {argv[0]} returned nothing usable"


def roster():
    """The hopping shows, plus every show Sonarr has (for the add box's suggestions)."""
    hopping, message = _json("hopping", "list")
    if hopping is None:
        return {"ok": False, "hopping": [], "shows": [], "message": message}
    # Sonarr being down must not stop the list from being shown or edited.
    shows, _ = _json("shows")
    return {"ok": True, "hopping": hopping.get("hopping", []),
            "shows": (shows or {}).get("shows", [])}


def edit(title, add):
    """Add or remove one show by title. Returns {"ok", "message"}."""
    title = (title or "").strip()
    if not title:
        return {"ok": False, "message": "no show title given"}
    if len(title) > 200 or "\n" in title:
        return {"ok": False, "message": "that is not a show title"}
    ok, out, message = _run("hopping", "add" if add else "remove", title)
    if not ok:
        return {"ok": False, "message": message}
    return {"ok": True, "message": out.strip()}


MEDIA_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Media · __TITLE__</title>
<style>
  {THEME}
  .wrap { max-width: 760px; margin: 0 auto; padding: 24px 18px 64px; }
  body.embedded .wrap { padding: 12px 14px 24px; max-width: 100%; }
  body.embedded .back { display: none; }
  header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 16px; }
  h1 { font-size: 22px; margin: 0; }
  h2 { font-size: 15px; margin: 24px 0 0; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .lede { color: var(--muted); font-size: 13px; margin: 10px 0 0; max-width: 72ch; }
  .row { display: flex; align-items: center; gap: 10px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 8px; padding: 9px 12px; margin-top: 8px; }
  .row .name { font-weight: 600; font-size: 14px; flex: 1; }
  .add { display: flex; gap: 8px; margin-top: 12px; }
  input { flex: 1; background: var(--panel); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 7px 10px; font-size: 13px; }
  button { background: var(--panel); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 5px 12px; font-size: 12px; cursor: pointer; }
  button:hover { border-color: var(--muted); background: var(--raise); }
  button:disabled { opacity: 0.45; cursor: default; }
  .empty { color: var(--muted); font-size: 13px; padding: 14px; background: var(--panel);
    border: 1px dashed var(--border); border-radius: 8px; margin-top: 8px; }
  .msg { font-size: 12px; color: var(--muted); margin-top: 12px; min-height: 18px; }
  .msg.bad { color: var(--down); }
  footer { margin-top: 36px; color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Media</h1>
    <a class="back" href="/">&larr; All services</a>
  </header>

  <h2>Hopping shows</h2>
  <p class="lede">The media autopilot keeps the next two episodes of each show you watch and
  deletes watched episodes after three days. Shows you watch out of order would be damaged by
  that, so the ones listed here are <em>never</em> touched: no deleting, no picking the next
  episodes. Changes apply on the next run, within five minutes.</p>

  <div id="list"><div class="empty">Loading…</div></div>
  <form class="add" id="addForm" autocomplete="off">
    <input id="title" list="shows" placeholder="Add a show (Sonarr title)…" required>
    <datalist id="shows"></datalist>
    <button type="submit">Add</button>
  </form>
  <div class="msg" id="msg"></div>

  <footer>The list lives in <code>services/media-autopilot/hopping.json</code>; the job is
    <code>autopilot.py</code> in the same folder.</footer>
</div>
<script>
if (new URLSearchParams(window.location.search).get('embedded') === '1') {
  document.body.classList.add('embedded');
}
const listEl = document.getElementById('list');
const msgEl = document.getElementById('msg');
const titleEl = document.getElementById('title');

function say(text, bad) {
  msgEl.textContent = text || '';
  msgEl.className = bad ? 'msg bad' : 'msg';
}

async function post(title, add) {
  say(add ? 'Adding…' : 'Removing…');
  try {
    const res = await fetch('/api/media/hopping', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({title: title, add: add}),
    });
    const data = await res.json();
    say(data.message || (data.ok ? 'Done' : 'Failed'), !data.ok);
    return data.ok;
  } catch (err) {
    say('' + err, true);
    return false;
  }
}

function row(title) {
  const el = document.createElement('div');
  el.className = 'row';
  const name = document.createElement('span');
  name.className = 'name';
  name.textContent = title;
  const btn = document.createElement('button');
  btn.textContent = 'Remove';
  btn.onclick = async () => { btn.disabled = true; await post(title, false); await load(); };
  el.append(name, btn);
  return el;
}

async function load() {
  let data;
  try {
    data = await (await fetch('/api/media', {headers: {'Accept': 'application/json'}})).json();
  } catch (err) {
    listEl.replaceChildren(Object.assign(document.createElement('div'),
      {className: 'empty', textContent: 'Could not reach the cockpit API: ' + err}));
    return;
  }
  if (!data.ok) {
    listEl.replaceChildren(Object.assign(document.createElement('div'),
      {className: 'empty', textContent: data.message || 'autopilot.py could not be read'}));
    return;
  }
  const have = new Set(data.hopping.map(t => t.toLowerCase()));
  document.getElementById('shows').replaceChildren(...data.shows
    .filter(t => !have.has(t.toLowerCase()))
    .map(t => Object.assign(document.createElement('option'), {value: t})));
  listEl.replaceChildren(...(data.hopping.length ? data.hopping.map(row) : [Object.assign(
    document.createElement('div'), {className: 'empty',
      textContent: 'No hopping shows: the autopilot manages every show it can see.'})]));
}

document.getElementById('addForm').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  if (await post(titleEl.value, true)) titleEl.value = '';
  await load();
});

load();
</script>
</body>
</html>
""".replace("{THEME}", THEME)
