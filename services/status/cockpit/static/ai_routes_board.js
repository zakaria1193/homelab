// Switchboard view of the AI Routes page: clients (grouped by project) on
// the left, workload classes in the middle, tool tiers and models on the
// right, with SVG cables between them. It edits the same `state` that
// ai_routes.js loads and saves, so the List view and Save keep working
// unchanged; every edit here goes through renderAll().
//
// Node ids: "c:<client id>", "k:<class>", "t:<tool>:<tier>", "m:<tool>:<model>".

const BOARD_TOOL_NAMES = { claude: 'Claude Code', agy: 'Gemini (agy)' };
const BOARD_TIERS = ['low', 'default', 'deep'];
const BOARD_EFFORTS = ['low', 'medium', 'high'];

let boardDrag = null;   // port being dragged: {node, port, x0, y0, moved}
let boardArmed = null;  // port tapped, waiting for a tap on its target
let boardSel = null;    // key of the selected cable
let boardOpen = null;   // node id whose editor is open
let boardNodes = new Map();

function boardTools() {
  const tools = Object.keys(state.models || {});
  return tools.length ? tools : ['claude', 'agy'];
}

function splitClient(id) {
  const at = id.indexOf('@');
  const base = at === -1 ? id : id.slice(0, at);
  const scope = at === -1 ? '' : id.slice(at + 1);
  const colon = base.indexOf(':');
  const project = colon === -1 ? base : base.slice(0, colon);
  const label = colon === -1 ? base : base.slice(colon + 1);
  return { base, scope, project, label };
}

// The class a client runs as: its own `class`, else the one its @scope names.
function clientClass(id, c) {
  return (c && c.class) || splitClient(id).scope || '';
}

function modelTool(model, hint) {
  const avail = state.available_models || {};
  if (hint && (avail[hint] || []).includes(model)) return hint;
  for (const [tool, list] of Object.entries(avail)) {
    if ((list || []).includes(model)) return tool;
  }
  return hint || (String(model).startsWith('gemini-') ? 'agy' : 'claude');
}

// Where a client's override points: a pinned model, else a tool/tier.
function clientTarget(id, c) {
  if (c.model) return 'm:' + modelTool(c.model, c.tool) + ':' + c.model;
  if (!c.tool && !c.tier) return null;
  const cls = state.classes[clientClass(id, c)] || {};
  return 't:' + (c.tool || cls.tool || 'claude') + ':' + (c.tier || cls.tier || 'default');
}

function parseNode(id) {
  const kind = id[0];
  const rest = id.slice(2);
  if (kind === 't' || kind === 'm') {
    const i = rest.indexOf(':');
    return { kind, tool: rest.slice(0, i), name: rest.slice(i + 1) };
  }
  return { kind, name: rest };
}

function boardCables() {
  const out = [];
  const reg = state.project_registry || {};
  for (const [id, c] of Object.entries(state.clients)) {
    const off = reg[splitClient(id).project] && reg[splitClient(id).project].enabled === false;
    const k = clientClass(id, c);
    if (k && state.classes[k]) {
      out.push({ key: 'cls|' + id, kind: splitClient(id).scope ? 'scoped' : 'member', from: 'c:' + id, port: 'out', to: 'k:' + k, off });
    }
    const t = clientTarget(id, c || {});
    if (t) out.push({ key: 'ovr|' + id, kind: 'override', from: 'c:' + id, port: 'out', to: t, off });
  }
  for (const [name, k] of Object.entries(state.classes)) {
    out.push({ key: 'pri|' + name, kind: 'primary', from: 'k:' + name, port: 'pri', to: 't:' + (k.tool || 'claude') + ':' + (k.tier || 'default') });
    const fb = getFirstFallbackStep(k);
    if (fb && fb.tool && fb.model) out.push({ key: 'fb|' + name, kind: 'fallback', from: 'k:' + name, port: 'fb', to: 'm:' + fb.tool + ':' + fb.model });
  }
  return out;
}

function usedModels() {
  const used = new Set();
  for (const k of Object.values(state.classes)) {
    const fb = getFirstFallbackStep(k);
    if (fb && fb.tool && fb.model) used.add(fb.tool + ':' + fb.model);
  }
  for (const [id, c] of Object.entries(state.clients)) {
    if (c && c.model) used.add(modelTool(c.model, c.tool) + ':' + c.model);
  }
  return used;
}

function meterHtml(m) {
  if (typeof m.pct !== 'number') return '';
  const lvl = m.pct >= 95 ? 'danger' : m.pct >= 75 ? 'warn' : 'safe';
  const reset = formatReset(m.reset, 'weekly');
  return `<span class="meter ${lvl}" title="${esc(reset ? 'resets ' + reset : '')}"><span style="width:${Math.min(100, m.pct)}%"></span></span><span class="meter-pct ${lvl}">${m.pct}%</span>`;
}

function toolMeter(tool, model) {
  return meterFromUsage(tool, tool === 'agy' ? inferAgyGroup(model) : null);
}

// --- rendering ------------------------------------------------------------

function clientNodeHtml(id, c) {
  const p = splitClient(id);
  const ovr = [c.tool, c.tier, c.model].filter(Boolean).join(' / ');
  let edit = '';
  if (boardOpen === 'c:' + id) {
    edit = `
      <div class="node-edit">
        ${c.description ? `<div class="muted">${esc(c.description)}</div>` : ''}
        ${c.frequency ? `<div class="muted">${esc(c.frequency)}</div>` : ''}
        <label>Pinned model
          <input class="form-control" list="modelList" placeholder="Inherit from tier" value="${esc(c.model || '')}"
                 onchange="boardSetClientModel(${esc(JSON.stringify(id))}, this.value)">
        </label>
        <label>Effort
          <select class="form-control" onchange="boardSetClientEffort(${esc(JSON.stringify(id))}, this.value)">
            <option value="">inherit</option>
            ${BOARD_EFFORTS.map(e => `<option value="${e}" ${c.effort === e ? 'selected' : ''}>${e}</option>`).join('')}
          </select>
        </label>
        <div class="edit-actions">
          ${ovr ? `<button type="button" class="btn secondary small" onclick="boardClearOverride(${esc(JSON.stringify(id))})">Clear override</button>` : ''}
          <button type="button" class="btn danger small" onclick="boardRemoveClient(${esc(JSON.stringify(id))})">Remove client</button>
        </div>
      </div>`;
  }
  return `
    <div class="node client${ovr ? ' has-ovr' : ''}${boardOpen === 'c:' + id ? ' open' : ''}" data-node="c:${esc(id)}" title="${esc(id)}">
      <div class="node-main">
        <span class="node-name">${esc(p.label)}</span>
        ${p.scope ? `<span class="chip scope">@${esc(p.scope)}</span>` : ''}
      </div>
      ${ovr ? `<div class="node-sub ovr">override: ${esc(ovr)}</div>` : ''}
      ${edit}
      <span class="port out" data-port="out" title="Drag to a class, or to a tier/model to override"></span>
    </div>`;
}

function clientsColumnHtml() {
  const reg = state.project_registry || {};
  const groups = {};
  for (const id of Object.keys(state.clients).sort()) {
    (groups[splitClient(id).project] ||= []).push(id);
  }
  let html = `<div class="col-head">Clients <button type="button" class="btn secondary small" onclick="addClientRow()">+ Add</button></div>`;
  for (const project of Object.keys(groups).sort()) {
    const r = reg[project];
    const off = r && r.enabled === false;
    html += `<div class="proj${off ? ' off' : ''}">
      <div class="proj-head">
        ${r ? `<label title="aicli access on the OptiPlex"><input type="checkbox" ${off ? '' : 'checked'} onchange="setProjectEnabled(${esc(JSON.stringify(project))}, this.checked)"> <strong>${esc(project)}</strong></label>`
            : `<strong>${esc(project)}</strong>`}
        <span class="muted">${off ? 'disabled' : r ? 'enabled' : ''}</span>
      </div>
      ${groups[project].map(id => clientNodeHtml(id, state.clients[id] || {})).join('')}
    </div>`;
  }
  const idle = Object.keys(reg).filter(n => !groups[n]).sort();
  html += `<div class="proj idle"><div class="proj-head"><strong>Registered projects</strong>
      <button type="button" class="btn secondary small" onclick="addProject()">+ Register</button></div>
    <div class="idle-list">${idle.length ? idle.map(n => `
      <label class="idle-chip${reg[n].enabled ? '' : ' off'}"><input type="checkbox" ${reg[n].enabled ? 'checked' : ''}
        onchange="setProjectEnabled(${esc(JSON.stringify(n))}, this.checked)"> ${esc(n)}</label>`).join('')
      : '<span class="muted">Every registered project has clients above.</span>'}</div></div>`;
  return html;
}

function classNodeHtml(name, c) {
  const live = computeClassLiveState(name, c);
  const n = Object.entries(state.clients).filter(([id, cl]) => clientClass(id, cl || {}) === name).length;
  const fb = getFirstFallbackStep(c);
  let edit = '';
  if (boardOpen === 'k:' + name) {
    const jn = esc(JSON.stringify(name));
    edit = `
      <div class="node-edit">
        ${c.description ? `<div class="muted">${esc(c.description)}</div>` : ''}
        ${c.frequency ? `<div class="muted">Frequency: ${esc(c.frequency)}</div>` : ''}
        <label>Effort
          <select class="form-control" onchange="boardSetClassEffort(${jn}, this.value)">
            <option value="">auto</option>
            ${BOARD_EFFORTS.map(e => `<option value="${e}" ${c.effort === e ? 'selected' : ''}>${e}</option>`).join('')}
          </select>
        </label>
        <div class="state-sub">${live.subText}</div>
        ${fb ? `<div class="edit-actions"><button type="button" class="btn secondary small" onclick="boardClearFallback(${jn})">Remove fallback</button></div>` : ''}
      </div>`;
  }
  return `
    <div class="node cls st-${live.state}${boardOpen === 'k:' + name ? ' open' : ''}" data-node="k:${esc(name)}">
      <span class="port in"></span>
      <div class="node-main">
        <span class="dot" title="${esc(live.pillText)}"></span>
        <span class="node-name">${esc(name)}</span>
        ${c.effort ? `<span class="chip">${esc(c.effort)}</span>` : ''}
      </div>
      <div class="node-sub">${esc(live.effectiveText)} · ${n} client${n === 1 ? '' : 's'}</div>
      ${edit}
      <span class="port out pri" data-port="pri" title="Primary route: drag to a tier"></span>
      <span class="port out fb${fb ? '' : ' empty'}" data-port="fb" title="Fallback: drag to a model or tier"></span>
    </div>`;
}

function targetsColumnHtml() {
  const used = usedModels();
  let html = '<div class="col-head">Tools &amp; models</div>';
  for (const tool of boardTools()) {
    const u = state.usage && state.usage[tool];
    const status = !u ? '' : u.state === 'ok' ? '' : `<span class="muted">${esc(u.state || 'unknown')}</span>`;
    html += `<div class="tool"><div class="tool-head"><strong>${esc(BOARD_TOOL_NAMES[tool] || tool)}</strong>${status}</div>`;
    for (const tier of BOARD_TIERS) {
      const model = getModelName(tool, tier);
      html += `
        <div class="node tier" data-node="t:${esc(tool)}:${tier}">
          <span class="port in"></span>
          <div class="node-main"><span class="node-name">${tier}</span>${meterHtml(toolMeter(tool, model))}</div>
          <div class="node-sub mono">${esc(model)}</div>
        </div>`;
    }
    const models = [...new Set([...(state.available_models[tool] || []),
      ...[...used].filter(k => k.startsWith(tool + ':')).map(k => k.slice(tool.length + 1))])];
    html += `<div class="models">`;
    for (const model of models) {
      const isUsed = used.has(tool + ':' + model);
      html += `
        <div class="node model${isUsed ? '' : ' unused'}" data-node="m:${esc(tool)}:${esc(model)}">
          <span class="port in"></span>
          <div class="node-main"><span class="node-name mono">${esc(model)}</span>${meterHtml(toolMeter(tool, model))}</div>
        </div>`;
    }
    html += `</div></div>`;
  }
  return html;
}

function renderBoard() {
  const board = document.getElementById('board');
  if (!board) return;
  const classes = Object.entries(state.classes).sort(([a], [b]) => a.localeCompare(b));
  board.innerHTML = `
    <svg class="cables" id="cables" aria-hidden="true"></svg>
    <div class="col col-clients">${clientsColumnHtml()}</div>
    <div class="col col-classes"><div class="col-head">Classes</div>${classes.map(([n, c]) => classNodeHtml(n, c)).join('')}</div>
    <div class="col col-targets">${targetsColumnHtml()}</div>
    <div id="cableMenu" class="cable-menu" style="display:none;"></div>`;
  boardNodes = new Map();
  board.querySelectorAll('[data-node]').forEach(el => boardNodes.set(el.dataset.node, el));
  if (boardArmed) board.dataset.drag = dragKind(boardArmed);
  drawCables();
}

// --- cables ---------------------------------------------------------------

function anchor(el, side, origin) {
  const r = el.getBoundingClientRect();
  return { x: (side === 'right' ? r.right : r.left) - origin.left, y: r.top + r.height / 2 - origin.top };
}

function cablePath(a, b) {
  const dx = Math.max(40, Math.abs(b.x - a.x) * 0.45);
  return `M${a.x},${a.y} C${a.x + dx},${a.y} ${b.x - dx},${b.y} ${b.x},${b.y}`;
}

function drawCables() {
  const board = document.getElementById('board');
  const svg = document.getElementById('cables');
  if (!board || !svg || !board.offsetWidth) return;
  const origin = board.getBoundingClientRect();
  svg.setAttribute('width', board.scrollWidth);
  svg.setAttribute('height', board.scrollHeight);
  let html = '';
  let selMid = null;
  for (const cab of boardCables()) {
    const src = boardNodes.get(cab.from);
    const dst = boardNodes.get(cab.to);
    if (!src || !dst || !dst.offsetParent) continue;
    const port = src.querySelector(`.port[data-port="${cab.port}"]`) || src;
    const a = anchor(port, 'right', origin);
    const b = anchor(dst, 'left', origin);
    const d = cablePath(a, b);
    const sel = boardSel === cab.key;
    if (sel) selMid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, cab };
    html += `<g class="cable ${cab.kind}${cab.off ? ' off' : ''}${sel ? ' sel' : ''}" data-key="${esc(cab.key)}" data-a="${esc(cab.from)}" data-b="${esc(cab.to)}">
      <path class="hit" d="${d}"></path><path class="wire" d="${d}"></path></g>`;
  }
  html += '<path id="ghost" class="ghost" d=""></path>';
  svg.innerHTML = html;
  const menu = document.getElementById('cableMenu');
  if (menu) {
    if (selMid) {
      menu.style.left = selMid.x + 'px';
      menu.style.top = selMid.y + 'px';
      menu.innerHTML = cableMenuHtml(selMid.cab);
      menu.style.display = '';
    } else {
      menu.style.display = 'none';
    }
  }
}

function cableMenuHtml(cab) {
  const [kind, name] = [cab.key.slice(0, cab.key.indexOf('|')), cab.key.slice(cab.key.indexOf('|') + 1)];
  const text = {
    pri: `${name}: primary route. Drag its top dot to a tier to change it.`,
    fb: `${name}: fallback when the primary is ≥${(state.fallback_status && state.fallback_status.at) || 95}% used.`,
    cls: `${name} runs as ${clientClass(name, state.clients[name] || {})}.`,
    ovr: `${name} overrides its class's route.`,
  }[kind];
  const btn = kind === 'pri' ? '' :
    `<button type="button" class="btn danger small" onclick="boardRemoveCable(${esc(JSON.stringify(cab.key))})">✕ Remove</button>`;
  return `<div>${esc(text)}</div>${btn}`;
}

// --- editing ----------------------------------------------------------------

function boardChanged() {
  setDirty(true);
  renderAll();
}

function boardConnect(src, dstId) {
  const dst = parseNode(dstId);
  const s = parseNode(src.node);
  if (s.kind === 'c') {
    const id = s.name;
    const c = state.clients[id] || {};
    if (dst.kind === 'k') {
      const p = splitClient(id);
      if (p.scope) {
        // A class-scoped id names its class: rewiring it renames the id.
        const newId = p.base + '@' + dst.name;
        if (newId === id) return;
        if (state.clients[newId]) { banner(`${newId} already exists.`, true); return; }
        state.clients[newId] = c;
        delete state.clients[id];
      } else {
        c.class = dst.name;
        state.clients[id] = c;
      }
    } else if (dst.kind === 't') {
      c.tool = dst.tool;
      c.tier = dst.name;
      delete c.model;
      state.clients[id] = c;
    } else if (dst.kind === 'm') {
      c.tool = dst.tool;
      c.model = dst.name;
      delete c.tier;
      state.clients[id] = c;
    } else {
      return;
    }
  } else if (s.kind === 'k') {
    const cls = state.classes[s.name];
    if (!cls) return;
    if (src.port === 'pri') {
      if (dst.kind !== 't') {
        banner('A class routes to a tier. Drop its primary cable on low, default or deep; models take its fallback cable.', true);
        return;
      }
      cls.tool = dst.tool;
      cls.tier = dst.name;
    } else if (src.port === 'fb') {
      if (dst.kind !== 't' && dst.kind !== 'm') return;
      const model = dst.kind === 'm' ? dst.name : getModelName(dst.tool, dst.name);
      cls.fallback = { tool: dst.tool, model, ...(dst.tool === 'agy' ? { group: inferAgyGroup(model) } : {}) };
    }
  } else {
    return;
  }
  boardChanged();
}

function boardRemoveCable(key) {
  const i = key.indexOf('|');
  const kind = key.slice(0, i);
  const name = key.slice(i + 1);
  const c = state.clients[name];
  if (kind === 'fb' && state.classes[name]) {
    state.classes[name].fallback = null;
  } else if (kind === 'ovr' && c) {
    delete c.tool; delete c.tier; delete c.model;
  } else if (kind === 'cls' && c) {
    if (splitClient(name).scope) {
      if (!confirm(`Delete the class-scoped override ${name}?`)) return;
      delete state.clients[name];
    } else {
      delete c.class;
    }
  }
  boardSel = null;
  boardChanged();
}

function boardSetClassEffort(name, v) {
  const c = state.classes[name];
  if (!c) return;
  if (v) c.effort = v; else delete c.effort;
  boardChanged();
}

function boardClearFallback(name) {
  if (state.classes[name]) state.classes[name].fallback = null;
  boardChanged();
}

function boardSetClientModel(id, v) {
  const c = state.clients[id];
  if (!c) return;
  v = v.trim();
  if (v) { c.model = v; c.tool = modelTool(v, c.tool); delete c.tier; } else { delete c.model; }
  boardChanged();
}

function boardSetClientEffort(id, v) {
  const c = state.clients[id];
  if (!c) return;
  if (v) c.effort = v; else delete c.effort;
  boardChanged();
}

function boardClearOverride(id) {
  const c = state.clients[id];
  if (!c) return;
  delete c.tool; delete c.tier; delete c.model;
  boardChanged();
}

function boardRemoveClient(id) {
  if (!confirm(`Remove client ${id} from routes.json?`)) return;
  boardOpen = null;
  removeClient(id);
}

// --- pointer handling -------------------------------------------------------

function dragKind(d) {
  return d.node.startsWith('c:') ? 'client' : d.port;
}

function nodeAt(x, y) {
  const el = document.elementFromPoint(x, y);
  return el && el.closest('#board [data-node]');
}

function disarm() {
  boardArmed = null;
  const board = document.getElementById('board');
  if (board) delete board.dataset.drag;
  document.querySelectorAll('#board .port.armed').forEach(p => p.classList.remove('armed'));
  drawCables();
}

function onBoardPointerDown(e) {
  const port = e.target.closest('#board .port.out');
  if (!port) return;
  e.preventDefault();
  const node = port.closest('[data-node]');
  boardDrag = { node: node.dataset.node, port: port.dataset.port, x0: e.clientX, y0: e.clientY, moved: false, el: port };
  port.setPointerCapture(e.pointerId);
  const board = document.getElementById('board');
  board.dataset.drag = dragKind(boardDrag);
  boardSel = null;
  drawCables();
}

// Near the top or bottom edge while dragging, scroll so a far card is reachable.
function dragAutoScroll() {
  const d = boardDrag;
  if (!d || !d.moved) return;
  const edge = 48;
  const y = d.lastY;
  const dy = y < edge ? -(edge - y) / 2 : y > window.innerHeight - edge ? (y - window.innerHeight + edge) / 2 : 0;
  if (dy) {
    window.scrollBy(0, dy);
    drawGhost(d.lastX, d.lastY);
  }
  requestAnimationFrame(dragAutoScroll);
}

function drawGhost(x, y) {
  const board = document.getElementById('board');
  const origin = board.getBoundingClientRect();
  const ghost = document.getElementById('ghost');
  if (ghost) ghost.setAttribute('d', cablePath(anchor(boardDrag.el, 'right', origin), { x: x - origin.left, y: y - origin.top }));
  board.querySelectorAll('.drop-hot').forEach(n => n.classList.remove('drop-hot'));
  const hot = nodeAt(x, y);
  if (hot) hot.classList.add('drop-hot');
}

function onBoardPointerMove(e) {
  if (!boardDrag) return;
  boardDrag.lastX = e.clientX;
  boardDrag.lastY = e.clientY;
  if (!boardDrag.moved && Math.hypot(e.clientX - boardDrag.x0, e.clientY - boardDrag.y0) > 6) {
    boardDrag.moved = true;
    requestAnimationFrame(dragAutoScroll);
  }
  if (!boardDrag.moved) return;
  drawGhost(e.clientX, e.clientY);
}

function onBoardPointerUp(e) {
  if (!boardDrag) return;
  const d = boardDrag;
  boardDrag = null;
  if (d.moved) {
    const target = nodeAt(e.clientX, e.clientY);
    const board = document.getElementById('board');
    delete board.dataset.drag;
    board.querySelectorAll('.drop-hot').forEach(n => n.classList.remove('drop-hot'));
    if (target && target.dataset.node !== d.node) boardConnect(d, target.dataset.node);
    drawCables();
    return;
  }
  // A tap on a port arms it; the next tap on a card connects.
  if (boardArmed && boardArmed.node === d.node && boardArmed.port === d.port) { disarm(); return; }
  boardArmed = { node: d.node, port: d.port };
  d.el.classList.add('armed');
  banner('Now tap the card to connect it to (tap the dot again to cancel).');
}

function onBoardClick(e) {
  const board = document.getElementById('board');
  if (e.target.closest('.port.out') || e.target.closest('.node-edit') || e.target.closest('.cable-menu')
      || e.target.closest('input, select, button, label')) return;
  const node = e.target.closest('[data-node]');
  if (boardArmed) {
    const armed = boardArmed;
    if (node && node.dataset.node !== armed.node) {
      boardArmed = null;
      delete board.dataset.drag;
      boardConnect(armed, node.dataset.node);
    } else {
      disarm();
    }
    return;
  }
  const cable = e.target.closest('.cable');
  if (cable) {
    boardSel = boardSel === cable.dataset.key ? null : cable.dataset.key;
    drawCables();
    return;
  }
  if (node && (node.dataset.node.startsWith('k:') || node.dataset.node.startsWith('c:'))) {
    boardOpen = boardOpen === node.dataset.node ? null : node.dataset.node;
    boardSel = null;
    renderBoard();
    return;
  }
  if (boardSel) { boardSel = null; drawCables(); }
}

// Hovering a card lights up its cables.
function onBoardHover(e) {
  const node = e.target.closest('[data-node]');
  const id = node ? node.dataset.node : '';
  document.querySelectorAll('#cables .cable').forEach(g => {
    g.classList.toggle('hot', !!id && (g.dataset.a === id || g.dataset.b === id));
  });
}

// --- view switch ------------------------------------------------------------

function setView(view) {
  try { localStorage.setItem('ai_routes_view', view); } catch (e) { /* private window */ }
  document.getElementById('boardView').style.display = view === 'board' ? '' : 'none';
  document.getElementById('listView').style.display = view === 'list' ? '' : 'none';
  document.querySelectorAll('.seg [data-view]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.view === view)));
  document.body.dataset.view = view;
  if (view === 'board') renderBoard();
}

document.addEventListener('DOMContentLoaded', () => {
  let view = null;
  try { view = localStorage.getItem('ai_routes_view'); } catch (e) { /* private window */ }
  // Phones get the list of selects; the board needs room for three columns.
  setView(view || (window.innerWidth >= 860 ? 'board' : 'list'));
  const board = document.getElementById('board');
  board.addEventListener('pointerdown', onBoardPointerDown);
  board.addEventListener('pointermove', onBoardPointerMove);
  board.addEventListener('pointerup', onBoardPointerUp);
  board.addEventListener('pointercancel', () => { boardDrag = null; disarm(); });
  board.addEventListener('click', onBoardClick);
  board.addEventListener('mouseover', onBoardHover);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { boardSel = null; disarm(); } });
  if (window.ResizeObserver) new ResizeObserver(() => drawCables()).observe(board);
});
