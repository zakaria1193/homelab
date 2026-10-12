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

async function post(kind, title, add) {
  say(add ? 'Adding…' : 'Removing…');
  const data = await postJSON('/api/media/' + kind, {title: title, add: add});
  say(data.message || (data.ok ? 'Done' : 'Failed'), !data.ok);
  return data.ok;
}

function row(kind, title) {
  const el = document.createElement('div');
  el.className = 'row';
  const name = document.createElement('span');
  name.className = 'name';
  name.textContent = title;
  const btn = document.createElement('button');
  btn.className = 'btn secondary small';
  btn.textContent = 'Remove';
  btn.onclick = async () => { btn.disabled = true; await post(kind, title, false); await load(); };
  el.append(name, btn);
  return el;
}

function fill(kind, items, suggestions, datalistId) {
  const have = new Set(items.map(t => t.toLowerCase()));
  document.getElementById(datalistId).replaceChildren(...suggestions
    .filter(t => !have.has(t.toLowerCase()))
    .map(t => Object.assign(document.createElement('option'), {value: t})));
  document.getElementById('list-' + kind).replaceChildren(...(items.length ? items.map(t => row(kind, t))
    : [Object.assign(document.createElement('div'), {className: 'empty', textContent: EMPTY[kind]})]));
}

async function load() {
  let data;
  try {
    data = await (await fetch('/api/media', {headers: {'Accept': 'application/json'}})).json();
  } catch (err) {
    say('Could not reach the cockpit API: ' + err, true);
    return;
  }
  if (!data.ok) {
    say(data.message || 'autopilot.py could not be read', true);
    return;
  }
  fill('hopping', data.hopping, data.shows, 'shows');
  fill('maintained', data.maintained, data.movies, 'movies');
}

document.querySelectorAll('form.add').forEach(form => form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const input = form.querySelector('input');
  if (await post(form.dataset.kind, input.value, true)) input.value = '';
  await load();
}));

load();
