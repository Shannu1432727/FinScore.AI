/* admin.js */

/* ─── Theme toggle ───────────────────────────────────────────────────────────── */
const themeBtn = document.getElementById('themeToggle');
const html     = document.documentElement;

(function initTheme() {
  const saved = localStorage.getItem('finscore_theme') || 'dark';
  html.setAttribute('data-theme', saved);
  if (themeBtn) themeBtn.innerHTML = saved === 'dark'
    ? '<i class="fa-solid fa-moon"></i>'
    : '<i class="fa-solid fa-sun"></i>';
})();

if (themeBtn) {
  themeBtn.addEventListener('click', () => {
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('finscore_theme', next);
    themeBtn.innerHTML = next === 'dark'
      ? '<i class="fa-solid fa-moon"></i>'
      : '<i class="fa-solid fa-sun"></i>';
  });
}

/* ─── Live search + filter ───────────────────────────────────────────────────── */
const searchInput  = document.getElementById('searchInput');
const filterLoan   = document.getElementById('filterLoan');
const filterStatus = document.getElementById('filterStatus');
const rowCountEl   = document.getElementById('rowCount');
const tableBody    = document.getElementById('tableBody');

function filterRows() {
  if (!tableBody) return;
  const query  = (searchInput?.value || '').toLowerCase().trim();
  const loan   = (filterLoan?.value || '').toLowerCase();
  const status = (filterStatus?.value || '').toLowerCase();
  let visible  = 0;

  tableBody.querySelectorAll('tr').forEach(row => {
    const name    = row.dataset.name    || '';
    const email   = row.dataset.email   || '';
    const phone   = row.dataset.phone   || '';
    const report  = row.dataset.report  || '';
    const rowLoan = row.dataset.loan?.toLowerCase() || '';
    const rowStat = row.dataset.status?.toLowerCase() || '';

    const matchSearch = !query ||
      name.includes(query) || email.includes(query) ||
      phone.includes(query) || report.includes(query);
    const matchLoan   = !loan   || rowLoan === loan;
    const matchStatus = !status || rowStat === status;

    if (matchSearch && matchLoan && matchStatus) {
      row.classList.remove('hidden-row');
      visible++;
    } else {
      row.classList.add('hidden-row');
    }
  });

  if (rowCountEl) rowCountEl.textContent = `${visible} record${visible !== 1 ? 's' : ''}`;
}

if (searchInput)  searchInput.addEventListener('input',  filterRows);
if (filterLoan)   filterLoan.addEventListener('change',  filterRows);
if (filterStatus) filterStatus.addEventListener('change', filterRows);

/* ─── Delete with modal confirm ──────────────────────────────────────────────── */
let pendingDeleteId  = null;
let pendingDeleteRow = null;

const deleteModal   = new bootstrap.Modal(document.getElementById('deleteModal'));
const confirmDelBtn = document.getElementById('confirmDelete');

function deleteRecord(id, btn) {
  pendingDeleteId  = id;
  pendingDeleteRow = btn.closest('tr');
  deleteModal.show();
}

if (confirmDelBtn) {
  confirmDelBtn.addEventListener('click', async () => {
    if (!pendingDeleteId) return;
    confirmDelBtn.disabled = true;
    confirmDelBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>Deleting…';

    try {
      const res = await fetch(`/admin/delete/${pendingDeleteId}`, { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        pendingDeleteRow?.remove();
        filterRows();                   // refresh count
        deleteModal.hide();
      }
    } catch {
      alert('Delete failed. Try again.');
    } finally {
      confirmDelBtn.disabled = false;
      confirmDelBtn.innerHTML = 'Delete';
      pendingDeleteId  = null;
      pendingDeleteRow = null;
    }
  });
}

/* ─── Delete validation log entry ────────────────────────────────────────────── */
function deleteLog(id, btn) {
  if (!confirm('Delete this validation log entry?')) return;
  fetch(`/admin/delete-log/${id}`, { method: 'POST' })
    .then(r => r.json())
    .then(d => { if (d.success) btn.closest('tr').remove(); });
}
