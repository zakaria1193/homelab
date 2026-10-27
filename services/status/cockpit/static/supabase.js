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
  dot.className = 'status-dot ' + (p.paused ? 'status-unknown' : 'status-up');
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
  btn.className = 'btn secondary small';
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
  const data = await postJSON('/api/supabase/toggle', {ref: ref, paused: paused});
  say(data.message || (data.ok ? 'Done' : 'Failed'), !data.ok);
  await load();
}

load();
