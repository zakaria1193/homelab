"""/cron: the cron-manager jobs."""

from .theme import THEME

CRON_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cron Jobs · __TITLE__</title>
<style>
  {THEME}
  .wrap { max-width: 1050px; margin: 0 auto; padding: 24px 18px 64px; }
  body.embedded .wrap { padding: 12px 14px; max-width: 100%; }
  body.embedded header .back { display: none; }
  header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px; }
  h1 { font-size: 22px; margin: 0; display: flex; align-items: center; gap: 8px; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .back:hover { color: var(--text); }
  .top-right { display: flex; align-items: center; gap: 10px; }
  .lede { color: var(--muted); font-size: 13px; margin: 8px 0 16px; max-width: 75ch; }
  .badge { font-size: 11px; padding: 2px 7px; border-radius: 999px; background: var(--raise); border: 1px solid var(--border); color: var(--muted); font-weight: 500; display: inline-block; }
  .badge.active { color: var(--up); border-color: rgba(63,185,80,0.3); background: rgba(63,185,80,0.08); }
  .badge.disabled { color: var(--muted); border-color: var(--border); }
  .badge.security { color: #d29922; border-color: rgba(210,153,34,0.3); background: rgba(210,153,34,0.08); }
  .badge.maint { color: var(--accent); border-color: rgba(88,166,255,0.3); background: rgba(88,166,255,0.08); }
  .table-container { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; margin-top: 14px; }
  table.cron-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
  table.cron-table th { background: var(--raise); color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; padding: 10px 14px; border-bottom: 1px solid var(--border); }
  table.cron-table td { padding: 12px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }
  table.cron-table tr:last-child td { border-bottom: none; }
  table.cron-table tr:hover { background: rgba(255,255,255,0.02); }
  table.cron-table tr.disabled td { opacity: 0.65; }
  .job-name-cell { font-weight: 600; font-size: 14px; color: var(--text); }
  .job-id-code { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; color: var(--muted); margin-top: 2px; }
  .cron-code { font-family: ui-monospace, SFMono-Regular, monospace; background: var(--bg); border: 1px solid var(--border); padding: 2px 6px; border-radius: 4px; font-size: 12px; display: inline-block; }
  .cmd-block { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; background: var(--bg); border: 1px solid var(--border); padding: 6px 10px; border-radius: 5px; color: var(--text); word-break: break-all; white-space: pre-wrap; max-height: 85px; overflow-y: auto; margin-top: 4px; }
  .actions-cell { display: flex; gap: 6px; justify-content: flex-end; align-items: center; }
  button { background: var(--panel); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 4px 10px; font-size: 12px; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; font-weight: 500; }
  button:hover { border-color: var(--muted); background: var(--raise); }
  button.btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); }
  button.btn-primary:hover { opacity: 0.9; }
  button.btn-danger { color: var(--down); }
  button.btn-danger:hover { border-color: var(--down); background: rgba(248,81,73,0.1); }
  .modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 100; opacity: 0; pointer-events: none; transition: opacity 0.15s; }
  .modal-bg.open { opacity: 1; pointer-events: auto; }
  .modal { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 20px; width: 100%; max-width: 520px; }
  .modal h2 { margin: 0 0 14px; font-size: 18px; }
  .form-group { margin-bottom: 12px; }
  .form-group label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
  .form-group input, .form-group textarea, .form-group select { width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 7px 10px; font-size: 13px; font-family: inherit; }
  .modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
  .msg-banner { margin-top: 10px; padding: 10px 14px; border-radius: 6px; font-size: 13px; display: none; }
  .msg-banner.ok { background: rgba(63,185,80,0.15); border: 1px solid var(--up); color: var(--up); }
  .msg-banner.err { background: rgba(248,81,73,0.15); border: 1px solid var(--down); color: var(--down); }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>⏰ Cron Jobs Viewer & Editor</h1>
    <div class="top-right">
      <button type="button" class="btn-primary" onclick="openAddModal()">+ Add New Job</button>
      <a class="back" href="/">&larr; Back to Cockpit</a>
    </div>
  </header>
  <p class="lede">Manage scheduled maintenance, weekly security audits, system upgrades, and automated background tasks across your homelab.</p>
  
  <div id="msgBanner" class="msg-banner"></div>

  <div class="table-container">
    <table class="cron-table">
      <thead>
        <tr>
          <th style="width: 85px;">Status</th>
          <th style="width: 220px;">Job & ID</th>
          <th style="width: 110px;">Category</th>
          <th style="width: 120px;">Schedule</th>
          <th>Command & Description</th>
          <th style="width: 175px; text-align: right;">Actions</th>
        </tr>
      </thead>
      <tbody id="jobsList">
        <tr><td colspan="6" style="text-align: center; color: var(--muted); padding: 24px;">Loading scheduled jobs...</td></tr>
      </tbody>
    </table>
  </div>

  <footer style="margin-top: 40px; color: var(--muted); font-size: 12px;">
    Homelab Cron Manager · Registered in <code>tools/cron-manager/crontab.json</code>
  </footer>
</div>

<!-- Modal for Add New Job -->
<div id="addModal" class="modal-bg">
  <div class="modal">
    <h2>Add New Cron Job</h2>
    <form id="addForm">
      <div class="form-group">
        <label>Job ID (alphanumeric, e.g. <code>db-backup</code>)</label>
        <input type="text" id="addId" required pattern="[a-zA-Z0-9_-]+">
      </div>
      <div class="form-group">
        <label>Job Name</label>
        <input type="text" id="addName" required placeholder="e.g. Daily Vault Backup">
      </div>
      <div class="form-group">
        <label>Schedule (Cron expression, e.g. <code>0 9 * * 1</code>)</label>
        <input type="text" id="addSchedule" required placeholder="0 9 * * 1">
      </div>
      <div class="form-group">
        <label>Category</label>
        <input type="text" id="addCategory" placeholder="Security, Maintenance, Backup...">
      </div>
      <div class="form-group">
        <label>Shell Command</label>
        <textarea id="addCommand" rows="3" required placeholder="tools/slackbot-notify.sh 'Job executed'"></textarea>
      </div>
      <div class="form-group">
        <label>Description</label>
        <input type="text" id="addDesc" placeholder="Short description of purpose">
      </div>
      <div class="modal-actions">
        <button type="button" onclick="closeAddModal()">Cancel</button>
        <button type="submit" class="btn-primary">Save Job</button>
      </div>
    </form>
  </div>
</div>

<script>
if (new URLSearchParams(window.location.search).get('embedded') === '1') {
  document.body.classList.add('embedded');
}

async function loadJobs() {
  try {
    const res = await fetch('/api/cron');
    const data = await res.json();
    renderJobs(data.jobs || []);
  } catch (err) {
    document.getElementById('jobsList').innerHTML = '<tr><td colspan="6" style="color:var(--down); text-align:center; padding:20px;">Failed to load cron jobs: ' + err.message + '</td></tr>';
  }
}

function renderJobs(jobs) {
  const container = document.getElementById('jobsList');
  if (!jobs.length) {
    container.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--muted); padding:24px;">No cron jobs registered. Click "+ Add New Job" to create one.</td></tr>';
    return;
  }
  container.innerHTML = jobs.map(j => {
    const activeClass = j.enabled ? 'active' : 'disabled';
    const rowClass = j.enabled ? '' : 'disabled';
    const catClass = (j.category || '').toLowerCase().includes('sec') ? 'security' : 'maint';
    return `
      <tr class="${rowClass}">
        <td>
          <span class="badge ${activeClass}">${j.enabled ? 'ACTIVE' : 'DISABLED'}</span>
        </td>
        <td>
          <div class="job-name-cell">${esc(j.name)}</div>
          <div class="job-id-code"><code>${esc(j.id)}</code></div>
        </td>
        <td>
          <span class="badge ${catClass}">${esc(j.category || 'General')}</span>
        </td>
        <td>
          <span class="cron-code">${esc(j.schedule)}</span>
        </td>
        <td>
          ${j.description ? `<div style="font-size: 12px; color: var(--muted); margin-bottom: 2px;">${esc(j.description)}</div>` : ''}
          <div class="cmd-block">${esc(j.command)}</div>
        </td>
        <td>
          <div class="actions-cell">
            <button type="button" class="btn-primary" title="Run job immediately" onclick="runJob('${esc(j.id)}')">▶ Run</button>
            <button type="button" onclick="toggleJob('${esc(j.id)}')">${j.enabled ? '⏸ Pause' : '▶ Enable'}</button>
            <button type="button" class="btn-danger" title="Delete job" onclick="deleteJob('${esc(j.id)}')">🗑</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function showBanner(text, isErr=false) {
  const b = document.getElementById('msgBanner');
  b.className = 'msg-banner ' + (isErr ? 'err' : 'ok');
  b.textContent = text;
  b.style.display = 'block';
  setTimeout(() => { b.style.display = 'none'; }, 4000);
}

async function runJob(id) {
  showBanner('Triggering job ' + id + '...');
  try {
    const res = await fetch('/api/cron/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id})
    });
    const data = await res.json();
    if (data.ok) showBanner('Job ' + id + ' completed successfully!');
    else showBanner('Job ' + id + ' failed with code ' + (data.exit_code ?? 'err'), true);
  } catch (err) {
    showBanner('Error triggering job: ' + err.message, true);
  }
}

async function toggleJob(id) {
  try {
    const res = await fetch('/api/cron/toggle', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id})
    });
    const data = await res.json();
    if (data.ok) {
      showBanner('Job ' + id + ' status updated.');
      loadJobs();
    } else showBanner('Error: ' + data.message, true);
  } catch (err) {
    showBanner('Error toggling job: ' + err.message, true);
  }
}

async function deleteJob(id) {
  if (!confirm('Are you sure you want to delete job "' + id + '"?')) return;
  try {
    const res = await fetch('/api/cron/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id})
    });
    const data = await res.json();
    if (data.ok) {
      showBanner('Job ' + id + ' deleted.');
      loadJobs();
    } else showBanner('Error: ' + data.message, true);
  } catch (err) {
    showBanner('Error deleting job: ' + err.message, true);
  }
}

function openAddModal() { document.getElementById('addModal').classList.add('open'); }
function closeAddModal() { document.getElementById('addModal').classList.remove('open'); }

document.getElementById('addForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const payload = {
    id: document.getElementById('addId').value.trim(),
    name: document.getElementById('addName').value.trim(),
    schedule: document.getElementById('addSchedule').value.trim(),
    category: document.getElementById('addCategory').value.trim() || 'General',
    command: document.getElementById('addCommand').value.trim(),
    description: document.getElementById('addDesc').value.trim()
  };
  try {
    const res = await fetch('/api/cron/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.ok) {
      closeAddModal();
      showBanner('Job ' + payload.id + ' created!');
      document.getElementById('addForm').reset();
      loadJobs();
    } else showBanner('Error: ' + data.message, true);
  } catch (err) {
    showBanner('Error adding job: ' + err.message, true);
  }
});

loadJobs();
</script>
</body>
</html>
""".replace("{THEME}", THEME)
