const cfg = pageConfig();
let activeService = cfg.service || "";
let currentSessionParam = cfg.session || "";
let currentTmuxSession = cfg.tmuxSession || "";
const where = cfg.where || "";
let activeCmd = cfg.cmd || "";
const pageTitle = cfg.title || "";
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

const qs = encodeURIComponent;

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
  const res = await postJSON("/api/tmux/rename", { session: targetSession, name: cleanNew });
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
      postJSON("/api/tmux/kill", { session: targetSession }),
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
  document.title = `${short} shell · ${pageTitle}`;

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
  const res = await postJSON("/api/tmux/create", { name, cwd: "~" });
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
        postJSON("/api/tmux/kill", { session: currentTmuxSession }),
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
        await postJSON("/api/tmux/rename", { session: currentTmuxSession, name: rawNew });
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
          term.write("\r\n\x1b[33m[tmux session ended or killed]\x1b[0m\r\n");
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
            term.write("\r\n\x1b[33m[" + (msg.message || "tmux session was terminated") + "]\x1b[0m\r\n");
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
