if (new URLSearchParams(window.location.search).get('embedded') === '1') {
  document.body.classList.add('embedded');
}
const msgEl = document.getElementById('msg');
const EMPTY = {
  hopping: 'No hopping shows: the autopilot manages every show it can see.',
  maintained: 'No maintained movies: every watched movie is deleted after the one-week warning.',
};

function say(text, bad) {
  msgEl.textContent = text || '';
  msgEl.className = bad ? 'msg bad' : 'msg';
}

const ID_KEY = { hopping: 'tvdbId', maintained: 'tmdbId' };
// title (lowercase) -> id, for the picker in each list; rebuilt on every load().
const picks = { hopping: new Map(), maintained: new Map() };

async function post(kind, ident, add) {
  say(add ? 'Adding…' : 'Removing…');
  const body = { add: add };
  if (typeof ident === 'number') body.id = ident; else body.title = ident;
  const data = await postJSON('/api/media/' + kind, body);
  say(data.message || (data.ok ? 'Done' : 'Failed'), !data.ok);
  return data.ok;
}

function row(kind, entry) {
  const idKey = ID_KEY[kind];
  const el = document.createElement('div');
  el.className = 'row';
  const name = document.createElement('span');
  name.className = 'name';
  name.textContent = entry.title;
  el.append(name);
  if (entry.matched === false) {
    el.append(Object.assign(document.createElement('span'),
      { className: 'tag unmatched', textContent: 'matches nothing' }));
  }
  if (entry.current_title) {
    el.append(Object.assign(document.createElement('span'),
      { className: 'tag renamed', textContent: 'now: ' + entry.current_title }));
  }
  const btn = document.createElement('button');
  btn.className = 'btn secondary small';
  btn.textContent = 'Remove';
  const ident = entry[idKey] != null ? entry[idKey] : entry.title;
  btn.onclick = async () => { btn.disabled = true; await post(kind, ident, false); await load(); };
  el.append(btn);
  return el;
}

function fill(kind, items, suggestions, suggestMessage, datalistId) {
  const idKey = ID_KEY[kind];
  const have = new Set(items.map(e => e[idKey]).filter(id => id != null));
  const haveTitles = new Set(items.filter(e => e[idKey] == null).map(e => e.title.toLowerCase()));
  const pickable = suggestions.filter(s => !have.has(s[idKey]) && !haveTitles.has(s.title.toLowerCase()));
  const map = picks[kind];
  map.clear();
  pickable.forEach(s => map.set(s.title.toLowerCase(), s[idKey]));
  document.getElementById(datalistId).replaceChildren(...pickable
    .map(s => Object.assign(document.createElement('option'), { value: s.title })));
  document.getElementById('list-' + kind).replaceChildren(...(items.length ? items.map(e => row(kind, e))
    : [Object.assign(document.createElement('div'), { className: 'empty', textContent: EMPTY[kind] })]));
  const form = document.querySelector('form.add[data-kind="' + kind + '"]');
  const input = form.querySelector('input');
  const btn = form.querySelector('button');
  const note = document.getElementById('note-' + kind);
  if (suggestMessage) {
    input.disabled = true;
    btn.disabled = true;
    note.textContent = suggestMessage;
  } else {
    input.disabled = false;
    note.textContent = '';
    syncAddButton(kind);
  }
}

function syncAddButton(kind) {
  const form = document.querySelector('form.add[data-kind="' + kind + '"]');
  const input = form.querySelector('input');
  const btn = form.querySelector('button');
  if (input.disabled) return;
  btn.disabled = !picks[kind].has(input.value.trim().toLowerCase());
}

async function load() {
  let data;
  try {
    data = await (await fetch('/api/media', { headers: { 'Accept': 'application/json' } })).json();
  } catch (err) {
    say('Could not reach the cockpit API: ' + err, true);
    return;
  }
  if (!data.ok) {
    say(data.message || 'autopilot.py could not be read', true);
    return;
  }
  fill('hopping', data.hopping, data.shows, data.shows_message, 'shows');
  fill('maintained', data.maintained, data.movies, data.movies_message, 'movies');
}

document.querySelectorAll('form.add').forEach(form => {
  const kind = form.dataset.kind;
  const input = form.querySelector('input');
  input.addEventListener('input', () => syncAddButton(kind));
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const id = picks[kind].get(input.value.trim().toLowerCase());
    if (id == null) return;
    if (await post(kind, id, true)) input.value = '';
    await load();
  });
});

load();
