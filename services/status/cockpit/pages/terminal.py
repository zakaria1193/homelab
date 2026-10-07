"""/terminal: a browser shell (xterm.js over a WebSocket)."""

from .theme import THEME

TERMINAL_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, interactive-widget=resizes-content">
<title>__NAME__ shell · __TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.min.css">
<style>
  {THEME}
  html, body { height: 100%; }
  body { display: flex; flex-direction: column; height: 100vh; height: var(--vvh, 100dvh);
    overflow: hidden; }
  header { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px;
    padding: 12px 16px 10px; flex: none; }
  h1 { font-size: 17px; margin: 0; }
  .back { color: var(--muted); text-decoration: none; font-size: 13px; }
  .back:hover { color: var(--text); }
  .cmd { color: var(--muted); font-size: 12px; font-family: ui-monospace, SFMono-Regular,
    Menlo, Consolas, monospace; overflow-wrap: anywhere; }
  .font-controls { display: inline-flex; align-items: center; gap: 4px; }
  .font-size-val { font-size: 11px; color: var(--muted); min-width: 32px; text-align: center; }
  .state { margin-left: auto; font-size: 12px; color: var(--muted); }
  .state.live { color: var(--up); }
  .state.gone { color: var(--down); }
  #term { flex: 1 1 0; min-height: 0; margin: 0 12px 12px; padding: 4px;
    background: #fdfdfd; border: 1px solid var(--border); border-radius: 8px;
    position: relative; overflow: hidden; box-sizing: border-box; }
  .xterm { height: 100% !important; width: 100% !important; padding: 0 !important; }
  .xterm .xterm-viewport { overflow-y: auto !important; }
  .xterm .xterm-screen { width: 100% !important; }
  button { background: var(--panel); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 3px 9px; font-size: 12px; cursor: pointer; }
  button:hover { border-color: var(--muted); }
  .btn-close { background: var(--panel); border-color: var(--border); color: var(--down); font-weight: 500; }
  .btn-close:hover { background: #b62324; color: #fff; border-color: #d03030; }
  .warn { padding: 10px 20px; color: var(--muted); font-size: 13px; }

  /* Extra keys for touch screens, which have no Esc/Ctrl/Alt/arrows */
  #keybar { display: none; flex: none; grid-template-columns: repeat(8, minmax(0, 1fr));
    gap: 4px; padding: 0 8px 6px; }
  #keybar button { min-width: 0; padding: 7px 0; font-size: 13px; overflow: hidden;
    white-space: nowrap; touch-action: manipulation;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  #keybar button.armed { background: var(--accent); border-color: var(--accent); color: #fff; }
  @media (pointer: coarse) {
    #keybar { display: grid; }
    #term { margin-bottom: 8px; }
    /* The keyboard leaves little room: give it all to the terminal */
    body.kb-open header { display: none; }
  }

  /* Tmux Sessions Bar in Header */
  .tmux-bar { display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .session-tag { display: inline-flex; align-items: center; background: var(--panel);
    border: 1px solid var(--border); border-radius: 999px; padding: 2px 9px 2px 10px;
    font-size: 12px; color: var(--muted); text-decoration: none; max-width: 220px;
    transition: all 0.15s ease; }
  .session-tag:hover { border-color: var(--muted); background: var(--raise); color: var(--text); }
  .session-tag.active { border-color: var(--accent); color: var(--text); background: var(--raise); font-weight: 600; }
  .session-tag .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--warn); margin-right: 6px; flex: none; }
  .session-tag .dot.up { background: var(--up); }
  .session-tag .sname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .btn-new-sess { background: var(--panel); border: 1px dashed var(--accent); color: var(--accent);
    border-radius: 999px; padding: 2px 10px; font-size: 12px; cursor: pointer; display: inline-flex;
    align-items: center; gap: 4px; font-weight: 500; }
  .btn-new-sess:hover { background: var(--raise); border-color: var(--accent); }
  .title-wrap { display: inline-flex; align-items: center; gap: 6px; }
  .btn-rename-direct { background: transparent; border: 1px solid transparent; color: var(--muted);
    border-radius: 4px; padding: 1px 5px; font-size: 11px; cursor: pointer; }
  .btn-rename-direct:hover { border-color: var(--border); background: var(--raise); color: var(--text); }
  .btn-kill-direct { background: transparent; border: 1px solid transparent; color: var(--warn);
    border-radius: 4px; padding: 1px 5px; font-size: 11px; cursor: pointer; }
  .btn-kill-direct:hover { border-color: #d03030; background: rgba(208,48,48,0.15); color: #ff6b6b; }

  /* Confirmation Modal */
  .modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: flex;
    align-items: center; justify-content: center; z-index: 1000; backdrop-filter: blur(2px); }
  .modal-dialog { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 20px 22px; max-width: 440px; width: 90%; box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
  .modal-dialog h2 { margin: 0 0 10px; font-size: 16px; color: var(--text); }
  .modal-dialog p { margin: 0 0 18px; font-size: 13px; color: var(--muted); line-height: 1.5; }
  .modal-dialog code { font-size: 12px; color: var(--accent); background: var(--raise);
    padding: 2px 5px; border-radius: 4px; }
  .modal-actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; align-items: center; }
  .btn-danger { background: #b62324; border: 1px solid #d03030; color: #fff; padding: 6px 14px;
    border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; }
  .btn-danger:hover { background: #d03030; }
  .btn-secondary { background: var(--raise); border: 1px solid var(--border); color: var(--text);
    padding: 6px 14px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; }
  .btn-secondary:hover { border-color: var(--muted); }
  .btn-ghost { background: transparent; border: 1px solid transparent; color: var(--muted);
    padding: 6px 10px; border-radius: 6px; font-size: 13px; cursor: pointer; }
  .btn-ghost:hover { color: var(--text); }
</style>
</head>
<body>
<header>
  <a class="back" id="backAll" href="/">&larr; All services</a>
  <a class="back" id="backTmux" href="/tmux">Tmux sessions</a>
  <div class="title-wrap">
    <h1 id="pageTitle">__NAME__</h1>
    <button id="directRenameBtn" type="button" class="btn-rename-direct" title="Rename this tmux session">rename</button>
    <button id="directKillBtn" type="button" class="btn-kill-direct" title="Kill this session immediately without confirmation">kill</button>
  </div>
  <div class="tmux-bar" id="tmuxBar"></div>
  <button id="newTmuxBtn" type="button" class="btn-new-sess" title="Start new session at ~">+ New at ~</button>
  <div class="font-controls">
    <button id="fontDec" type="button" title="Decrease font size">A−</button>
    <span id="fontSizeLabel" class="font-size-val">15px</span>
    <button id="fontInc" type="button" title="Increase font size">A+</button>
  </div>
  <span class="state" id="state">connecting…</span>
  <button id="again" type="button" style="display:none">Reconnect</button>
  <button id="closeBtn" type="button" class="btn-close" title="Close terminal session">Close session</button>
</header>
<div id="term"></div>
<div id="keybar">
  <button type="button" data-key="esc">Esc</button>
  <button type="button" data-key="tab">Tab</button>
  <button type="button" data-mod="ctrl">Ctrl</button>
  <button type="button" data-mod="alt">Alt</button>
  <button type="button" data-key="left">&larr;</button>
  <button type="button" data-key="down">&darr;</button>
  <button type="button" data-key="up">&uarr;</button>
  <button type="button" data-key="right">&rarr;</button>
  <button type="button" data-key="ctrl-c">^C</button>
  <button type="button" data-key="ctrl-b" title="tmux prefix">^B</button>
  <button type="button" data-key="pgup">PgUp</button>
  <button type="button" data-key="pgdn">PgDn</button>
  <button type="button" data-key="home">Home</button>
  <button type="button" data-key="end">End</button>
  <button type="button" data-text="|">|</button>
  <button type="button" data-text="~">~</button>
</div>

<div id="closeModal" class="modal-backdrop" style="display:none" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
  <div class="modal-dialog">
    <h2 id="modalTitle">Close Terminal Session</h2>
    <p id="modalPrompt">Do you want to exit and kill this tmux session, or keep it running in the background?</p>
    <div id="modalRenameWrap" style="margin: 12px 0 16px; display: none;">
      <label for="bgRenameInput" style="display:block;font-size:12px;color:var(--muted);margin-bottom:4px;">Session name (rename before keeping in background):</label>
      <input id="bgRenameInput" style="width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 9px;font:inherit;font-size:14px;" placeholder="name">
    </div>
    <div class="modal-actions">
      <button id="modalCancelBtn" type="button" class="btn-ghost">Cancel</button>
      <button id="modalBgBtn" type="button" class="btn-secondary">Keep in bg</button>
      <button id="modalKillBtn" type="button" class="btn-danger">Exit &amp; kill session</button>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.min.js"></script>
<script>
let activeService = "__SERVICE__";
let currentSessionParam = "__SESSION__";
let currentTmuxSession = "__TMUX_SESSION__";
const where = "__WHERE__";
let activeCmd = "__CMD__";
const pageTitleEl = document.getElementById("pageTitle");
const directRenameBtn = document.getElementById("directRenameBtn");
const directKillBtn = document.getElementById("directKillBtn");
const tmuxBarEl = document.getElementById("tmuxBar");
const newTmuxBtn = document.getElementById("newTmuxBtn");
const stateEl = document.getElementById("state");
const againEl = document.getElementById("again");
const fontSizeLabel = document.getElementById("fontSizeLabel");
const fontDecBtn = document.getElementById("fontDec");
const fontIncBtn = document.getElementById("fontInc");
const closeBtn = document.getElementById("closeBtn");
const closeModal = document.getElementById("closeModal");
const modalPrompt = document.getElementById("modalPrompt");
const modalKillBtn = document.getElementById("modalKillBtn");
const modalBgBtn = document.getElementById("modalBgBtn");
const modalCancelBtn = document.getElementById("modalCancelBtn");
const bgRenameInput = document.getElementById("bgRenameInput");
const modalRenameWrap = document.getElementById("modalRenameWrap");
const backAll = document.getElementById("backAll");
const backTmux = document.getElementById("backTmux");

let socket = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
let pingInterval = null;
let intentionalClose = false;
let sessionTerminated = false;
let term = null;
let targetUrl = "/";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const qs = encodeURIComponent;

const post = async (path, body) => {
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return await res.json();
  } catch (err) {
    return { ok: false, message: String(err) };
  }
};

let pingTimerId = null;
let pingWorker = null;

try {
  const pingBlob = new Blob([
    "let t=null;self.onmessage=e=>{if(e.data==='start'){if(!t)t=setInterval(()=>self.postMessage('p'),10000);}else{clearInterval(t);t=null;}};"
  ], { type: "application/javascript" });
  pingWorker = new Worker(URL.createObjectURL(pingBlob));
  pingWorker.onmessage = () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ ping: 1 }));
    }
  };
} catch (_) {
  pingWorker = null;
}

function startPing() {
  if (pingWorker) {
    pingWorker.postMessage("start");
  } else if (!pingTimerId) {
    pingTimerId = setInterval(() => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ ping: 1 }));
      }
    }, 10000);
  }
}

function clearPing() {
  if (pingWorker) {
    pingWorker.postMessage("stop");
  }
  if (pingTimerId) {
    clearInterval(pingTimerId);
    pingTimerId = null;
  }
}

async function renameCurrentSessionDirectly() {
  const targetSession = currentTmuxSession || currentSessionParam;
  if (!targetSession) {
    alert("No active tmux session to rename.");
    return;
  }
  const currentShort = targetSession.startsWith("cockpit-") ? targetSession.slice(8) : targetSession;
  const newName = prompt(`Rename tmux session "${targetSession}":`, currentShort);
  if (!newName || !newName.trim() || newName.trim() === currentShort || newName.trim() === targetSession) {
    return;
  }
  const cleanNew = newName.trim();
  directRenameBtn.disabled = true;
  directRenameBtn.textContent = "renaming…";
  const res = await post("/api/tmux/rename", { session: targetSession, name: cleanNew });
  directRenameBtn.disabled = false;
  directRenameBtn.textContent = "rename";
  if (!res || !res.ok) {
    alert(res && res.message ? res.message : "Failed to rename session.");
    return;
  }
  const newFullName = res.session || (cleanNew.startsWith("cockpit-") ? cleanNew : "cockpit-" + cleanNew);
  currentTmuxSession = newFullName;
  currentSessionParam = newFullName;
  const newShort = newFullName.startsWith("cockpit-") ? newFullName.slice(8) : newFullName;
  if (pageTitleEl) pageTitleEl.textContent = newShort;
  const url = new URL(window.location.href);
  url.searchParams.delete("service");
  url.searchParams.set("session", newFullName);
  window.history.replaceState({}, "", url.toString());
  loadTmuxBar();
}

directRenameBtn.addEventListener("click", renameCurrentSessionDirectly);

async function killCurrentSessionDirectly() {
  const targetSession = currentTmuxSession || currentSessionParam;
  if (!targetSession) {
    alert("No active tmux session to kill.");
    return;
  }
  directKillBtn.disabled = true;
  directKillBtn.textContent = "killing…";
  intentionalClose = true;
  clearPing();
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (socket) {
    try { socket.close(); } catch (_) {}
    socket = null;
  }
  try {
    await Promise.race([
      post("/api/tmux/kill", { session: targetSession }),
      new Promise((resolve) => setTimeout(resolve, 1500)),
    ]);
  } catch (_) {}
  window.location.href = "/tmux";
}

directKillBtn.addEventListener("click", killCurrentSessionDirectly);

function switchToSession(targetSession) {
  if (!targetSession) return;
  const fullTarget = targetSession.startsWith("cockpit-") ? targetSession : "cockpit-" + targetSession;
  if (currentTmuxSession === fullTarget && currentSessionParam === fullTarget && socket && socket.readyState === WebSocket.OPEN) return;

  intentionalClose = true;
  clearPing();
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (socket) {
    const oldSock = socket;
    socket = null;
    oldSock.onclose = null;
    oldSock.onerror = null;
    oldSock.onmessage = null;
    try { oldSock.close(); } catch (_) {}
  }
  intentionalClose = false;
  sessionTerminated = false;
  reconnectAttempts = 0;

  currentTmuxSession = fullTarget;
  currentSessionParam = fullTarget;
  activeService = "";
  activeCmd = "";

  const short = fullTarget.startsWith("cockpit-") ? fullTarget.slice(8) : fullTarget;
  if (pageTitleEl) pageTitleEl.textContent = short;
  document.title = `${short} shell · __TITLE__`;

  const url = new URL(window.location.href);
  url.searchParams.delete("service");
  url.searchParams.delete("cmd");
  url.searchParams.set("session", fullTarget);
  window.history.pushState({ session: fullTarget }, "", url.toString());

  if (term) {
    term.reset();
  }
  loadTmuxBar();
  connect();
}

window.addEventListener("popstate", () => {
  const url = new URL(window.location.href);
  const sess = url.searchParams.get("session");
  if (sess && sess !== currentTmuxSession) {
    switchToSession(sess);
  }
});

newTmuxBtn.addEventListener("click", async () => {
  const rawName = prompt("New session name (leave empty for auto):", "");
  if (rawName === null) return;
  const name = rawName.trim() || ("session-" + Math.floor(Date.now() / 1000).toString().slice(-4));
  newTmuxBtn.disabled = true;
  newTmuxBtn.textContent = "Creating…";
  const res = await post("/api/tmux/create", { name, cwd: "~" });
  newTmuxBtn.disabled = false;
  newTmuxBtn.textContent = "+ New at ~";
  if (res && res.ok && res.session) {
    switchToSession(res.session);
  } else {
    alert(res && res.message ? res.message : "Failed to create session.");
  }
});

tmuxBarEl.addEventListener("click", (e) => {
  const tag = e.target.closest("a.session-tag");
  if (!tag) return;
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  const target = tag.dataset.session;
  if (target) switchToSession(target);
});

async function loadTmuxBar() {
  try {
    const res = await fetch("/api/tmux", { cache: "no-store" });
    const data = await res.json();
    if (!data || !data.sessions) return;
    const activeFullName = currentTmuxSession || (currentSessionParam ? (currentSessionParam.startsWith("cockpit-") ? currentSessionParam : "cockpit-" + currentSessionParam) : "");
    const html = data.sessions.map(s => {
      const isCurrent = !sessionTerminated && ((activeFullName && s.name === activeFullName) || (s.name === currentTmuxSession));
      const short = s.name.startsWith(data.prefix || "cockpit-") ? s.name.slice((data.prefix || "cockpit-").length) : s.name;
      const dotCls = s.attached ? "dot up" : "dot";
      const titleText = `${s.name} (${s.attached ? "attached" : "detached"}, created ${s.created_human})`;
      if (isCurrent) {
        return `<span class="session-tag active" title="${esc(titleText)}"><span class="${dotCls}"></span><span class="sname">${esc(short)}</span></span>`;
      }
      return `<a class="session-tag" href="/terminal?session=${qs(s.name)}" data-session="${esc(s.name)}" title="${esc(titleText)}"><span class="${dotCls}"></span><span class="sname">${esc(short)}</span></a>`;
    }).join("");
    tmuxBarEl.innerHTML = html;
  } catch (_) {}
}

loadTmuxBar();
setInterval(loadTmuxBar, 4000);

function showCloseModal(target) {
  targetUrl = target || "/";
  if (currentTmuxSession) {
    modalPrompt.innerHTML = `Do you want to exit and terminate tmux session <code>${esc(currentTmuxSession)}</code>, or keep it running in the background?`;
    modalBgBtn.style.display = "";
    if (modalRenameWrap && bgRenameInput) {
      modalRenameWrap.style.display = "";
      bgRenameInput.value = currentTmuxSession.startsWith("cockpit-") ? currentTmuxSession.slice(8) : currentTmuxSession;
    }
  } else {
    modalPrompt.textContent = "Do you want to close this terminal session?";
    modalBgBtn.style.display = "none";
    if (modalRenameWrap) modalRenameWrap.style.display = "none";
  }
  closeModal.style.display = "flex";
  modalKillBtn.disabled = false;
  modalKillBtn.textContent = "Exit & kill session";
  modalBgBtn.disabled = false;
  modalCancelBtn.disabled = false;
  modalKillBtn.focus();
}

function hideCloseModal() {
  closeModal.style.display = "none";
  if (term) {
    try { term.focus(); } catch (_) {}
  }
}

closeBtn.addEventListener("click", () => showCloseModal("/"));
if (backAll) backAll.addEventListener("click", () => {
  intentionalClose = true;
});
if (backTmux) backTmux.addEventListener("click", () => {
  intentionalClose = true;
});

modalCancelBtn.addEventListener("click", hideCloseModal);
closeModal.addEventListener("click", (e) => {
  if (e.target === closeModal) hideCloseModal();
});
document.addEventListener("keydown", (e) => {
  if (closeModal.style.display !== "none" && e.key === "Escape") {
    hideCloseModal();
  }
});

modalKillBtn.addEventListener("click", async () => {
  modalKillBtn.disabled = true;
  modalBgBtn.disabled = true;
  modalCancelBtn.disabled = true;
  modalKillBtn.textContent = "Terminating…";
  intentionalClose = true;
  clearPing();
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (socket) {
    try { socket.close(); } catch (_) {}
    socket = null;
  }
  if (currentTmuxSession) {
    try {
      await Promise.race([
        post("/api/tmux/kill", { session: currentTmuxSession }),
        new Promise((resolve) => setTimeout(resolve, 1500)),
      ]);
    } catch (_) {}
  }
  window.location.href = targetUrl;
});

modalBgBtn.addEventListener("click", async () => {
  modalKillBtn.disabled = true;
  modalBgBtn.disabled = true;
  modalCancelBtn.disabled = true;
  modalBgBtn.textContent = "Saving…";
  intentionalClose = true;
  clearPing();
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (socket) {
    try { socket.close(); } catch (_) {}
    socket = null;
  }
  if (currentTmuxSession && bgRenameInput) {
    const rawNew = bgRenameInput.value.trim();
    const currentShort = currentTmuxSession.startsWith("cockpit-") ? currentTmuxSession.slice(8) : currentTmuxSession;
    if (rawNew && rawNew !== currentTmuxSession && rawNew !== currentShort) {
      try {
        await post("/api/tmux/rename", { session: currentTmuxSession, name: rawNew });
      } catch (_) {}
    }
  }
  window.location.href = targetUrl;
});

if (typeof Terminal === "undefined") {
  document.getElementById("term").innerHTML =
    '<div class="warn">Could not load xterm.js from the CDN, so the terminal ' +
    'cannot render. This page needs outbound access to cdn.jsdelivr.net.</div>';
  stateEl.textContent = "unavailable";
} else {
  const savedFontSize = parseInt(localStorage.getItem("status_term_font_size") || "15", 10);
  let currentFontSize = (!isNaN(savedFontSize) && savedFontSize >= 10 && savedFontSize <= 28) ? savedFontSize : 15;
  fontSizeLabel.textContent = currentFontSize + "px";

  term = new Terminal({
    fontSize: currentFontSize,
    lineHeight: 1.15,
    cursorBlink: true,
    scrollback: 10000,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
    theme: {
      background: "#fdfdfd", foreground: "#1d1d1f", cursor: "#1d1d1f",
      selectionBackground: "rgba(21, 91, 208, 0.25)",
      black: "#1d1d1f", red: "#c7342d", green: "#1a7f37", yellow: "#9a6700",
      blue: "#155bd0", magenta: "#8250df", cyan: "#0d7490", white: "#6e6e73",
      brightBlack: "#86868b", brightRed: "#d53f3f", brightGreen: "#1a9c4b",
      brightYellow: "#b9770e", brightBlue: "#2f6fe0", brightMagenta: "#a26fe0",
      brightCyan: "#1398b5", brightWhite: "#1d1d1f",
    },
    allowTransparency: true,
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(document.getElementById("term"));
  document.getElementById("term").addEventListener("click", () => {
    if (term) term.focus();
  });

  function safeFit() {
    try {
      fit.fit();
      sendResize();
    } catch (_) {}
  }

  function setFontSize(newSize) {
    currentFontSize = Math.max(10, Math.min(28, newSize));
    term.options.fontSize = currentFontSize;
    fontSizeLabel.textContent = currentFontSize + "px";
    localStorage.setItem("status_term_font_size", currentFontSize);
    safeFit();
  }

  fontDecBtn.addEventListener("click", () => setFontSize(currentFontSize - 1));
  fontIncBtn.addEventListener("click", () => setFontSize(currentFontSize + 1));

  function setState(text, cls) {
    stateEl.textContent = text;
    stateEl.className = "state" + (cls ? " " + cls : "");
  }

  function sendResize() {
    if (socket && socket.readyState === WebSocket.OPEN && term.cols && term.rows) {
      socket.send(JSON.stringify({ resize: [term.cols, term.rows] }));
    }
  }

  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => {
      safeFit();
    });
    ro.observe(document.getElementById("term"));
  }
  window.addEventListener("resize", safeFit);

  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(safeFit);
  }

  requestAnimationFrame(() => {
    safeFit();
    setTimeout(safeFit, 100);
  });

  function scheduleReconnect() {
    if (intentionalClose || sessionTerminated || reconnectTimer) return;
    reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempts - 1), 10000);
    const delaySec = Math.max(1, Math.round(delay / 1000));
    setState(`disconnected · reconnecting in ${delaySec}s…`, "gone");
    againEl.textContent = "Reconnect";
    againEl.style.display = "";
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, delay);
  }

  async function connect(forceCreate) {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    clearPing();
    if (socket) {
      try { socket.close(); } catch (_) {}
      socket = null;
    }
    againEl.style.display = "none";
    setState("connecting…");
    let ticket;
    try {
      const q = new URLSearchParams();
      if (activeService && !currentSessionParam) q.set("service", activeService);
      if (currentSessionParam || currentTmuxSession) q.set("session", currentSessionParam || currentTmuxSession);
      if (where) q.set("where", where);
      if (activeCmd && !currentSessionParam) q.set("cmd", activeCmd);
      if (forceCreate) q.set("create", "1");
      if (term.cols && term.rows) {
        q.set("cols", term.cols);
        q.set("rows", term.rows);
      }
      const response = await fetch(
        "/api/terminal-ticket?" + q.toString(),
        { cache: "no-store" });
      if (!response.ok) {
        if (response.status === 404) {
          sessionTerminated = true;
          setState("session ended / not found", "gone");
          term.write("\\r\\n\\x1b[33m[tmux session ended or killed]\\x1b[0m\\r\\n");
          againEl.textContent = "Recreate session";
          againEl.style.display = "";
          loadTmuxBar();
          return;
        }
        throw new Error(await response.text());
      }
      ticket = (await response.json()).ticket;
      sessionTerminated = false;
    } catch (err) {
      setState("no ticket: " + err.message, "gone");
      scheduleReconnect();
      return;
    }

    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(scheme + "://" + location.host +
                             "/ws/terminal?ticket=" + encodeURIComponent(ticket));
    ws.binaryType = "arraybuffer";
    socket = ws;

    ws.onopen = () => {
      if (socket !== ws) return;
      reconnectAttempts = 0;
      sessionTerminated = false;
      setState("connected", "live");
      safeFit();
      // Ensure resize is immediately sent upon connection
      sendResize();
      term.focus();
      startPing();
    };

    ws.onmessage = (event) => {
      if (socket !== ws) return;
      if (typeof event.data === "string") {
        try {
          const msg = JSON.parse(event.data);
          if (msg.pong) return;
          if (msg.event === "session_terminated") {
            sessionTerminated = true;
            setState("session terminated", "gone");
            term.write("\\r\\n\\x1b[33m[" + (msg.message || "tmux session was terminated") + "]\\x1b[0m\\r\\n");
            againEl.textContent = "Recreate session";
            againEl.style.display = "";
            loadTmuxBar();
            return;
          }
        } catch (_) {}
        term.write(event.data);
      } else {
        term.write(new Uint8Array(event.data));
      }
    };

    ws.onclose = (event) => {
      if (socket !== ws) return;
      clearPing();
      socket = null;
      if (sessionTerminated) {
        setState("session terminated", "gone");
        againEl.textContent = "Recreate session";
        againEl.style.display = "";
        loadTmuxBar();
      } else if (!intentionalClose) {
        scheduleReconnect();
      } else {
        setState("closed", "gone");
      }
    };

    ws.onerror = () => {
      if (socket !== ws) return;
      ws.close();
    };
  }

  function sendData(data) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(new TextEncoder().encode(data));
    }
  }

  // Sticky Ctrl/Alt from the touch key bar: armed by a tap, applied to the
  // next key (typed or tapped), then released.
  const mods = { ctrl: false, alt: false };
  const keybar = document.getElementById("keybar");
  function setMod(name, on) {
    mods[name] = on;
    const btn = keybar.querySelector(`[data-mod="${name}"]`);
    if (btn) btn.classList.toggle("armed", on);
  }
  function applyMods(data) {
    if ((!mods.ctrl && !mods.alt) || !data) return data;
    let first = data[0];
    const rest = data.slice(1);
    if (mods.ctrl && first !== "\x1b") {
      const c = first.toUpperCase().charCodeAt(0);
      if (c >= 64 && c <= 95) first = String.fromCharCode(c - 64);
      else if (first === " ") first = "\x00";
      else if (first === "?") first = "\x7f";
    }
    let out = first + rest;
    if (mods.alt) out = "\x1b" + out;
    setMod("ctrl", false);
    setMod("alt", false);
    return out;
  }
  const KEYS = {
    esc: "\x1b", tab: "\t", "ctrl-c": "\x03", "ctrl-b": "\x02",
    up: "A", down: "B", right: "C", left: "D",
    home: "\x1b[H", end: "\x1b[F", pgup: "\x1b[5~", pgdn: "\x1b[6~",
  };
  // mousedown's default would move focus off xterm and close the keyboard.
  keybar.addEventListener("mousedown", (e) => e.preventDefault());
  keybar.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    if (btn.dataset.mod) {
      setMod(btn.dataset.mod, !mods[btn.dataset.mod]);
    } else if (btn.dataset.text) {
      sendData(applyMods(btn.dataset.text));
    } else {
      const k = KEYS[btn.dataset.key];
      if (k && "ABCD".includes(k)) {
        // Arrows: modifiers go in the CSI parameter (Alt=3, Ctrl=5, both=7).
        const m = 1 + (mods.alt ? 2 : 0) + (mods.ctrl ? 4 : 0);
        sendData(m > 1 ? `\x1b[1;${m}${k}` : "\x1b[" + k);
        setMod("ctrl", false);
        setMod("alt", false);
      } else if (k) {
        sendData(applyMods(k));
      }
    }
    term.focus();
  });

  term.onData((data) => sendData(applyMods(data)));

  // On phones the on-screen keyboard shrinks only the *visual* viewport, so a
  // 100vh page keeps its height and the keyboard covers the bottom of the
  // terminal. Size the page to the visual viewport instead, and hide the
  // header while the keyboard is up.
  if (window.visualViewport) {
    const vv = window.visualViewport;
    let fullHeight = vv.height;
    const onViewport = () => {
      fullHeight = Math.max(fullHeight, vv.height);
      document.documentElement.style.setProperty("--vvh", vv.height + "px");
      document.body.classList.toggle("kb-open", fullHeight - vv.height > 150);
      window.scrollTo(0, 0);
      safeFit();
    };
    vv.addEventListener("resize", onViewport);
    window.addEventListener("orientationchange", () => {
      fullHeight = 0;
      setTimeout(onViewport, 300);
    });
    onViewport();
  }

  // Touch scrolling. tmux runs in the alternate screen, so xterm has no
  // scrollback of its own to swipe through; turn vertical swipes into mouse
  // wheel events (SGR encoding) and let tmux scroll (copy-mode, mouse on).
  (() => {
    const el = term.element;
    if (!el) return;
    let lastY = null, acc = 0, moved = false;
    const cell = () => {
      const screen = el.querySelector(".xterm-screen");
      return {
        rect: screen.getBoundingClientRect(),
        h: screen.clientHeight / term.rows,
        w: screen.clientWidth / term.cols,
      };
    };
    el.addEventListener("touchstart", (e) => {
      if (e.touches.length !== 1) { lastY = null; return; }
      lastY = e.touches[0].clientY; acc = 0; moved = false;
    }, { capture: true, passive: true });
    el.addEventListener("touchmove", (e) => {
      if (lastY === null || term.modes.mouseTrackingMode === "none") return;
      const t = e.touches[0];
      const c = cell();
      acc += t.clientY - lastY;
      lastY = t.clientY;
      if (Math.abs(acc) > 8) moved = true;
      if (!moved) return;
      e.preventDefault();
      e.stopPropagation();
      // tmux scrolls several lines per wheel tick, so use ~2 rows of travel each.
      const step = c.h * 2;
      const col = Math.min(term.cols, Math.max(1, Math.floor((t.clientX - c.rect.left) / c.w) + 1));
      const row = Math.min(term.rows, Math.max(1, Math.floor((t.clientY - c.rect.top) / c.h) + 1));
      while (Math.abs(acc) >= step) {
        // Finger down -> content follows -> wheel up (64); finger up -> wheel down (65).
        sendData(`\x1b[<${acc > 0 ? 64 : 65};${col};${row}M`);
        acc -= Math.sign(acc) * step;
      }
    }, { capture: true, passive: false });
    el.addEventListener("touchend", (e) => {
      // A swipe should not also count as a tap (which would place the cursor).
      if (moved) { e.preventDefault(); e.stopPropagation(); }
      lastY = null;
    }, { capture: true, passive: false });
  })();

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && !sessionTerminated) {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        if (reconnectTimer) {
          clearTimeout(reconnectTimer);
          reconnectTimer = null;
        }
        reconnectAttempts = 0;
        connect();
      } else {
        try { socket.send(JSON.stringify({ ping: 1 })); } catch (_) {}
        safeFit();
      }
    }
  });
  window.addEventListener("online", () => {
    if (!sessionTerminated && (!socket || socket.readyState !== WebSocket.OPEN)) {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      reconnectAttempts = 0;
      connect();
    }
  });

  addEventListener("beforeunload", (event) => {
    if (intentionalClose || currentTmuxSession) return;
    clearPing();
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (socket && socket.readyState === WebSocket.OPEN) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  againEl.addEventListener("click", () => {
    reconnectAttempts = 0;
    const forceCreate = sessionTerminated;
    sessionTerminated = false;
    connect(forceCreate);
  });

  // Fit terminal DOM dimensions before opening ticket and socket
  requestAnimationFrame(() => {
    safeFit();
    setTimeout(() => {
      safeFit();
      connect();
    }, 50);
  });
}
</script>
</body>
</html>
""".replace("{THEME}", THEME)
