const REFRESH = parseInt(pageConfig().refresh, 10) || 15;
const qs = encodeURIComponent;

// Which address family this browser reached us on decides which link we lead
// with: opened over a public hostname you want the tunnel URLs, opened over the
// LAN IP you want the LAN ones. The other is always one click away as "alt".
const PUBLIC_VIEW = !/^[\d.]+$|^\[|^localhost$|\.local$/i.test(location.hostname);

function links(s) {
  if (s.alt_link) {
    const primary = (PUBLIC_VIEW && s.remote) || s.link || s.remote || "";
    return { primary, alt: s.alt_link, altLabel: s.alt_label || "servers" };
  }
  const lan = s.link, pub = s.remote;
  const primary = (PUBLIC_VIEW && pub) || lan || pub || "";
  const alt = primary === pub ? lan : pub;
  return { primary, alt, altLabel: primary === pub ? "LAN" : "WAN" };
}

// Projects now lives in pjm: the tab is a plain link to its Projects page,
// not a pane. Before /api/status answers we don't know pjm's configured
// link/remote, so lead with a same-host guess; render() below replaces it
// with the real [pjm] entry (and its WAN address once PUBLIC_VIEW applies).
function setProjectsTabLink(href) {
  const a = document.getElementById("projectsTabLink");
  if (a && href) a.href = href;
}
setProjectsTabLink(`http://${location.hostname}:8400/#/projects`);

// Folded by default: this page is for operating the homelab, not staring at it.
const isOpen = (g) => localStorage.getItem("fold:" + g) === "open";

const icon = (name) => ICONS[name] || "";
const iconOf = (s) => icon(s.icon || String(s.name).trim().toLowerCase().replace(/[ _]+/g, "-"));
// Where it runs, when that is not this box. The service's own icon already says
// "Raspberry Pi" on the Pi entry itself, so it is not badged twice.
const nodeBadge = (s) => s.node === "pi" && s.icon !== "raspberry"
  ? `<span class="node" title="runs on the Raspberry Pi">${icon("raspberry")}</span>` : "";

function altSession(s) {
  const list = s.tmux_sessions || [];
  if (!list.length) return "";
  return list.map(name => {
    const live = s.attached_sessions && s.attached_sessions.includes(name);
    return `<a class="alt" href="/terminal?session=${qs(name)}"
      title="tmux session: ${esc(name)}">${icon("terminal")}<span class="dot ${live ? "up" : "warn"}"></span></a>`;
  }).join("");
}

// An address you paste into an agent's config, not a page you visit. Copying is
// the only thing you ever do with it, so that is the only button it gets.
const copyBtn = (value, cls) => `<button class="${cls}" data-copy="${esc(value)}"
  title="Copy ${esc(value)}">${cls === "alt copy" ? icon("copy") : "Copy"}</button>`;

function chip(s) {
  const { primary, alt, altLabel } = links(s);
  // No page behind it, but still worth a chip when it names an endpoint: you
  // come here to read its state and take the address away with you.
  if (!primary && !s.endpoint) return "";
  const cls = "chip" + (s.state === "up" ? "" : " offline");
  const head = `<span class="dot ${esc(s.state)}"></span>${iconOf(s)}${esc(s.name)}${nodeBadge(s)}`;
  const altList = (s.alt_links && s.alt_links.length)
    ? s.alt_links
    : (alt ? [{ href: alt, icon: s.alt_icon, label: altLabel }] : []);
  const altButtons = altList.map(a => `<a class="alt" href="${esc(a.href)}"${a.href.startsWith("/") ? "" : ' target="_blank" rel="noopener"'}
    title="${esc(a.label || a.icon || "alt")}: ${esc(a.href)}">${icon(a.icon) || esc(a.label || "alt")}</a>`).join("");
  return `<span class="${cls}">
    ${primary
      ? `<a href="${esc(primary)}" target="_blank" rel="noopener">${head}</a>`
      : `<span class="plain" title="${esc(s.endpoint)}">${head}</span>`}
    ${s.endpoint ? copyBtn(s.endpoint, "alt copy") : ""}
    ${altSession(s)}
    ${s.has_chip_shell ? `<a class="alt" href="/terminal?service=${qs(s.name)}"
      title="shell: ${esc(s.command)}">${icon("terminal")}</a>` : ""}
    ${altButtons}</span>`;
}

function launcher(l) {
  if (!l.enabled) return "";
  return `<span class="chip term">
    <a href="/terminal?service=${qs(l.name)}">${icon(l.icon)}${esc(l.name)}
      ${l.command ? `<code>${esc(l.command)}</code>` : ""}</a></span>`;
}

// The tmux sessions a preconfigured row owns: its claude, agy and Shell
// buttons (names as tmux_manager.session_name_for_check builds them, plus the
// unprefixed names older sessions still carry).
function presetSessionNames(l) {
  const n = l.service.replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  return {
    claude: [`cockpit-${n}-claude`, `${n}-claude`],
    agy: [`cockpit-${n}-agy`, `${n}-agy`],
    shell: [`cockpit-${n}`],
  };
}

// The Remote Control servers serving a workspace: a dot for the unit, the
// agent's mark opening its web console, and the unit's logs. A workspace with
// no Claude server gets a "+ RC" link to the create form, path filled in.
// A workspace locked in services.conf (`rc_locked`) shows a lock instead.
function rcCell(l) {
  if (l.rc_locked) {
    return `<span class="rc-cell"><span class="btn-table-action" style="cursor:default; opacity:0.7;" title="No Remote Control here: ${esc(l.rc_locked)}">🔒 no RC</span></span>`;
  }
  const rcs = (l.rc || []).map(r => `<span class="rc-pill" title="${esc(r.unit)}: ${esc(r.detail || r.state)}">
      <span class="dot ${esc(r.state)}"></span>
      <a class="btn-table-action${r.state === "up" ? " primary-link" : ""}" href="${esc(r.web)}" target="_blank" rel="noopener"
        title="Open the ${r.agent === "claude" ? "Claude" : "Antigravity"} web console">${icon(r.agent)} web</a>
      <a class="btn-table-action" href="${esc(r.logs)}" title="Logs of ${esc(r.unit)}">logs</a>
    </span>`).join("");
  const hasClaude = (l.rc || []).some(r => r.agent === "claude");
  const add = !hasClaude && l.dir
    ? `<a class="btn-table-action" href="/claude-rc?workspace=${qs(l.dir)}" title="Start an always-on Claude Remote Control server in ${esc(l.dir)}">+ RC</a>`
    : "";
  return `<span class="rc-cell">${rcs}${add}</span>`;
}

// One row per AI workspace: where it opens, the Remote Control servers running
// there, and a button per local way in.
// A button whose tmux session already runs reads "attach", with a dot (green:
// someone is attached, amber: it runs in the background) - those sessions are
// left out of the Other Active Live Sessions table below, so each shows once.
function sessionRow(l, tmux) {
  const sessions = (tmux && tmux.sessions) || [];
  const names = presetSessionNames(l);
  const live = kind => sessions.find(t => names[kind].includes(t.name));
  const button = (kind, href, iconName, label, launchTitle) => {
    const t = live(kind);
    const dot = t ? `<span class="dot ${t.attached ? "up" : "warn"}"></span>` : "";
    const title = t
      ? `Running (${t.attached ? "attached" : "background"}): attach to ${t.name}`
      : launchTitle;
    return `<a class="btn-table-action${t ? " primary-link" : ""}" href="${href}" title="${esc(title)}">${dot}${icon(iconName)} ${t ? "attach" : label}</a>`;
  };
  const dash = `<span class="muted-dash">—</span>`;
  const launch = (cmd, iconName, label) => l.terminal ? button(cmd,
    `/terminal?service=${qs(l.service)}&cmd=${cmd}`, iconName, cmd,
    `Launch ${label} in ${l.name}: ${l[`${cmd}_command`] || cmd}`) : dash;
  const shell = l.terminal && l.command
    ? button("shell", `/terminal?service=${qs(l.service)}`, "terminal", "Shell", `Shell, runs: ${l.command}`)
    : `<span class="muted-dash">—</span>`;
  const del = l.custom
    ? `<button type="button" class="btn-table-action" data-delete-session="${esc(l.name)}" title="Remove session ${esc(l.name)}">×</button>`
    : "";
  const home = "/home/zfadli";
  const dir = (l.dir || "").startsWith(home) ? "~" + l.dir.slice(home.length) : (l.dir || "");
  return `<tr>
    <td class="service-cell"><span class="service-head">${icon(l.icon || "briefcase")}<span class="service-table-name">${esc(l.name)}</span></span></td>
    <td><code title="${esc(l.dir || "")}">${esc(dir)}</code></td>
    <td style="color:var(--muted);">${esc(l.note || "")}</td>
    <td>${rcCell(l)}</td>
    <td style="text-align:center;">${launch("claude", "claude", "Claude Code")}</td>
    <td style="text-align:center;">${launch("agy", "antigravity", "Antigravity")}</td>
    <td style="text-align:center;">${shell}</td>
    <td style="text-align:center;">${del}</td>
  </tr>`;
}

function card(s) {
  const { primary, alt, altLabel } = links(s);
  const named = (href, label) =>
    `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(label)}</a>`;
  const altList = (s.alt_links && s.alt_links.length)
    ? s.alt_links
    : (s.alt_link ? [{ href: s.alt_link, icon: s.alt_icon, label: s.alt_label }] : []);
  const consoles = altList.map(a => named(a.href, a.label || a.icon || "alt")).join("");
  const toggleBtn = s.can_toggle
    ? `<button class="btn-toggle ${s.unit_enabled ? "on" : "off"}" data-toggle-service="${esc(s.name)}" data-enabled="${s.unit_enabled ? "true" : "false"}" title="${s.unit_enabled ? "Click to disable (systemctl disable)" : "Click to enable (systemctl enable)"}"><span class="dot ${s.unit_enabled ? "up" : "down"}"></span>${s.unit_enabled ? "Enabled" : "Disabled"}</button>`
    : "";
  const acts = [
    toggleBtn,
    s.has_logs ? `<a href="/logs?service=${qs(s.name)}">Logs</a>` : "",
    s.has_terminal ? `<a href="/terminal?service=${qs(s.name)}">Shell</a>` : "",
    s.has_terminal ? `<a href="/terminal?service=${qs(s.name)}&cmd=agy">agy</a>` : "",
    s.has_terminal ? `<a href="/terminal?service=${qs(s.name)}&cmd=claude">claude</a>` : "",
    s.has_host_shell ? `<a href="/terminal?service=${qs(s.name)}&where=host">Compose</a>` : "",
    alt ? `<a href="${esc(alt)}" target="_blank" rel="noopener">${altLabel}</a>` : "",
    consoles,
    s.endpoint ? copyBtn(s.endpoint, "copy") : "",
  ].join("");
  return `<div class="card ${esc(s.state)}">
    <span class="dot"></span>
    <div class="body">
      <div class="name">${iconOf(s)}${primary
        ? `<a href="${esc(primary)}" target="_blank" rel="noopener">${esc(s.name)}</a>`
        : esc(s.name)}${nodeBadge(s)}</div>
      <div class="detail">${esc(s.detail)}</div>
      <div class="meta">${[s.meta, s.note].filter(Boolean).map(esc).join(" · ")}</div>
      ${s.endpoint ? `<div class="meta"><code>${esc(s.endpoint)}</code></div>` : ""}
      <div class="acts">${acts}</div>
    </div>
  </div>`;
}

let servicesSortColumn = "group";
let servicesSortAsc = true;
let servicesSearchQuery = "";
let servicesSelectedGroup = "";
let servicesSelectedType = "";
let cachedOtherServices = [];

function serviceTableRow(s) {
  const { primary, alt, altLabel } = links(s);
  const altList = (s.alt_links && s.alt_links.length)
    ? s.alt_links
    : (s.alt_link ? [{ href: s.alt_link, icon: s.alt_icon, label: s.alt_label }] : []);

  // 1. Service column
  const nameEl = primary
    ? `<a href="${esc(primary)}" target="_blank" rel="noopener" class="service-table-link">${esc(s.name)}</a>`
    : `<span class="service-table-name">${esc(s.name)}</span>`;
  const nodeEl = nodeBadge(s);
  const noteText = s.note || s.detail || "";
  const serviceCell = `
    <div class="service-cell">
      <div class="service-head">${iconOf(s)}${nameEl}${nodeEl}</div>
      ${noteText ? `<div class="rc-unit-sub" title="${esc(noteText)}">${esc(noteText)}</div>` : ""}
      ${s.endpoint ? `<div class="meta" style="margin-top:2px;"><code>${esc(s.endpoint)}</code></div>` : ""}
    </div>`;

  // 2. Group column
  const groupCell = `<span class="rc-scope-badge" style="margin-left:0;">${esc(s.group)}</span>`;

  // 3. Status column
  const statusCell = `
    <div class="status-cell">
      <span class="rc-status-cell"><span class="dot ${esc(s.state)}"></span><b style="text-transform:capitalize;">${esc(s.state)}</b></span>
      ${s.detail && s.state !== "up" ? `<span class="rc-unit-sub" style="color:var(--${esc(s.state)});" title="${esc(s.detail)}">${esc(s.detail)}</span>` : ""}
    </div>`;

  // 4. Open / Web column
  const openBtns = [];
  if (primary) {
    openBtns.push(`<a class="btn-table-action primary-link" href="${esc(primary)}" target="_blank" rel="noopener" title="Open ${esc(primary)}">Open ↗</a>`);
  }
  if (alt) {
    openBtns.push(`<a class="btn-table-action" href="${esc(alt)}" target="_blank" rel="noopener" title="${esc(altLabel)}: ${esc(alt)}">${esc(altLabel)}</a>`);
  }
  altList.forEach(a => {
    if (a.href !== primary && a.href !== alt) {
      openBtns.push(`<a class="btn-table-action" href="${esc(a.href)}" target="_blank" rel="noopener" title="${esc(a.label || a.icon || 'alt')}">${esc(a.label || a.icon || 'alt')}</a>`);
    }
  });
  if (s.endpoint) {
    openBtns.push(copyBtn(s.endpoint, "btn-table-action copy"));
  }
  const openCell = openBtns.length ? `<div class="btn-group" style="justify-content:center;">${openBtns.join("")}</div>` : `<span class="muted-dash">—</span>`;

  // 5. Shell column
  const shellBtns = [];
  if (s.has_terminal) {
    shellBtns.push(`<a class="btn-table-action" href="/terminal?service=${qs(s.name)}" title="Shell in ${esc(s.name)}">${icon("terminal")} Shell</a>`);
  }
  if (s.has_host_shell) {
    shellBtns.push(`<a class="btn-table-action" href="/terminal?service=${qs(s.name)}&where=host" title="Host compose shell">${icon("docker")} Compose</a>`);
  }
  const shellCell = shellBtns.length ? `<div class="btn-group" style="justify-content:center;">${shellBtns.join("")}</div>` : `<span class="muted-dash">—</span>`;

  // 6. agy column
  const agyCell = s.has_terminal
    ? `<a class="btn-table-action" href="/terminal?service=${qs(s.name)}&cmd=agy" title="Antigravity in ${esc(s.name)}">${icon("antigravity")} agy</a>`
    : `<span class="muted-dash">—</span>`;

  // 7. claude column
  const claudeCell = s.has_terminal
    ? `<a class="btn-table-action" href="/terminal?service=${qs(s.name)}&cmd=claude" title="Claude Code in ${esc(s.name)}">${icon("claude")} claude</a>`
    : `<span class="muted-dash">—</span>`;

  // 8. Logs column
  const logsCell = s.has_logs
    ? `<a class="btn-table-action" href="/logs?service=${qs(s.name)}" title="Logs for ${esc(s.name)}">Logs</a>`
    : `<span class="muted-dash">—</span>`;

  // 9. Toggle column
  let toggleCell = `<span class="muted-dash">—</span>`;
  if (s.can_toggle) {
    toggleCell = `<button type="button" class="btn-toggle ${s.unit_enabled ? "on" : "off"}" data-toggle-service="${esc(s.name)}" data-enabled="${s.unit_enabled ? "true" : "false"}" title="${s.unit_enabled ? "Click to disable (systemctl disable)" : "Click to enable (systemctl enable)"}"><span class="dot ${s.unit_enabled ? "up" : "down"}"></span>${s.unit_enabled ? "Enabled" : "Disabled"}</button>`;
  } else if (s.unit_file_state) {
    toggleCell = `<span class="rc-scope-badge" style="margin:0;" title="Unit file state">${esc(s.unit_file_state)}</span>`;
  }

  return `<tr>
    <td>${serviceCell}</td>
    <td>${groupCell}</td>
    <td>${statusCell}</td>
    <td style="text-align: center;">${openCell}</td>
    <td style="text-align: center;">${shellCell}</td>
    <td style="text-align: center;">${agyCell}</td>
    <td style="text-align: center;">${claudeCell}</td>
    <td style="text-align: center;">${logsCell}</td>
    <td style="text-align: center;">${toggleCell}</td>
  </tr>`;
}

function renderOtherServicesTable(otherGroups) {
  const allServices = [];
  otherGroups.forEach(g => {
    (g.services || []).forEach(s => {
      allServices.push(s);
    });
    (g.launchers || []).forEach(l => {
      allServices.push({
        name: l.name,
        group: g.name,
        state: "up",
        detail: l.note || l.command || "",
        note: l.note || "",
        icon: l.icon || "terminal",
        command: l.command || "",
        has_terminal: l.enabled,
        has_chip_shell: l.enabled && Boolean(l.command),
        has_logs: false,
        has_host_shell: false,
        can_toggle: false,
        is_launcher: true,
      });
    });
  });

  cachedOtherServices = allServices;

  // Populate Quick Group Filter Pills in Filter Bar
  const pillsContainer = document.getElementById("servicesGroupPills");
  if (pillsContainer) {
    const groupNames = Array.from(new Set(allServices.map(s => s.group))).filter(Boolean).sort();
    const allActive = !servicesSelectedGroup ? " active" : "";
    let pillsHtml = `<button type="button" class="group-filter-pill${allActive}" data-group-pill="">All <span class="pill-count">(${allServices.length})</span></button>`;
    groupNames.forEach(gn => {
      const count = allServices.filter(s => s.group === gn).length;
      const active = servicesSelectedGroup === gn ? " active" : "";
      pillsHtml += `<button type="button" class="group-filter-pill${active}" data-group-pill="${esc(gn)}">${esc(gn)} <span class="pill-count">(${count})</span></button>`;
    });
    pillsContainer.innerHTML = pillsHtml;
  }

  updateServicesTableRows();
}

function updateServicesTableRows() {
  const tbody = document.getElementById("servicesTableBody");
  if (!tbody) return;

  const q = (servicesSearchQuery || "").trim().toLowerCase();
  let filtered = cachedOtherServices.filter(s => {
    // 1. State filter
    if (activeStateFilter !== null && s.state !== activeStateFilter) {
      return false;
    }
    // 2. Group filter
    if (servicesSelectedGroup && s.group !== servicesSelectedGroup) {
      return false;
    }
    // 3. Type filter
    if (servicesSelectedType) {
      const st = String(s.type || s.meta || "").toLowerCase();
      if (!st.includes(servicesSelectedType.toLowerCase())) {
        return false;
      }
    }
    // 4. Search query
    if (q) {
      const match = (s.name && s.name.toLowerCase().includes(q)) ||
        (s.group && s.group.toLowerCase().includes(q)) ||
        (s.detail && s.detail.toLowerCase().includes(q)) ||
        (s.note && s.note.toLowerCase().includes(q)) ||
        (s.endpoint && s.endpoint.toLowerCase().includes(q)) ||
        (s.link && s.link.toLowerCase().includes(q)) ||
        (s.remote && s.remote.toLowerCase().includes(q));
      if (!match) return false;
    }
    return true;
  });

  // Sorting
  filtered.sort((a, b) => {
    let cmp = 0;
    if (servicesSortColumn === "name") {
      cmp = (a.name || "").localeCompare(b.name || "");
    } else if (servicesSortColumn === "group") {
      cmp = (a.group || "").localeCompare(b.group || "");
      if (cmp === 0) cmp = (a.name || "").localeCompare(b.name || "");
    } else if (servicesSortColumn === "state") {
      const rank = { down: 0, warn: 1, unknown: 2, up: 3 };
      const ra = rank[a.state] ?? 9;
      const rb = rank[b.state] ?? 9;
      cmp = ra - rb;
      if (cmp === 0) cmp = (a.name || "").localeCompare(b.name || "");
    }
    return servicesSortAsc ? cmp : -cmp;
  });

  // Update sort arrow indicators
  ["name", "group", "state"].forEach(col => {
    const el = document.getElementById(`sort-arrow-${col}`);
    if (el) {
      el.textContent = servicesSortColumn === col ? (servicesSortAsc ? "▲" : "▼") : "↕";
    }
  });

  // Update count badge
  const countBadge = document.getElementById("servicesCountBadge");
  if (countBadge) {
    if (filtered.length === cachedOtherServices.length) {
      countBadge.textContent = `${filtered.length} services`;
    } else {
      countBadge.textContent = `${filtered.length} / ${cachedOtherServices.length} services`;
    }
  }

  // Update Reset button visibility in filter bar
  const resetBtn = document.getElementById("resetAllFiltersBtn");
  const hasActiveFilters = Boolean(q || servicesSelectedGroup || servicesSelectedType || activeStateFilter !== null);
  if (resetBtn) {
    resetBtn.style.display = hasActiveFilters ? "" : "none";
  }

  // Update clear search button
  const clearSearchBtn = document.getElementById("clearSearchBtn");
  if (clearSearchBtn) {
    clearSearchBtn.style.display = q ? "" : "none";
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--muted); padding: 32px 14px;">No services matching current filter</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(serviceTableRow).join("");
}

const RANK = { claude: 0, antigravity: 0, terminal: 1 };
const rank = (item) => RANK[item.icon] ?? 2;

function group(g, tmux) {
  // The quick row is the operating surface: it holds the launchers plus
  // whatever is up and has somewhere to click through to. Ordered by what the
  // chip opens - Claude sessions, then local shells, then plain links - so the
  // two kinds of "somewhere to work" lead. Sorting is stable, so config order
  // still decides within each kind.

  const tmuxCount = tmux ? tmux.count : 0;
  const tmuxBadge = tmuxCount > 0 ? ` (${tmuxCount})` : "";
  const infraLaunchers = g.name === "Infra" ? [
    { icon: "terminal", html: `<span class="chip term"><a href="/tmux" title="manage and open active tmux sessions">${icon("terminal")}Tmux sessions${tmuxBadge}</a></span>` },
  ] : [];
  const launchers = g.launchers.filter(l => l.enabled).map(l => ({ icon: l.icon, html: launcher(l) }));

  // Services are filtered by activeStateFilter:
  // - When null, all services in the group are shown.
  // - When "up", "warn", "down", "unknown", only services matching that state are shown.
  let matchingServices = g.services;
  if (activeStateFilter !== null) {
    matchingServices = g.services.filter(s => s.state === activeStateFilter);
  }

  const eligible = matchingServices.filter(s => !s.headline)
    .filter(s => s.pinned || (s.state === "up" && (s.link || s.remote || s.endpoint)) || s.state === "warn" || s.state === "down");

  const quick = [
    ...infraLaunchers,
    ...launchers,
    ...eligible.map(s => ({ icon: s.icon, html: chip(s) })),
  ].sort((a, b) => rank(a) - rank(b)).map(item => item.html).join("");

  // If there are no launchers and no matching services, don't show the group
  if (!quick && matchingServices.length === 0) {
    return "";
  }

  const counts = ["down", "warn", "unknown", "up"]
    .map(state => [state, matchingServices.filter(s => s.state === state).length])
    .filter(([, n]) => n > 0)
    .map(([state, n]) => `<span><span class="dot ${state}"></span>${n} ${state}</span>`)
    .join("");

  const hasDegraded = matchingServices.some(s => s.state === "warn" || s.state === "down");
  const details = matchingServices.length ? `
    <details class="more" data-group="${esc(g.name)}"${hasDegraded || activeStateFilter !== null || isOpen(g.name) ? " open" : ""}>
      <summary>${matchingServices.length} ${matchingServices.length > 1 ? "Services" : "Service"} · Logs &amp; shells</summary>
      <div class="grid">${matchingServices.map(card).join("")}</div>
    </details>` : "";

  return `<section class="group">
    <div class="ghead"><h2>${esc(g.name)}</h2>${counts ? `<span class="gsum">${counts}</span>` : ""}</div>
    <div class="quick">${quick}</div>
    ${details}
  </section>`;
}

// Plan-usage health bars: how close the Claude and Antigravity accounts
// running this homelab are to their 5-hour and weekly limits. Refreshed on
// its own slow timer server-side (usage.py) and polled asynchronously via /api/usage.
function usageLevel(pct) {
  if (pct >= 85) return "down";
  if (pct >= 50) return "warn";
  return "up";
}

function parseResetDate(raw) {
  if (!raw) return null;
  let d = new Date(raw);
  if (!isNaN(d.getTime())) return d;

  // Claude format: "Aug 31, 6:59pm (Europe/Paris)" or "Aug 31, 1:09am"
  const m = String(raw).match(/^([A-Za-z]+)\s+(\d+),\s*(\d+)(?::(\d+))?\s*(am|pm)?/i);
  if (m) {
    const monthNames = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];
    const monthIdx = monthNames.indexOf(m[1].toLowerCase().slice(0, 3));
    if (monthIdx !== -1) {
      const day = parseInt(m[2], 10);
      let hour = parseInt(m[3], 10);
      const min = m[4] ? parseInt(m[4], 10) : 0;
      const ampm = m[5] ? m[5].toLowerCase() : null;
      if (ampm === "pm" && hour < 12) hour += 12;
      if (ampm === "am" && hour === 12) hour = 0;

      const now = new Date();
      let year = now.getFullYear();
      d = new Date(year, monthIdx, day, hour, min, 0);
      if (d.getTime() < now.getTime() - 180 * 86400 * 1000) {
        d = new Date(year + 1, monthIdx, day, hour, min, 0);
      }
      if (!isNaN(d.getTime())) return d;
    }
  }
  return null;
}

// A 5-hour window is short enough that "when" only matters as a countdown; a
// weekly one is long enough that a countdown stops being legible ("in 4290
// minutes") and the day it lands on is what you actually want to know. Both
// CLIs' reset strings parse as a Date - agy prints ISO, and claude's
// "Aug 25, 6:10am (Europe/Paris)" is parsed by parseResetDate.
function formatReset(reset, period) {
  if (!reset) return "";
  const d = parseResetDate(reset);
  if (!d) return reset;  // could not parse - show the CLI's own text verbatim
  if (period === "five_hour") {
    const ms = d.getTime() - Date.now();
    if (ms <= 0) return "any moment";
    const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000);
    return h > 0 ? `in ${h}h ${m}m` : `in ${m}m`;
  }
  return d.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" });
}

function usageMeter(label, bar, period) {
  if (!bar) {
    return `<span class="meter"><span class="mlabel">${label}</span><span class="mval muted">n/a</span></span>`;
  }
  const pct = Math.min(Math.max(bar.pct, 0), 100);
  const reset = formatReset(bar.reset, period);
  const title = `${label}: ${bar.pct}% of the limit used` + (reset ? ` · resets ${reset}` : "");
  return `<span class="meter" title="${esc(title)}">
    <span class="mlabel">${label}</span>
    <span class="bar-track"><span class="bar-fill ${usageLevel(bar.pct)}" style="width:${pct}%"></span></span>
    <span class="mval">${bar.pct}% used${reset ? ` <span class="reset">· resets ${esc(reset)}</span>` : ""}</span></span>`;
}

function usageCard(name, iconKey, entry) {
  if (!entry) return "";
  if (entry.state !== "ok") {
    return `<span class="usage-card offline" title="${esc(entry.detail || "unavailable")}">
      ${icon(iconKey)}<span class="uname">${esc(name)}</span><span class="mval muted">n/a</span></span>`;
  }
  const argonBar = entry.groups && entry.groups["Gemini 4 Argon"] && entry.groups["Gemini 4 Argon"].weekly;
  return `<span class="usage-card">
    ${icon(iconKey)}<span class="uname">${esc(name)}</span>
    ${usageMeter("5h", entry.bars.five_hour, "five_hour")}
    ${usageMeter("wk", entry.bars.weekly, "weekly")}
    ${argonBar ? usageMeter("argon", argonBar, "weekly") : ""}</span>`;
}

let usageLoaded = false;

function renderUsage(usage) {
  // Both cards render the same metric the same way - "% of the limit used",
  // rising and turning red as a period runs out - so this caption only needs
  // to say it once, not have every meter repeat it.
  document.getElementById("usageBars").innerHTML = usage
    ? `<span class="usage-caption">plan limits · % used</span>`
      + usageCard("Claude", "claude", usage.claude) + usageCard("Antigravity", "antigravity", usage.agy)
    : "";
}

async function pollUsage() {
  try {
    const response = await fetch("/api/usage", { cache: "no-store" });
    if (response.ok) {
      const u = await response.json();
      if (u) {
        renderUsage(u);
        const bothOk = u.claude && u.claude.state === "ok" && u.agy && u.agy.state === "ok";
        usageLoaded = bothOk;
        if (!bothOk) {
          setTimeout(pollUsage, 3000);
        }
      } else if (!usageLoaded) {
        setTimeout(pollUsage, 2500);
      }
    }
  } catch (err) {
    // ignore
  }
}

let activeStateFilter = null;
let lastData = null;
let lastSignature = "";

function render(data) {
  lastData = data;
  const t = data.totals;
  const lead = (data.headline || []).map(chip).join("");
  const tmuxCount = data.tmux ? data.tmux.count : 0;
  const tmuxBadge = tmuxCount > 0 ? ` (${tmuxCount})` : "";

  const newSessionChip = `<span class="chip term"><a href="/terminal?session=new" title="start direct terminal session in ~">${icon("terminal")}+ New session</a></span>`;
  const lastActive = data.tmux ? (data.tmux.last_active || (data.tmux.sessions && data.tmux.sessions[0])) : null;
  const lastActivePill = lastActive ? (() => {
    const raw = lastActive.name;
    const shortName = raw.startsWith("cockpit-") ? raw.slice(8) : raw;
    const cls = lastActive.attached ? "up" : "warn";
    return `<a class="pill ${cls}" href="/terminal?session=${qs(raw)}" title="resume last active session (${esc(raw)})"><span class="dot"></span><b>${esc(shortName)}</b></a>`;
  })() : "";
  const allTmuxChip = `<span class="chip term"><a href="/tmux" title="manage all tmux sessions">${icon("terminal")}Tmux sessions${tmuxBadge}</a></span>`;

  const statePills = [
    ["up", "Up", t.up], ["warn", "Degraded", t.warn],
    ["down", "Down", t.down], ["unknown", "Unknown", t.unknown],
  ].filter(([, , n]) => n > 0).map(([cls, label, n]) => {
    const active = activeStateFilter === cls ? " active" : "";
    return `<button type="button" class="pill ${cls}${active}" data-state-filter="${cls}" title="${active ? "Click to clear filter" : "Click to view " + label + " services"}"><span class="dot"></span><b>${n}</b> ${label}</button>`;
  }).join("");

  const hideBtn = activeStateFilter
    ? `<button type="button" class="pill" data-state-filter="clear" title="Show all services" style="opacity: 0.8; font-weight: 500;">✕ Clear filter</button>`
    : "";

  document.getElementById("totals").innerHTML = statePills + hideBtn;

  const aiGroup = data.groups.find(g => g.name === "AI Sessions" || g.name === "Preconfigured AI Sessions");
  const otherGroups = data.groups.filter(g => g !== aiGroup);

  const pjmService = data.groups.flatMap(g => g.services || []).find(s => s.name === "pjm");
  if (pjmService) {
    const { primary } = links(pjmService);
    if (primary) setProjectsTabLink(primary.replace(/\/+$/, "") + "/#/projects");
  }

  const aiGroupEl = document.getElementById("aiSessionsGroup");
  const workspaces = data.workspaces || [];
  if (workspaces.length) {
    if (aiGroupEl) aiGroupEl.style.display = "";
    const aiLaunchers = workspaces.map(l => sessionRow(l, data.tmux)).join("");
    const aiQuickEl = document.getElementById("aiSessionsQuick");
    if (aiQuickEl) aiQuickEl.innerHTML = aiLaunchers;
  } else if (aiGroupEl) {
    aiGroupEl.style.display = "none";
  }

  // Other Active Live Sessions section in Tab 1
  const activeSecEl = document.getElementById("activeSessionsSection");
  const activeQuickEl = document.getElementById("activeSessionsQuick");
  const activeCountEl = document.getElementById("activeSessionsCount");
  const presetNames = new Set(workspaces
    .filter(l => l.service)
    .flatMap(l => Object.values(presetSessionNames(l)).flat()));
  const tmuxSessions = ((data.tmux && data.tmux.sessions) || [])
    .filter(t => !presetNames.has(t.name));
  if (activeSecEl && activeQuickEl) {
    if (tmuxSessions.length > 0) {
      activeSecEl.style.display = "";
      if (activeCountEl) activeCountEl.textContent = `${tmuxSessions.length} active`;
      activeQuickEl.innerHTML = tmuxSessions.map(s => {
        const live = s.attached;
        const isCockpit = s.name.startsWith("cockpit-");
        const shortName = isCockpit ? s.name.slice(8) : s.name;
        let toolIcon = "terminal";
        if (s.name.endsWith("-claude") || s.name.includes("claude")) toolIcon = "claude";
        else if (s.name.endsWith("-agy") || s.name.includes("agy") || s.name.includes("antigravity")) toolIcon = "antigravity";
        const dot = `<span class="dot ${live ? "up" : "warn"}"></span>`;
        return `<tr>
          <td class="service-cell"><span class="service-head" title="${esc(s.name)}">${icon(toolIcon)}<span class="service-table-name">${esc(shortName)}</span></span></td>
          <td style="color:var(--muted);"><span class="service-head" style="font-weight:400;">${dot}${live ? `attached (${s.attached_count})` : "background"}</span></td>
          <td style="text-align:center;"><a class="btn-table-action primary-link" href="/terminal?session=${qs(s.name)}" title="Attach to session ${esc(s.name)}">attach</a></td>
        </tr>`;
      }).join("");
    } else {
      activeSecEl.style.display = "none";
      activeQuickEl.innerHTML = "";
    }
  }

  // Update tab button count badge
  const tmuxTabBtn = document.querySelector('[data-tab="tmux-sessions"]');
  if (tmuxTabBtn) {
    const count = (data.tmux && data.tmux.count) || 0;
    tmuxTabBtn.innerHTML = `<svg class="ico" viewBox="0 0 16 16"><rect x="1" y="2.5" width="14" height="11" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M4 6l2.5 2L4 10 M8.5 10.5h3.5" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> Tmux Sessions${count > 0 ? ` (${count})` : ""}`;
  }

  // Render Other Services Table
  renderOtherServicesTable(otherGroups);

  document.getElementById("updated").textContent = "updated " + data.generated_at;
  document.body.classList.remove("stale");

  const activeTab = localStorage.getItem("cockpit_active_tab");
  if (activeTab === "tmux-sessions") {
    loadTmuxSessions();
  }
}

document.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-state-filter]");
  if (!btn) return;
  event.preventDefault();
  const filter = btn.dataset.stateFilter;
  if (filter === "clear" || activeStateFilter === filter) {
    activeStateFilter = null;
  } else {
    activeStateFilter = filter;
  }
  if (lastData) {
    lastSignature = "";
    render(lastData);
  }
});

// Other services filter bar & sorting listeners
document.addEventListener("input", (e) => {
  if (e.target && e.target.id === "servicesSearchInput") {
    servicesSearchQuery = e.target.value;
    updateServicesTableRows();
  }
});

document.addEventListener("change", (e) => {
  if (e.target && e.target.id === "servicesTypeFilter") {
    servicesSelectedType = e.target.value;
    updateServicesTableRows();
  }
});

document.addEventListener("click", (e) => {
  if (e.target && e.target.id === "clearSearchBtn") {
    e.preventDefault();
    servicesSearchQuery = "";
    const inp = document.getElementById("servicesSearchInput");
    if (inp) { inp.value = ""; inp.focus(); }
    updateServicesTableRows();
    return;
  }

  const groupPill = e.target.closest("[data-group-pill]");
  if (groupPill) {
    e.preventDefault();
    servicesSelectedGroup = groupPill.dataset.groupPill || "";
    document.querySelectorAll(".group-filter-pill").forEach(p => {
      p.classList.toggle("active", p.dataset.groupPill === servicesSelectedGroup);
    });
    updateServicesTableRows();
    return;
  }

  if (e.target && e.target.id === "resetAllFiltersBtn") {
    e.preventDefault();
    servicesSearchQuery = "";
    servicesSelectedGroup = "";
    servicesSelectedType = "";
    activeStateFilter = null;
    const inp = document.getElementById("servicesSearchInput");
    if (inp) inp.value = "";
    const typeSel = document.getElementById("servicesTypeFilter");
    if (typeSel) typeSel.value = "";
    document.querySelectorAll(".group-filter-pill").forEach(p => {
      p.classList.toggle("active", p.dataset.groupPill === "");
    });
    if (lastData) {
      render(lastData);
    } else {
      updateServicesTableRows();
    }
    return;
  }

  const sortBtn = e.target.closest(".sort-header");
  if (sortBtn && sortBtn.dataset.sort) {
    e.preventDefault();
    const col = sortBtn.dataset.sort;
    if (servicesSortColumn === col) {
      servicesSortAsc = !servicesSortAsc;
    } else {
      servicesSortColumn = col;
      servicesSortAsc = true;
    }
    updateServicesTableRows();
  }
});

// Delegated: every poll that changes something rebuilds the cards wholesale,
// so a listener bound to a button would not survive the next refresh.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  event.preventDefault();
  const value = button.dataset.copy;
  try {
    // Only available over HTTPS or on localhost; the LAN view is plain HTTP,
    // so fall back to the old execCommand path rather than silently doing
    // nothing on exactly the address you reach this page from most often.
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
    } else {
      const scratch = document.createElement("textarea");
      scratch.value = value;
      scratch.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(scratch);
      scratch.select();
      document.execCommand("copy");
      scratch.remove();
    }
    button.classList.add("copied");
    setTimeout(() => button.classList.remove("copied"), 1200);
  } catch (err) {
    button.title = "copy failed - " + value;
  }
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-toggle-service]");
  if (!button) return;
  event.preventDefault();
  const service = button.dataset.toggleService;
  const currentEnabled = button.dataset.enabled === "true";
  const targetEnabled = !currentEnabled;

  button.disabled = true;
  const originalText = button.innerHTML;
  button.textContent = "…";

  try {
    const res = await fetch("/api/service/toggle-enable", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service: service, enabled: targetEnabled })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      alert("Toggle failed: " + (data.message || "error"));
    }
  } catch (err) {
    alert("Toggle failed: " + err);
  } finally {
    await poll();
  }
});

document.getElementById("expand").addEventListener("click", (event) => {
  event.preventDefault();
  const details = document.querySelectorAll("details.more");
  if (!details.length) return;
  const opening = [...details].some(el => !el.open);
  details.forEach(el => { el.open = opening; });
  event.target.textContent = opening ? "Collapse all" : "Expand all";
});

async function poll() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    render(await response.json());
  } catch (err) {
    document.body.classList.add("stale");
    document.getElementById("updated").textContent = "unreachable — retrying…";
  }
}

function switchTab(tabId) {
  document.querySelectorAll(".cockpit-tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabId);
  });
  document.querySelectorAll(".cockpit-tab-pane").forEach(pane => {
    pane.style.display = pane.id === "pane-" + tabId ? "" : "none";
  });
  localStorage.setItem("cockpit_active_tab", tabId);
  if (tabId === "cron") {
    const iframe = document.getElementById("cronIframe");
    if (iframe && !iframe.src) iframe.src = iframe.dataset.src;
  } else if (tabId === "media") {
    const iframe = document.getElementById("mediaIframe");
    if (iframe && !iframe.src) iframe.src = iframe.dataset.src;
  } else if (tabId === "tokens") {
    const iframe = document.getElementById("tokensIframe");
    if (iframe && !iframe.src) iframe.src = iframe.dataset.src;
  } else if (tabId === "ai-routes") {
    const iframe = document.getElementById("aiRoutesIframe");
    if (iframe && !iframe.src) iframe.src = iframe.dataset.src;
  } else if (tabId === "ai-usage") {
    const iframe = document.getElementById("aiUsageIframe");
    if (iframe && !iframe.src) iframe.src = iframe.dataset.src;
  } else if (tabId === "tmux-sessions") {
    loadTmuxSessions();
  }
}

let tmuxLoaded = false;
async function loadTmuxSessions() {
  const container = document.getElementById("tmuxSessionsContainer");
  if (!container) return;
  try {
    const res = await fetch("/api/tmux", { cache: "no-store" });
    const data = await res.json();
    const sessions = data.sessions || [];

    if (sessions.length === 0) {
      container.innerHTML = `<div style="text-align:center; color:var(--muted); padding:36px; background:var(--panel); border:1px solid var(--border); border-radius:8px;">
        No active tmux sessions right now. Use <b>+ New session</b> above or start a terminal session.
      </div>`;
      tmuxLoaded = true;
      return;
    }

    let rowsHtml = sessions.map(s => {
      const live = s.attached;
      const statusHtml = `<span class="rc-status-cell"><span class="dot ${live ? "up" : "warn"}"></span>${live ? `attached (${s.attached_count})` : "detached"}</span>`;
      const isCockpit = s.name.startsWith("cockpit-");
      const shortName = isCockpit ? s.name.slice(8) : s.name;
      const badge = isCockpit ? `<span class="rc-scope-badge">cockpit</span>` : `<span class="rc-scope-badge">tmux</span>`;
      const nameHtml = `<span class="rc-session-name">${esc(shortName)}</span>${badge}<span class="rc-unit-sub">${esc(s.name)}</span>`;
      const windowsHtml = `<span class="rc-config-text">${esc(s.windows)} window${s.windows === 1 ? "" : "s"}</span>`;
      const createdHtml = `<span class="rc-config-text">${esc(s.created_human || "")}</span>`;
      const actsHtml = `<div class="acts">
        <a href="/terminal?session=${qs(s.name)}">Attach</a>
        <button type="button" class="btn-subtle" data-rename-tmux="${esc(s.name)}" style="font-size:12px; padding:1px 8px;">Rename</button>
        <button type="button" class="btn-subtle" data-kill-tmux="${esc(s.name)}" style="font-size:12px; padding:1px 8px; color:var(--down); border-color:color-mix(in srgb, var(--down) 30%, var(--border));">Kill</button>
      </div>`;

      return `<tr>
        <td>${nameHtml}</td>
        <td>${statusHtml}</td>
        <td>${windowsHtml}</td>
        <td>${createdHtml}</td>
        <td>${actsHtml}</td>
      </tr>`;
    }).join("");

    container.innerHTML = `<div class="rc-table-wrap">
      <table class="rc-table">
        <thead>
          <tr>
            <th>Session</th>
            <th>Status</th>
            <th>Windows</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    </div>`;
    tmuxLoaded = true;
  } catch (err) {
    container.innerHTML = `<div class="card down"><div class="body"><div class="detail">Failed loading tmux sessions: ${esc(err)}</div></div></div>`;
  }
}

document.addEventListener("click", async (e) => {
  const killBtn = e.target.closest("[data-kill-tmux]");
  if (killBtn) {
    e.preventDefault();
    const name = killBtn.dataset.killTmux;
    if (!confirm(`Terminate tmux session "${name}" and all processes in it?`)) return;
    killBtn.disabled = true;
    try {
      const res = await fetch("/api/tmux/kill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session: name }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        alert(data.message || "Failed to kill tmux session");
      }
      await loadTmuxSessions();
      await poll();
    } catch (err) {
      alert("Error: " + err);
    }
    return;
  }

  const renameBtn = e.target.closest("[data-rename-tmux]");
  if (renameBtn) {
    e.preventDefault();
    const oldName = renameBtn.dataset.renameTmux;
    const currentShort = oldName.startsWith("cockpit-") ? oldName.slice(8) : oldName;
    const newName = prompt(`Enter new name for tmux session "${oldName}":`, currentShort);
    if (!newName || newName.trim() === currentShort || newName.trim() === oldName) return;
    renameBtn.disabled = true;
    try {
      const res = await fetch("/api/tmux/rename", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session: oldName, name: newName.trim() }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        alert(data.message || "Failed to rename tmux session");
      }
      await loadTmuxSessions();
      await poll();
    } catch (err) {
      alert("Error: " + err);
    }
    return;
  }

  if (e.target && e.target.id === "btnToggleNewTmux") {
    const form = document.getElementById("formNewTmux");
    if (form) {
      const isHidden = form.style.display === "none";
      form.style.display = isHidden ? "block" : "none";
      if (isHidden) {
        const inp = document.getElementById("newTmuxName");
        if (inp) inp.focus();
      }
    }
  } else if (e.target && e.target.id === "btnCancelNewTmux") {
    const form = document.getElementById("formNewTmux");
    if (form) form.style.display = "none";
  }
});

document.addEventListener("submit", async (e) => {
  if (e.target && e.target.id === "formNewTmux") {
    e.preventDefault();
    const nameInp = document.getElementById("newTmuxName");
    const msgEl = document.getElementById("newTmuxMsg");
    const rawName = nameInp.value.trim();
    if (!rawName) return;
    if (msgEl) msgEl.textContent = "Creating session…";
    try {
      const res = await fetch("/api/tmux/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: rawName, cwd: "~" }),
      });
      const data = await res.json();
      if (res.ok && data.ok && data.session) {
        if (msgEl) msgEl.textContent = "Redirecting…";
        location.href = "/terminal?session=" + qs(data.session);
      } else {
        if (msgEl) msgEl.textContent = "Error: " + (data.message || "Failed to create session");
      }
    } catch (err) {
      if (msgEl) msgEl.textContent = "Error: " + err;
    }
  }
});

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-tab]");
  if (btn) {
    e.preventDefault();
    switchTab(btn.dataset.tab);
  }
});

document.addEventListener("click", (e) => {
  if (e.target && e.target.id === "btnToggleAddRepo") {
    const form = document.getElementById("formAddRepo");
    if (form) {
      const isHidden = form.style.display === "none";
      form.style.display = isHidden ? "block" : "none";
      if (isHidden) {
        const inp = document.getElementById("addRepoPath");
        if (inp) inp.focus();
      }
    }
  } else if (e.target && e.target.id === "btnCancelAddRepo") {
    const form = document.getElementById("formAddRepo");
    if (form) form.style.display = "none";
  }
});

document.addEventListener("input", (e) => {
  if (e.target && e.target.id === "addRepoPath") {
    const nameInp = document.getElementById("addRepoName");
    if (nameInp && (!nameInp.value.trim() || nameInp.dataset.autofilled)) {
      const parts = e.target.value.trim().replace(/[\/]+$/, "").split("/");
      const base = parts[parts.length - 1] || "";
      const deduced = base.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
      if (deduced) {
        nameInp.value = deduced;
        nameInp.dataset.autofilled = "true";
      }
    }
  }
  if (e.target && e.target.id === "addRepoName") {
    delete e.target.dataset.autofilled;
  }
});

document.addEventListener("submit", async (e) => {
  if (e.target && e.target.id === "formAddRepo") {
    e.preventDefault();
    let name = document.getElementById("addRepoName").value.trim();
    const path = document.getElementById("addRepoPath").value.trim();
    if (!name && path) {
      const parts = path.replace(/[\/]+$/, "").split("/");
      name = (parts[parts.length - 1] || "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
    }
    const note = document.getElementById("addRepoNote").value.trim();
    const msgEl = document.getElementById("addRepoMsg");
    if (msgEl) msgEl.textContent = "Adding and committing to git…";
    try {
      const res = await fetch("/api/ai-sessions/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, path, note })
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        if (msgEl) msgEl.textContent = "Error: " + (data.message || "Failed");
        return;
      }
      if (msgEl) msgEl.textContent = "✓ Added and committed to git!";
      e.target.reset();
      setTimeout(() => {
        document.getElementById("formAddRepo").style.display = "none";
        if (msgEl) msgEl.textContent = "";
      }, 1200);
      await poll();
    } catch (err) {
      if (msgEl) msgEl.textContent = "Error: " + err;
    }
  }
});

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-delete-session]");
  if (!btn) return;
  e.preventDefault();
  const name = btn.dataset.deleteSession;
  if (!confirm(`Remove preconfigured session "${name}" from services.conf and commit?`)) return;
  try {
    const res = await fetch("/api/ai-sessions/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      alert("Error: " + (data.message || "Failed"));
      return;
    }
    await poll();
  } catch (err) {
    alert("Error: " + err);
  }
});

// The cockpit always opens on AI Sessions, whatever tab was open last time.
switchTab("ai-sessions");
poll();
pollUsage();
setInterval(poll, REFRESH * 1000);
setInterval(pollUsage, Math.max(REFRESH, 60) * 1000);
