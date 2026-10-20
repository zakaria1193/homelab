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
    const activeCls = j.enabled ? 'up' : '';
    const rowClass = j.enabled ? '' : 'disabled';
    const catCls = (j.category || '').toLowerCase().includes('sec') ? 'warn' : 'accent';
    return `
      <tr class="${rowClass}">
        <td>
          <span class="badge ${activeCls}">${j.enabled ? 'ACTIVE' : 'DISABLED'}</span>
        </td>
        <td>
          <div class="job-name-cell">${esc(j.name)}</div>
          <div class="job-id-code"><code>${esc(j.id)}</code></div>
        </td>
        <td>
          <span class="badge ${catCls}">${esc(j.category || 'General')}</span>
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
            <button type="button" class="btn small" title="Run job immediately" onclick="runJob('${esc(j.id)}')">▶ Run</button>
            <button type="button" class="btn secondary small" onclick="toggleJob('${esc(j.id)}')">${j.enabled ? '⏸ Pause' : '▶ Enable'}</button>
            <button type="button" class="btn danger small" title="Delete job" onclick="deleteJob('${esc(j.id)}')">🗑</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function showBanner(text, isErr = false) {
  const b = document.getElementById('msgBanner');
  b.className = 'msg-banner ' + (isErr ? 'err' : 'ok');
  b.textContent = text;
  b.style.display = 'block';
  setTimeout(() => { b.style.display = 'none'; }, 4000);
}

async function runJob(id) {
  showBanner('Triggering job ' + id + '...');
  const data = await postJSON('/api/cron/run', { id });
  if (data.ok) showBanner('Job ' + id + ' completed successfully!');
  else showBanner('Job ' + id + ' failed with code ' + (data.exit_code ?? 'err'), true);
}

async function toggleJob(id) {
  const data = await postJSON('/api/cron/toggle', { id });
  if (data.ok) {
    showBanner('Job ' + id + ' status updated.');
    loadJobs();
  } else showBanner('Error: ' + data.message, true);
}

async function deleteJob(id) {
  if (!confirm('Are you sure you want to delete job "' + id + '"?')) return;
  const data = await postJSON('/api/cron/delete', { id });
  if (data.ok) {
    showBanner('Job ' + id + ' deleted.');
    loadJobs();
  } else showBanner('Error: ' + data.message, true);
}

function openAddModal() { document.getElementById('addModal').style.display = 'flex'; }
function closeAddModal() { document.getElementById('addModal').style.display = 'none'; }

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
  const data = await postJSON('/api/cron/add', payload);
  if (data.ok) {
    closeAddModal();
    showBanner('Job ' + payload.id + ' created!');
    document.getElementById('addForm').reset();
    loadJobs();
  } else showBanner('Error: ' + data.message, true);
});

loadJobs();
