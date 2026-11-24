if (new URLSearchParams(window.location.search).get('embedded') === '1') {
  document.body.classList.add('embedded');
}

let state = {
  classes: {},
  clients: {},
  optiplex_projects: [],
  project_registry: {},
  overridden: { classes: [], clients: [] },
  stale: { classes: [], clients: [] },
  default_classes: [],
  default_clients: [],
  usage: null,
  fallback_status: { at: 95, classes: {} },
  models: {
    claude: { low: "claude-haiku-5-5", default: "claude-sonnet-5", deep: "claude-opus-5-5" },
    agy: { low: "gemini-3.8-flash-low", default: "gemini-3.8-flash-high", deep: "gemini-3.8-flash-high" }
  },
  available_models: {
    claude: ["claude-haiku-5-5", "claude-sonnet-5", "claude-opus-5-5"],
    agy: [
      "gemini-4-hydrogen-low", "gemini-4-hydrogen-medium", "gemini-4-hydrogen-high", "gemini-4-hydrogen-xhigh",
      "gemini-4-argon-low", "gemini-4-argon-medium", "gemini-4-argon-high",
      "gemini-4-neon-low", "gemini-4-neon-medium", "gemini-4-neon-high", "gemini-4-neon-xhigh",
      "gemini-3.8-flash-low", "gemini-3.8-flash-medium", "gemini-3.8-flash-high",
      "claude-sonnet-5-5-low", "claude-sonnet-5-5-medium", "claude-sonnet-5-5-high",
      "claude-opus-5-5-low", "claude-opus-5-5-medium", "claude-opus-5-5-high",
      "gpt-oss-120b-medium",
      "gemini-pro-orchestrator-neon", "gemini-pro-orchestrator-g1-pro"
    ]
  }
};
let quotaRetryTimer = null;

function inferAgyGroup(model) {
  if (!model) return "Gemini Models";
  const m = String(model).toLowerCase();
  if (m.startsWith("gemini-4-argon")) return "Gemini 4 Argon";
  if (m.startsWith("gemini-")) return "Gemini Models";
  if (m.startsWith("claude-") || m.startsWith("gpt-")) return "Claude and GPT models";
  return "Gemini Models";
}

function parseResetDate(raw) {
  if (!raw) return null;
  let d = new Date(raw);
  if (!isNaN(d.getTime())) return d;

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

function formatReset(reset, period) {
  if (!reset) return "";
  const d = parseResetDate(reset);
  if (!d) return reset;
  if (period === "five_hour") {
    const ms = d.getTime() - Date.now();
    if (ms <= 0) return "any moment";
    const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000);
    return h > 0 ? `in ${h}h ${m}m` : `in ${m}m`;
  }
  return d.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function banner(msg, isErr) {
  const b = document.getElementById('msgBanner');
  b.className = 'msg-banner ' + (isErr ? 'err' : 'ok');
  b.textContent = msg;
  b.style.display = 'block';
  setTimeout(() => { b.style.display = 'none'; }, 4000);
}

// One chip per meter: Claude's two bars, then each agy model group's.
function quotaChips(u) {
  const chips = [];
  const reserve = Number(state.fallback_status && state.fallback_status.reserve) || 0;
  const reserveYieldAt = reserve > 0 ? Math.max(1, 100 - reserve) : null;
  const level = (p, isReserveGroup) => {
    if (p >= 95) return 'danger';
    if (isReserveGroup && reserveYieldAt && p >= reserveYieldAt) return 'warn';
    return p >= 75 ? 'warn' : 'safe';
  };
  const chip = (label, b, period, isReserveGroup) => {
    if (!b || typeof b.pct !== 'number') return;
    const reset = formatReset(b.reset, period);
    const inReserve = isReserveGroup && reserveYieldAt && b.pct >= reserveYieldAt;
    const reserveTag = inReserve ? ' <span style="font-size: 10px; opacity: 0.85;">(in reserve)</span>' : '';
    chips.push(`<span class="qchip ${level(b.pct, isReserveGroup)}" title="${esc(reset ? 'resets ' + reset : '')}${inReserve ? ' · standard classes yielded at ' + reserveYieldAt + '%' : ''}">${esc(label)} <strong>${b.pct}%</strong>${reserveTag}</span>`);
  };
  if (u.claude && u.claude.state === 'ok') {
    chip('Claude 5h', (u.claude.bars || {}).five_hour, 'five_hour', false);
    chip('Claude week', (u.claude.bars || {}).weekly, 'weekly', false);
  }
  if (u.agy && u.agy.state === 'ok') {
    for (const [group, bars] of Object.entries(u.agy.groups || {})) {
      const name = 'agy ' + group.replace(/ models?$/i, '');
      const isGeminiGroup = group.toLowerCase().includes('gemini');
      chip(name + ' 5h', bars.five_hour, 'five_hour', isGeminiGroup);
      chip(name + ' week', bars.weekly, 'weekly', isGeminiGroup);
    }
  }
  if (reserve > 0) {
    chips.push(`<span class="qchip reserve-chip" style="background: rgba(59, 130, 246, 0.12); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); font-weight: 500;" title="20% quota headroom (80%–97%) reserved exclusively for critical classes (maintenance, managerial-audit). Standard dev yields at 80%.">🛡️ ${reserve}% Reserve (${reserveYieldAt}% cap)</span>`);
  }
  return chips;
}

function renderQuota(usage) {
  state.usage = usage || state.usage;
  const u = state.usage;
  const warnEl = document.getElementById('quotaWarningBanner');
  if (!u) return;
  const claudeOk = u.claude && u.claude.state === 'ok';
  const agyOk = u.agy && u.agy.state === 'ok';
  const strip = document.getElementById('quotaStrip');
  if (strip) {
    const chips = quotaChips(u);
    strip.innerHTML = chips.length ? chips.join('') : '<span class="muted">Plan usage unknown</span>';
  }

  const warnings = [
    ...((u.claude && u.claude.warnings) || []),
    ...((u.agy && u.agy.warnings) || [])
  ];
  if (warnEl) {
    if (warnings.length > 0) {
      warnEl.textContent = '⚠️ CLI Quota Parser Warning: ' + warnings.join(' | ');
      warnEl.style.display = 'block';
    } else {
      warnEl.style.display = 'none';
    }
  }

  if (strip && !(claudeOk && agyOk)) {
    const detail = (!claudeOk && u.claude && u.claude.detail) || (!agyOk && u.agy && u.agy.detail) || 'refreshing';
    strip.insertAdjacentHTML('beforeend', `<span class="muted">probing (${esc(detail)})…</span>`);
  }
}

async function pollQuota(force) {
  try {
    const url = '/api/usage' + (force ? '?refresh=1' : '');
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) return;
    const u = await res.json();
    if (u) {
      const wasDegraded = !state.usage || (state.usage.claude && state.usage.claude.state !== 'ok') || (state.usage.agy && state.usage.agy.state !== 'ok');
      renderQuota(u);
      renderClasses();
      if (typeof renderBoard === 'function') renderBoard();
      const isDegraded = !u.claude || u.claude.state !== 'ok' || !u.agy || u.agy.state !== 'ok';
      if (isDegraded || force) {
        clearTimeout(quotaRetryTimer);
        quotaRetryTimer = setTimeout(() => pollQuota(false), 3000);
      } else if (wasDegraded) {
        loadRoutes(false);
      }
    } else {
      clearTimeout(quotaRetryTimer);
      quotaRetryTimer = setTimeout(() => pollQuota(false), 2500);
    }
  } catch (e) {
    // ignore transient poll error
  }
}

function getModelName(tool, tier) {
  if (state.models && state.models[tool] && state.models[tool][tier]) {
    return state.models[tool][tier];
  }
  return tier || '';
}

function getFallbackSteps(c) {
  if (!c || !c.fallback) return [];
  if (Array.isArray(c.fallback)) return c.fallback.filter(s => s && s.tool);
  if (typeof c.fallback === 'object' && c.fallback.tool) return [c.fallback];
  return [];
}

function getFirstFallbackStep(c) {
  return getFallbackSteps(c)[0] || null;
}

function meterFromUsage(tool, group) {
  const u = state.usage && state.usage[tool];
  if (!u || u.state !== 'ok') return { pct: null, reset: '' };
  const bars = group ? ((u.groups && u.groups[group]) || {}) : (u.bars || {});
  let top = null;
  for (const b of Object.values(bars)) {
    if (b && typeof b.pct === 'number') {
      if (!top || b.pct > top.pct) top = b;
    }
  }
  return top ? { pct: top.pct, reset: top.reset || '' } : { pct: null, reset: '' };
}

function classPrimaryModel(c) {
  return (c && c.model) || getModelName((c && c.tool) || 'claude', (c && c.tier) || 'default');
}

function activeAllowanceOverride(name, c) {
  const fbCls = (state.fallback_status && state.fallback_status.classes && state.fallback_status.classes[name]) || {};
  const ov = (c && 'allowance_override' in c) ? c.allowance_override : fbCls.allowance_override;
  if (!ov || typeof ov !== 'object') return null;
  const pct = Number(ov.pct);
  if (!Number.isInteger(pct) || pct < 1 || pct > 100) return null;
  if (ov.expires_at) {
    const exp = parseResetDate(ov.expires_at);
    if (!exp || Date.now() >= exp.getTime()) return null;
  }
  return { pct, expires_at: ov.expires_at || '' };
}

function toolHasCriticalClasses(tool) {
  return Object.values(state.classes || {}).some(c => (c.tool || 'claude') === tool && c.priority === 'critical');
}

function classPrimaryAt(name, c) {
  const ov = activeAllowanceOverride(name, c);
  if (ov) return ov.pct;
  const base = Number(c && c.allowance);
  if (Number.isInteger(base) && base >= 1 && base <= 100) return base;
  const at = (state.fallback_status && state.fallback_status.at) || 95;
  const reserve = Number(state.fallback_status && state.fallback_status.reserve) || 0;
  const tool = (c && c.tool) || 'claude';
  if (reserve > 0 && (!c || c.priority !== 'critical') && toolHasCriticalClasses(tool)) {
    return Math.min(at, Math.max(1, 100 - reserve));
  }
  return at;
}

function setClassAllowanceOverride(name) {
  const cls = state.classes[name];
  if (!cls) return;
  const cur = classPrimaryAt(name, cls);
  const raw = prompt(`Temporary 5h-slot allowance % for "${name}" (1-100):`, String(cur));
  if (raw === null) return;
  const pct = Number(String(raw).trim());
  if (!Number.isInteger(pct) || pct < 1 || pct > 100) {
    alert('Allowance percentage must be an integer between 1 and 100.');
    return;
  }
  cls.allowance_override = { pct };
  state.classes[name] = cls;
  setDirty(true);
  renderClasses();
  if (typeof renderBoard === 'function') renderBoard();
}

function clearClassAllowanceOverride(name) {
  const cls = state.classes[name];
  if (!cls) return;
  cls.allowance_override = null;
  if (state.fallback_status && state.fallback_status.classes && state.fallback_status.classes[name]) {
    state.fallback_status.classes[name].allowance_override = null;
  }
  state.classes[name] = cls;
  setDirty(true);
  renderClasses();
  if (typeof renderBoard === 'function') renderBoard();
}

function computeClassLiveState(name, c) {
  const at = (state.fallback_status && state.fallback_status.at) || 95;
  const primaryAt = classPrimaryAt(name, c);
  const tool = c.tool || 'claude';
  const tier = c.tier || 'default';
  const effort = c.effort || '';
  const primaryModel = classPrimaryModel(c);
  const primaryGroup = tool === 'agy' ? inferAgyGroup(primaryModel) : null;
  const pMeter = meterFromUsage(tool, primaryGroup);
  const pExhausted = typeof pMeter.pct === 'number' && pMeter.pct >= primaryAt;
  const fbSteps = getFallbackSteps(c);
  const fbStep = fbSteps[0] || null;
  const reserve = Number(state.fallback_status && state.fallback_status.reserve) || 0;
  const isCritical = c && c.priority === 'critical';
  const hasAllowance = (c && c.allowance) || activeAllowanceOverride(name, c);
  const capNote = hasAllowance
    ? ` (${primaryAt}% allowance)`
    : (reserve > 0 && !isCritical && toolHasCriticalClasses(tool) ? ` (${primaryAt}% cap, ${reserve}% reserve)` : (primaryAt !== at ? ` (${primaryAt}% cap)` : ''));

  if (!pExhausted) {
    const pPctStr = typeof pMeter.pct === 'number' ? ` (${pMeter.pct}% used${primaryAt !== at ? `, ${primaryAt}% cap` : ''})` : (primaryAt !== at ? ` (${primaryAt}% cap)` : '');
    const fbNote = fbStep
      ? `Fallback ready: <code>${esc(fbStep.tool)}/${esc(fbStep.model)}</code>`
      : 'No fallback configured';
    return {
      state: 'ok',
      pillText: '✓ PRIMARY ACTIVE',
      effectiveText: `${tool} / ${primaryModel}` + (effort ? ` (${effort})` : ''),
      subText: `Primary${pPctStr} · ${fbNote}`
    };
  }

  const resetFmt = formatReset(pMeter.reset, 'weekly') || pMeter.reset || 'reset window';
  let lastFbMeter = null;
  for (const step of fbSteps) {
    if (!step.tool || !step.model) continue;
    const fbGroup = step.group || (step.tool === 'agy' ? inferAgyGroup(step.model) : null);
    const fbMeter = meterFromUsage(step.tool, fbGroup);
    const stepAt = typeof step.at === 'number' ? step.at : at;
    const fbExhausted = typeof fbMeter.pct === 'number' && fbMeter.pct >= stepAt;
    lastFbMeter = fbMeter;
    if (!fbExhausted) {
      const fbPctStr = typeof fbMeter.pct === 'number' ? ` (${fbMeter.pct}% used)` : '';
      return {
        state: 'fallback',
        pillText: '⚡ ON FALLBACK',
        effectiveText: `${step.tool} / ${step.model}${fbPctStr}`,
        subText: `Primary ${esc(primaryModel)} at ${pMeter.pct}%${capNote} · retests primary at ${esc(resetFmt)}`
      };
    }
  }
  if (lastFbMeter !== null) {
    const fbLabel = fbSteps.length > 1 ? `all ${fbSteps.length} fallbacks (${lastFbMeter.pct}%)` : `fallback (${lastFbMeter.pct}%)`;
    return {
      state: 'blocked',
      pillText: '⛔ ALL EXHAUSTED',
      effectiveText: `${tool} / ${primaryModel}`,
      subText: `Primary (${pMeter.pct}%${capNote}) & ${fbLabel} full · next OK: ${esc(resetFmt)}`
    };
  }

  return {
    state: 'blocked',
    pillText: '⛔ QUOTA FULL (NO FALLBACK)',
    effectiveText: `${tool} / ${primaryModel} (paused)`,
    subText: `${tool} at ${pMeter.pct}%${capNote} · no fallback · next OK: ${esc(resetFmt)}`
  };
}

function renderClassLiveCell(cell, name, c) {
  const info = computeClassLiveState(name, c);
  cell.innerHTML = `
    <div><span class="state-pill ${info.state}">${esc(info.pillText)}</span></div>
    <div><span class="badge model-tag class-model">${esc(info.effectiveText)}</span></div>
    <div class="state-sub">${info.subText}</div>
  `;
}

function fallbackModelOptionsHtml(fbTool, selectedModel) {
  if (!fbTool) return '<option value="">(no fallback)</option>';
  const list = (state.available_models && state.available_models[fbTool]) || [];
  const defaultModel = fbTool === 'agy' ? 'gemini-4-argon-medium' : 'claude-sonnet-5';
  const target = selectedModel && list.includes(selectedModel) ? selectedModel : defaultModel;
  return list.map(m => `<option value="${esc(m)}" ${m === target ? 'selected' : ''}>${esc(m)}</option>`).join('');
}

function renderClasses() {
  const tbody = document.getElementById('classesTbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  const entries = Object.entries(state.classes).sort(([a], [b]) => a.localeCompare(b));
  if (entries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--muted); padding: 20px;">No classes configured.</td></tr>';
    return;
  }

  for (const [name, c] of entries) {
    const tr = document.createElement('tr');
    tr.dataset.className = name;
    const fbStep = getFirstFallbackStep(c);
    const fbTool = fbStep ? fbStep.tool : '';
    const fbModel = fbStep ? fbStep.model : '';
    const isStale = state.stale.classes.includes(name);
    const isOverridden = state.overridden.classes.includes(name);
    const overrideTag = isStale
      ? ` <button type="button" class="btn secondary small" title="Override refers to a class aicli.toml no longer defines" onclick="resetRoute('classes', '${esc(name)}')">stale override · Remove</button>`
      : isOverridden
        ? ` <button type="button" class="btn secondary small" onclick="resetRoute('classes', '${esc(name)}')">overridden · Reset</button>`
        : '';

    tr.innerHTML = `
      <td><span class="badge class-name">${esc(name)}</span>${c.priority === 'critical' ? ' <span class="chip priority-critical" style="color: #f87171; border-color: rgba(239, 68, 68, 0.4);">critical</span>' : ''}${overrideTag}</td>
      <td>
        <div><strong>${esc(c.description || '')}</strong></div>
        <div style="color: var(--muted); font-size: 11px; margin-top: 2px;">Frequency: ${esc(c.frequency || 'N/A')}</div>
      </td>
      <td>
        <div class="route-controls">
          <select class="form-control class-tool" title="Primary CLI tool" onchange="onClassChange(this.closest('tr'))">
            <option value="claude" ${c.tool === 'claude' ? 'selected' : ''}>Claude Code</option>
            <option value="agy" ${c.tool === 'agy' ? 'selected' : ''}>Gemini (agy)</option>
          </select>
          <select class="form-control class-tier" title="Primary tier" onchange="onClassChange(this.closest('tr'))">
            <option value="low" ${c.tier === 'low' ? 'selected' : ''}>low</option>
            <option value="default" ${(!c.tier || c.tier === 'default') ? 'selected' : ''}>default</option>
            <option value="deep" ${c.tier === 'deep' ? 'selected' : ''}>deep</option>
          </select>
          <select class="form-control class-effort" title="Primary reasoning effort" onchange="onClassChange(this.closest('tr'))">
            <option value="low" ${c.effort === 'low' ? 'selected' : ''}>effort: low</option>
            <option value="medium" ${(!c.effort || c.effort === 'medium') ? 'selected' : ''}>effort: medium</option>
            <option value="high" ${c.effort === 'high' ? 'selected' : ''}>effort: high</option>
          </select>
          <select class="form-control class-priority" title="Workload priority (critical gets full quota ceiling; standard yields at reserve threshold)" onchange="onClassChange(this.closest('tr'))">
            <option value="standard" ${c.priority !== 'critical' ? 'selected' : ''}>standard</option>
            <option value="critical" ${c.priority === 'critical' ? 'selected' : ''}>critical</option>
          </select>
        </div>
        <div class="state-sub">Primary model: <code>${esc(classPrimaryModel(c))}</code></div>
        ${(c.allowance || activeAllowanceOverride(name, c)) ? (() => {
          const ov = activeAllowanceOverride(name, c);
          const jn = esc(JSON.stringify(name));
          const cap = c.allowance ? `<span class="badge">${esc(c.allowance)}% cap</span>` : '';
          const ovBadge = ov
            ? ` <span class="badge">Override: ${esc(ov.pct)}%${ov.expires_at ? ` until ${esc(formatReset(ov.expires_at, 'five_hour') || ov.expires_at)}` : ''}</span> <button type="button" class="btn secondary small" onclick="clearClassAllowanceOverride(${jn})">Clear override</button>`
            : '';
          return `<div class="state-sub">${cap}${ovBadge} <button type="button" class="btn secondary small" onclick="setClassAllowanceOverride(${jn})">Override 5h cap</button></div>`;
        })() : ''}
      </td>
      <td>
        <div class="route-controls">
          <select class="form-control class-fb-tool" title="Fallback tool when primary quota >= 95%" onchange="onFallbackToolChange(this.closest('tr'))">
            <option value="" ${!fbTool ? 'selected' : ''}>No fallback</option>
            <option value="agy" ${fbTool === 'agy' ? 'selected' : ''}>Fallback: agy</option>
            <option value="claude" ${fbTool === 'claude' ? 'selected' : ''}>Fallback: claude</option>
          </select>
          <select class="form-control class-fb-model" title="Fallback model" style="${fbTool ? '' : 'display:none;'}" onchange="onClassChange(this.closest('tr'))">
            ${fallbackModelOptionsHtml(fbTool, fbModel)}
          </select>
        </div>
      </td>
      <td class="class-live-cell"></td>
    `;
    renderClassLiveCell(tr.querySelector('.class-live-cell'), name, c);
    tbody.appendChild(tr);
  }
}

function onFallbackToolChange(tr) {
  const fbTool = tr.querySelector('.class-fb-tool').value;
  const fbModelSel = tr.querySelector('.class-fb-model');
  if (!fbTool) {
    fbModelSel.style.display = 'none';
    fbModelSel.innerHTML = '<option value="">(no fallback)</option>';
  } else {
    fbModelSel.style.display = '';
    fbModelSel.innerHTML = fallbackModelOptionsHtml(fbTool, '');
  }
  onClassChange(tr);
}

function onClassChange(tr) {
  const className = tr.dataset.className;
  const tool = tr.querySelector('.class-tool').value;
  const tier = tr.querySelector('.class-tier').value;
  const effort = tr.querySelector('.class-effort').value;
  const prioritySel = tr.querySelector('.class-priority');
  const priority = prioritySel ? prioritySel.value : '';
  const fbTool = tr.querySelector('.class-fb-tool').value;
  const fbModel = tr.querySelector('.class-fb-model').value;

  const cls = state.classes[className] || {};
  cls.tool = tool;
  cls.tier = tier;
  if (effort) {
    cls.effort = effort;
  } else {
    delete cls.effort;
  }
  if (priority === 'critical') {
    cls.priority = 'critical';
  } else {
    delete cls.priority;
  }
  if (fbTool && fbModel) {
    cls.fallback = {
      tool: fbTool,
      model: fbModel,
      ...(fbTool === 'agy' ? { group: inferAgyGroup(fbModel) } : {})
    };
  } else {
    cls.fallback = null;
  }
  state.classes[className] = cls;
  setDirty(true);
  renderClassLiveCell(tr.querySelector('.class-live-cell'), className, cls);
}

function renderClients() {
  const tbody = document.getElementById('clientsTbody');
  tbody.innerHTML = '';
  const modelList = document.getElementById('modelList');
  if (modelList) {
    const all = Object.values(state.available_models || {}).flat();
    modelList.innerHTML = [...new Set(all)].map(m => `<option value="${esc(m)}"></option>`).join('');
  }
  const entries = Object.entries(state.clients).sort(([a], [b]) => a.localeCompare(b));
  if (entries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--muted); padding: 16px;">No clients configured.</td></tr>';
    return;
  }

  for (const [clientId, c] of entries) {
    const tr = document.createElement('tr');
    tr.dataset.client = clientId;
    const descText = c.description ? esc(c.description) : '<span style="color:var(--muted); font-style:italic;">Default client</span>';
    const freqText = c.frequency ? `<div style="font-size: 11px; color: var(--muted); margin-top: 2px;">${esc(c.frequency)}</div>` : '';
    tr.innerHTML = `
      <td><code>${esc(clientId)}</code></td>
      <td>
        <div>${descText}</div>
        ${freqText}
      </td>
      <td>
        <select class="form-control client-class" onchange="onClientChange(this.closest('tr'))">
          <option value="">(none)</option>
          ${Object.keys(state.classes).map(k => `<option value="${esc(k)}" ${c.class === k ? 'selected' : ''}>${esc(k)}</option>`).join('')}
        </select>
      </td>
      <td>
        <select class="form-control client-tool" onchange="onClientChange(this.closest('tr'))">
          <option value="" ${!c.tool ? 'selected' : ''}>Inherit from class</option>
          <option value="claude" ${c.tool === 'claude' ? 'selected' : ''}>Claude Code</option>
          <option value="agy" ${c.tool === 'agy' ? 'selected' : ''}>Gemini (agy)</option>
        </select>
      </td>
      <td>
        <select class="form-control client-tier" onchange="onClientChange(this.closest('tr'))">
          <option value="" ${!c.tier ? 'selected' : ''}>Inherit from class</option>
          <option value="low" ${c.tier === 'low' ? 'selected' : ''}>low</option>
          <option value="default" ${c.tier === 'default' ? 'selected' : ''}>default</option>
          <option value="deep" ${c.tier === 'deep' ? 'selected' : ''}>deep</option>
        </select>
      </td>
      <td>
        <input type="text" class="form-control client-model client-temporary-override" list="modelList" placeholder="temporary_override (5h max)"
               title="temporary_override lasts up to 5 hours. Reuse an existing class or define one in aicli.toml instead of using permanent overrides."
               value="${esc(c.temporary_override || c.model || '')}" onchange="onClientChange(this.closest('tr'))">
        ${(c.temporary_override || c.model) && (c.temporary_override_expires_at || c.model_expires_at) ? `<div style="font-size: 11px; color: var(--accent); margin-top: 2px;" title="${esc(c.temporary_override_expires_at || c.model_expires_at)}">⏳ temporary_override: expires ${esc(formatReset(c.temporary_override_expires_at || c.model_expires_at, 'five_hour') || (c.temporary_override_expires_at || c.model_expires_at))}</div>` : ''}
      </td>
      <td style="text-align: right;">
        <button type="button" class="btn danger small" onclick="removeClient(this.closest('tr').dataset.client)">${state.default_clients.includes(clientId) ? 'Reset' : 'Remove'}</button>
      </td>
    `;
    tbody.appendChild(tr);
  }
}

// Drops a class's or client's whole state-file override - "Reset" for a
// row aicli.toml still defines (back to its default), "Remove" for one that
// only exists because the cockpit or `aicli route` added it. Applied right
// away, not deferred to Save, since there is no "undo" edit to batch here.
async function resetRoute(section, name) {
  const data = await postJSON('/api/ai-routes', { reset: { [section]: [name] } });
  if (data.ok === false) {
    banner("Failed to reset " + name + ": " + (data.message || "request failed"), true);
    return;
  }
  banner((state.default_classes.includes(name) || state.default_clients.includes(name) ? "Reset " : "Removed ") + name + ".");
  loadRoutes(false);
}

function onClientChange(tr) {
  const clientId = tr.dataset.client;
  const cls = tr.querySelector('.client-class').value;
  const tool = tr.querySelector('.client-tool').value;
  const tier = tr.querySelector('.client-tier').value;
  const overrideVal = (tr.querySelector('.client-temporary-override') || tr.querySelector('.client-model')).value.trim();
  const prev = state.clients[clientId] || {};
  const prevExp = prev.temporary_override_expires_at || prev.model_expires_at;
  const prevVal = prev.temporary_override || prev.model;
  state.clients[clientId] = {
    ...prev,
    class: cls || undefined,
    tool: tool || undefined,
    tier: tier || undefined,
    model: overrideVal || undefined,
    temporary_override: overrideVal || undefined,
    model_expires_at: overrideVal ? (prevVal === overrideVal && prevExp ? prevExp : undefined) : undefined,
    temporary_override_expires_at: overrideVal ? (prevVal === overrideVal && prevExp ? prevExp : undefined) : undefined
  };
  setDirty(true);
}

function addClientRow() {
  const clientId = prompt("Enter client identifier (e.g. pjm:auto-execute, or pjm:auto-spec@deep-spec to pin it for one class):");
  if (!clientId || !clientId.trim()) return;
  const cleanId = clientId.trim();
  if (state.clients[cleanId]) {
    alert("Client already exists.");
    return;
  }
  state.clients[cleanId] = { class: "maintenance" };
  setDirty(true);
  renderAll();
}

function removeClient(clientId) {
  resetRoute('clients', clientId);
}

// Both views draw from `state`; the board lives in ai_routes_board.js.
function renderAll() {
  renderClasses();
  renderClients();
  renderProjects();
  if (typeof renderBoard === 'function') renderBoard();
}

function setDirty(on) {
  const tag = document.getElementById('dirtyTag');
  if (tag) tag.style.display = on ? '' : 'none';
  const fab = document.getElementById('saveFab');
  if (fab) {
    fab.classList.toggle('dirty', !!on);
    fab.title = fab.ariaLabel = on ? 'Save all routes (unsaved changes)' : 'Save all routes';
  }
}

// Feedback beside the floating Save, where the eye already is.
let saveToastTimer = null;
function saveFeedback(kind, msg) {
  const fab = document.getElementById('saveFab');
  const t = document.getElementById('saveToast');
  if (fab) {
    fab.classList.remove('saving', 'ok', 'err');
    if (kind) fab.classList.add(kind);
    fab.disabled = kind === 'saving';
  }
  if (!t) return;
  clearTimeout(saveToastTimer);
  t.className = 'save-toast' + (msg ? ' show ' + kind : '');
  t.textContent = msg || '';
  if (kind === 'ok' || kind === 'err') {
    saveToastTimer = setTimeout(() => {
      t.classList.remove('show');
      if (fab) fab.classList.remove('ok', 'err');
    }, kind === 'err' ? 6000 : 2500);
  }
}

function projectClients(name) {
  return Object.keys(state.clients).filter(id => id === name || id.startsWith(name + ':'));
}

function renderProjects() {
  const container = document.getElementById('projectsList');
  if (!container) return;
  container.innerHTML = '';
  const names = Object.keys(state.project_registry).sort();
  if (names.length === 0) {
    container.innerHTML = '<span style="color: var(--muted); font-size: 13px;">No projects registered.</span>';
    return;
  }
  for (const name of names) {
    const enabled = state.project_registry[name].enabled;
    const n = projectClients(name).length;
    const row = document.createElement('div');
    row.dataset.project = name;
    row.style.cssText = 'display:flex; align-items:center; gap:12px; padding:6px 0;' + (enabled ? '' : ' opacity:0.6;');
    row.innerHTML = `
      <label style="display:flex; align-items:center; gap:8px; flex:1; cursor:pointer;">
        <input type="checkbox" ${enabled ? 'checked' : ''} onchange="setProjectEnabled(this.closest('[data-project]').dataset.project, this.checked)">
        🖥️ <strong>${esc(name)}</strong>
        <span style="font-size:12px; color:var(--muted);">${enabled ? 'enabled' : 'disabled'} · ${n} client ID${n === 1 ? '' : 's'} kept</span>
      </label>
      <button type="button" class="btn secondary small" onclick="removeProject(this.closest('[data-project]').dataset.project)">Unregister</button>`;
    container.appendChild(row);
  }
}

function addProject() {
  const name = prompt("Project name to register (runs on OptiPlex with aicli access):");
  if (!name || !name.trim()) return;
  const clean = name.trim();
  if (state.project_registry[clean]) {
    alert("Project already registered.");
    return;
  }
  state.project_registry[clean] = { enabled: true };
  setDirty(true);
  renderAll();
}

function setProjectEnabled(name, enabled) {
  state.project_registry[name] = { enabled };
  setDirty(true);
  renderAll();
}

function removeProject(name) {
  // Only the registry entry goes; its client IDs and overrides stay in the table above.
  delete state.project_registry[name];
  setDirty(true);
  renderAll();
}

async function loadRoutes(forceRefresh) {
  try {
    fetchAuthStatus();
    const url = '/api/ai-routes' + (forceRefresh ? '?refresh=1' : '');
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    state.classes = data.classes || {};
    state.clients = data.clients || {};
    state.optiplex_projects = data.optiplex_projects || [];
    state.project_registry = data.project_registry || {};
    state.overridden = data.overridden || { classes: [], clients: [] };
    state.stale = data.stale || { classes: [], clients: [] };
    state.default_classes = data.default_classes || [];
    state.default_clients = data.default_clients || [];
    state.fallback_status = data.fallback_status || { at: 95, classes: {} };
    if (data.models) state.models = data.models;
    if (data.available_models && Object.keys(data.available_models).length > 0) {
      state.available_models = data.available_models;
    }
    renderQuota(data.usage);
    renderAll();
    setDirty(false);
    if (forceRefresh || !data.usage || !data.usage.claude || data.usage.claude.state !== 'ok') {
      clearTimeout(quotaRetryTimer);
      quotaRetryTimer = setTimeout(() => pollQuota(false), 3000);
    }
  } catch (err) {
    banner("Failed to load routes: " + err.message, true);
  }
}

async function saveRoutes() {
  const payload = {
    classes: state.classes,
    clients: state.clients,
    project_registry: state.project_registry
  };
  saveFeedback('saving', 'Saving…');
  const data = await postJSON('/api/ai-routes', payload);
  if (data.ok === false && !data.routes) {
    saveFeedback('err', "Save failed: " + (data.message || "request failed"));
    banner("Failed to save routes: " + (data.message || "request failed"), true);
    return;
  }
  saveFeedback('ok', 'Saved');
  banner("Routes & fallback configuration saved! Applied immediately across homelab and aicli.");
  loadRoutes(false);
}

let currentAuthStatus = null;

async function fetchAuthStatus() {
  try {
    const res = await fetch('/api/ai/reauth/status', { cache: 'no-store' });
    if (!res.ok) return;
    const data = await res.json();
    currentAuthStatus = data;
    const claudeTag = document.getElementById('claudeAuthStatusTag');
    if (claudeTag && data.claude) {
      if (data.claude.authenticated) {
        claudeTag.className = 'auth-status-tag ok';
        claudeTag.textContent = 'Active';
      } else {
        claudeTag.className = 'auth-status-tag expired';
        claudeTag.textContent = 'Session Expired';
      }
    }
    const agyTag = document.getElementById('agyAuthStatusTag');
    if (agyTag && data.agy) {
      if (data.agy.authenticated) {
        agyTag.className = 'auth-status-tag ok';
        agyTag.textContent = 'Active' + (data.agy.account ? ' (' + data.agy.account + ')' : '');
      } else {
        agyTag.className = 'auth-status-tag expired';
        agyTag.textContent = 'Not Signed In';
      }
    }
  } catch (e) {
    console.error('Failed fetching auth status:', e);
  }
}

async function openClaudeReauth() {
  const modal = document.getElementById('claudeReauthModal');
  const loading = document.getElementById('claudeReauthLoading');
  const step = document.getElementById('claudeReauthStep');
  const footer = document.getElementById('claudeReauthFooter');
  const errBox = document.getElementById('claudeReauthError');
  const link = document.getElementById('claudeOAuthLink');
  const input = document.getElementById('claudeAuthCodeInput');

  if (!modal) return;
  modal.style.display = 'flex';
  loading.style.display = 'block';
  step.style.display = 'none';
  footer.style.display = 'none';
  if (errBox) errBox.style.display = 'none';
  if (input) input.value = '';

  try {
    const res = await postJSON('/api/ai/reauth/claude/start', {});
    if (res && res.ok && res.auth_url) {
      link.href = res.auth_url;
      loading.style.display = 'none';
      step.style.display = 'block';
      footer.style.display = 'flex';
      setTimeout(() => { if (input) input.focus(); }, 100);
      try {
        window.open(res.auth_url, '_blank');
      } catch (e) {}
    } else {
      loading.innerHTML = '<p class="err" style="color:var(--down); margin:0;">Failed to start login: ' + esc(res && res.error || 'unknown error') + '</p>';
      footer.style.display = 'flex';
    }
  } catch (err) {
    loading.innerHTML = '<p class="err" style="color:var(--down); margin:0;">Network error: ' + esc(err.message) + '</p>';
    footer.style.display = 'flex';
  }
}

async function closeClaudeReauth() {
  const modal = document.getElementById('claudeReauthModal');
  if (modal) modal.style.display = 'none';
  try {
    await postJSON('/api/ai/reauth/claude/cancel', {});
  } catch (e) {}
}

async function submitClaudeCode() {
  const input = document.getElementById('claudeAuthCodeInput');
  const errBox = document.getElementById('claudeReauthError');
  const btn = document.getElementById('btnSubmitClaudeCode');
  const code = (input && input.value || '').trim();

  if (!code) {
    if (errBox) {
      errBox.textContent = 'Please enter the authorization code from Claude.';
      errBox.style.display = 'block';
    }
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Verifying…';
  }
  if (errBox) errBox.style.display = 'none';

  try {
    const res = await postJSON('/api/ai/reauth/claude/submit', { code: code });
    if (res && res.ok) {
      const modal = document.getElementById('claudeReauthModal');
      if (modal) modal.style.display = 'none';
      banner('🎉 ' + (res.message || 'Claude Code re-authenticated successfully!'));
      fetchAuthStatus();
      pollQuota(true);
      loadRoutes(true);
    } else {
      if (errBox) {
        errBox.textContent = 'Authentication failed: ' + (res && res.error || 'Code rejected');
        errBox.style.display = 'block';
      }
    }
  } catch (err) {
    if (errBox) {
      errBox.textContent = 'Request failed: ' + err.message;
      errBox.style.display = 'block';
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Complete Sign-In';
    }
  }
}

const AGY_LINK_POLL_INTERVAL_MS = 2000;
const AGY_LINK_POLL_TIMEOUT_MS = 120000;
let agyLinkPollTimer = null;
let agyLinkPollDeadline = 0;

async function openAgyReauth() {
  const modal = document.getElementById('agyReauthModal');
  const text = document.getElementById('agyModalStatusText');
  const loading = document.getElementById('agyReauthLoading');
  const linkBox = document.getElementById('agyReauthLink');
  const errBox = document.getElementById('agyReauthError');
  if (!modal) return;
  modal.style.display = 'flex';
  if (text) {
    if (currentAuthStatus && currentAuthStatus.agy && currentAuthStatus.agy.authenticated) {
      text.innerHTML = '<strong>Status:</strong> Active &amp; Authenticated.<br>Account: <code>' + esc(currentAuthStatus.agy.account || 'Google') + '</code>';
    } else {
      text.innerHTML = '<strong>Status:</strong> <span style="color:var(--down); font-weight:600;">Not Signed In</span>.';
    }
  }
  if (loading) loading.style.display = 'block';
  if (linkBox) linkBox.style.display = 'none';
  if (errBox) errBox.style.display = 'none';

  try {
    const res = await postJSON('/api/ai/reauth/agy/start', {});
    if (!res || !res.ok) {
      if (loading) loading.style.display = 'none';
      if (errBox) {
        errBox.textContent = 'Failed to start AGY sign-in session: ' + (res && res.error || 'unknown error');
        errBox.style.display = 'block';
      }
      return;
    }
  } catch (err) {
    if (loading) loading.style.display = 'none';
    if (errBox) {
      errBox.textContent = 'Failed to start AGY sign-in session: ' + err.message;
      errBox.style.display = 'block';
    }
    return;
  }

  startAgyLinkPoll();
}

function stopAgyLinkPoll() {
  clearTimeout(agyLinkPollTimer);
  agyLinkPollTimer = null;
}

function startAgyLinkPoll() {
  stopAgyLinkPoll();
  agyLinkPollDeadline = Date.now() + AGY_LINK_POLL_TIMEOUT_MS;
  pollAgyLink();
}

async function pollAgyLink() {
  const modal = document.getElementById('agyReauthModal');
  if (!modal || modal.style.display === 'none') {
    stopAgyLinkPoll();
    return;
  }
  const loading = document.getElementById('agyReauthLoading');
  const linkBox = document.getElementById('agyReauthLink');
  const link = document.getElementById('agyOAuthLink');
  const errBox = document.getElementById('agyReauthError');

  try {
    const res = await fetch('/api/ai/reauth/agy/link', { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (data && data.url) {
        if (link) link.href = data.url;
        if (loading) loading.style.display = 'none';
        if (linkBox) linkBox.style.display = 'block';
        if (errBox) errBox.style.display = 'none';
        stopAgyLinkPoll();
        return;
      }
    }
  } catch (e) {
    // transient poll error, keep trying until the timeout
  }

  if (Date.now() >= agyLinkPollDeadline) {
    if (loading) loading.style.display = 'none';
    if (linkBox) linkBox.style.display = 'none';
    if (errBox) {
      errBox.textContent = "No sign-in link showed up yet. Open the setup terminal below to finish signing in.";
      errBox.style.display = 'block';
    }
    stopAgyLinkPoll();
    return;
  }

  agyLinkPollTimer = setTimeout(pollAgyLink, AGY_LINK_POLL_INTERVAL_MS);
}

function copyAgyLink() {
  const link = document.getElementById('agyOAuthLink');
  const url = link && link.getAttribute('href');
  if (!url || url === '#') return;
  if (!navigator.clipboard || !navigator.clipboard.writeText) {
    banner('Copy is not supported in this browser.', true);
    return;
  }
  navigator.clipboard.writeText(url).then(
    () => banner('Link copied.'),
    () => banner('Could not copy link.', true)
  );
}

function closeAgyReauth() {
  const modal = document.getElementById('agyReauthModal');
  if (modal) modal.style.display = 'none';
  stopAgyLinkPoll();
  fetchAuthStatus();
}

function launchAgyTerminal() {
  window.open('/terminal?session=cockpit-agy-reauth', '_blank');
}

document.addEventListener('DOMContentLoaded', () => {
  loadRoutes(false);
  fetchAuthStatus();
  setInterval(() => {
    pollQuota(false);
    fetchAuthStatus();
  }, 30000);
});
