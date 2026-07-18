/* ─── Rupee rain ─────────────────────────────────────────────────────────────── */
(function createRupees() {
  const container = document.getElementById('rupeeRain');
  if (!container) return;
  for (let i = 0; i < 28; i++) {
    const el = document.createElement('span');
    el.className = 'rupee-symbol';
    el.textContent = '₹';
    el.style.cssText = `
      left:${Math.random() * 100}vw;
      font-size:${14 + Math.random() * 20}px;
      animation-duration:${8 + Math.random() * 14}s;
      animation-delay:${Math.random() * 12}s;
    `;
    container.appendChild(el);
  }
})();

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

/* ─── Step wizard ────────────────────────────────────────────────────────────── */
function goStep(n) {
  const s1  = document.getElementById('step1');
  const s2  = document.getElementById('step2');
  const si1 = document.getElementById('si1');
  const si2 = document.getElementById('si2');

  if (n === 2) {
    const validationError = validatePersonalDetails();
    if (validationError) { showError(validationError); return; }
    hideError();
    s1.classList.add('d-none');
    s2.classList.remove('d-none');
    si1.classList.remove('active'); si1.classList.add('done');
    si2.classList.add('active');
  } else {
    s2.classList.add('d-none');
    s1.classList.remove('d-none');
    si2.classList.remove('active');
    si1.classList.remove('done'); si1.classList.add('active');
  }
}

function validatePersonalDetails() {
  const name  = document.querySelector('[name="name"]').value.trim();
  const email = document.querySelector('[name="email"]').value.trim();
  const phone = document.querySelector('[name="phone"]').value.trim();

  if (!name || !email || !phone) return 'Please fill all personal details.';

  const validNameCharacters = /^[\p{L}][\p{L}\s.'-]*$/u.test(name);
  const letterCount = (name.match(/\p{L}/gu) || []).length;
  if (name.length < 2 || name.length > 80 || !validNameCharacters || letterCount < 2) {
    return 'Enter a valid full name (2-80 letters; spaces, apostrophes, hyphens and periods are allowed).';
  }

  const emailPattern = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$/;
  if (email.length > 254 || !emailPattern.test(email)) {
    return 'Enter a valid email address, for example name@example.com.';
  }

  const compactPhone = phone.replace(/[\s()-]/g, '');
  if (!/^(?:\+91)?[6-9]\d{9}$/.test(compactPhone)) {
    return 'Enter a valid 10-digit Indian mobile number, optionally starting with +91.';
  }

  return null;
}

/* ─── File upload drag-drop ──────────────────────────────────────────────────── */
const zone       = document.getElementById('uploadZone');
const fileInput  = document.getElementById('fileInput');
const fileNameEl = document.getElementById('fileName');

if (zone) {
  zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', ()  => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); zone.classList.remove('dragover');
    const f = e.dataTransfer.files[0];
    if (f) assignFile(f);
  });
}

if (fileInput) {
  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) assignFile(fileInput.files[0]);
  });
}

function assignFile(f) {
  const ext = f.name.split('.').pop().toLowerCase();
  if (!['pdf', 'csv'].includes(ext)) { showError('Only PDF and CSV files are allowed.'); return; }
  const dt = new DataTransfer();
  dt.items.add(f);
  fileInput.files = dt.files;
  fileNameEl.textContent = `✓  ${f.name}  (${(f.size / 1024).toFixed(1)} KB)`;
  fileNameEl.classList.remove('d-none');
  hideError();
}

/* ─── Form submit ────────────────────────────────────────────────────────────── */
const form = document.getElementById('applyForm');
if (form) {
  form.addEventListener('submit', async e => {
    e.preventDefault();
    if (!fileInput || !fileInput.files[0]) { showError('Please upload a statement file.'); return; }
    await submitAnalysis();
  });
}

async function submitAnalysis(pdfPassword) {
  showLoading(true);
  animateLoadingSteps();

  const fd = new FormData(form);
  if (pdfPassword) fd.set('pdf_password', pdfPassword);

  try {
    const res = await fetch('/analyze', { method: 'POST', body: fd, redirect: 'manual' });
    if (res.type === 'opaqueredirect' || res.status === 0 || res.redirected || (res.status >= 300 && res.status < 400)) {
      window.location.href = '/login';
      return;
    }

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showLoading(false);
      if (data.password_required) {
        showPdfPasswordModal();
      } else if (data.validation_failed) {
        showValidationError(data);
      } else {
        showError(data.error || 'Analysis failed.');
      }
      return;
    }
    window.location.href = '/dashboard';
  } catch (err) {
    showLoading(false);
    showError('Network error. Please try again.');
  }
}

function showPdfPasswordModal(message = '') {
  const fname = fileInput && fileInput.files[0] ? fileInput.files[0].name : '';
  const el = document.getElementById('pwModalFileName');
  if (el) el.textContent = fname;
  const pwErr = document.getElementById('pwError');
  if (pwErr) {
    pwErr.style.display = message ? 'block' : 'none';
    const messageEl = pwErr.querySelector('span');
    if (messageEl) messageEl.textContent = message;
  }
  const pwInput = document.getElementById('pdfPasswordInput');
  if (pwInput) pwInput.value = '';
  const modal = new bootstrap.Modal(document.getElementById('pdfPasswordModal'));
  modal.show();
  setTimeout(() => { if (pwInput) pwInput.focus(); }, 400);
}

function togglePwVisibility() {
  const input = document.getElementById('pdfPasswordInput');
  const icon  = document.getElementById('pwEyeIcon');
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    icon.className = 'fa-solid fa-eye-slash';
  } else {
    input.type = 'password';
    icon.className = 'fa-solid fa-eye';
  }
}

async function submitWithPassword() {
  const pwInput = document.getElementById('pdfPasswordInput');
  const pw = pwInput ? pwInput.value : '';
  if (!pw) { pwInput && pwInput.focus(); return; }

  const modal = bootstrap.Modal.getInstance(document.getElementById('pdfPasswordModal'));
  if (modal) modal.hide();

  const pwErr = document.getElementById('pwError');

  showLoading(true);
  animateLoadingSteps();

  const fd = new FormData(form);
  fd.set('pdf_password', pw);

  try {
    const res = await fetch('/analyze', { method: 'POST', body: fd, redirect: 'manual' });
    if (res.type === 'opaqueredirect' || res.status === 0 || res.redirected || (res.status >= 300 && res.status < 400)) {
      window.location.href = '/login';
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showLoading(false);
      if (data.password_required) {
        // Wrong password — reopen modal with error
        showPdfPasswordModal(data.error || 'Invalid PDF password. Please try again.');
        setTimeout(() => {
          const err = document.getElementById('pwError');
          if (err) err.style.display = 'block';
        }, 450);
      } else if (data.validation_failed) {
        showValidationError(data);
      } else {
        showError(data.error || 'Analysis failed.');
      }
      return;
    }
    window.location.href = '/dashboard';
  } catch (err) {
    showLoading(false);
    showError('Network error. Please try again.');
  }
}

// Allow Enter key inside password modal
document.addEventListener('DOMContentLoaded', () => {
  const pwInput = document.getElementById('pdfPasswordInput');
  if (pwInput) {
    pwInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') submitWithPassword();
    });
  }
});

function showLoading(on) {
  const lb = document.getElementById('loadingBox');
  const fb = document.getElementById('applyForm');
  if (!lb) return;
  if (on) { lb.classList.remove('d-none'); fb.classList.add('d-none'); }
  else    { lb.classList.add('d-none');    fb.classList.remove('d-none'); }
}

function animateLoadingSteps() {
  ['ls1','ls2','ls3','ls4'].forEach((id, i) => {
    setTimeout(() => {
      const el = document.getElementById(id);
      if (el) el.classList.add('active');
    }, i * 900);
  });
}

function showError(msg) {
  const box = document.getElementById('errorBox');
  if (!box) return;
  box.innerHTML = msg;
  box.classList.remove('d-none');
}

function hideError() {
  const box = document.getElementById('errorBox');
  if (box) box.classList.add('d-none');
}

function showValidationError(data) {
  const box = document.getElementById('errorBox');
  if (!box) return;

  const score    = data.score ?? 0;
  const reasons  = data.reasons || [];
  const bankName = data.bank_name ? `<span class="val-bank">${data.bank_name}</span>` : '';

  const reasonsHtml = reasons.map(r => {
    const ok = r.startsWith('✓');
    return `<div class="val-reason ${ok ? 'val-ok' : 'val-fail'}">${r}</div>`;
  }).join('');

  box.innerHTML = `
    <div class="val-error-wrap">
      <div class="val-header">
        <i class="fa-solid fa-shield-exclamation me-2"></i>
        <strong>Document Validation Failed</strong>
      </div>
      <p class="val-msg">${data.error || 'The uploaded file is not a valid bank statement.'}</p>

      <div class="val-score-row">
        <span>Validation Score</span>
        <div class="val-score-bar"><div class="val-score-fill" style="width:${score}%"></div></div>
        <span class="val-score-num">${score}/100</span>
      </div>

      ${reasonsHtml ? `<div class="val-reasons">${reasonsHtml}</div>` : ''}

      <div class="val-guide">
        <div class="vg-col">
          <div class="vg-title vg-ok"><i class="fa-solid fa-circle-check me-1"></i>Upload These</div>
          <div>✓ SBI / HDFC / ICICI Bank Statement PDF</div>
          <div>✓ CSV Transaction Export from Net Banking</div>
          <div>✓ Bank Passbook PDF with transactions</div>
        </div>
        <div class="vg-col">
          <div class="vg-title vg-fail"><i class="fa-solid fa-circle-xmark me-1"></i>Not Accepted</div>
          <div>✗ Aadhaar Card / PAN Card</div>
          <div>✗ Resume / Certificates</div>
          <div>✗ Salary Slip / Invoice / Generic PDF</div>
        </div>
      </div>
    </div>
  `;
  box.classList.remove('d-none', 'alert-danger');
  box.classList.add('val-error-box');
}

document.querySelectorAll('.finscore-toast').forEach((toastElement) => {
  bootstrap.Toast.getOrCreateInstance(toastElement).show();
});

/* ─── Hero live preview updates ─────────────────────────────────────────────── */
(function initHeroLivePreview() {
  const liveScore = document.getElementById('liveScore');
  const liveLoan  = document.getElementById('liveLoan');
  const liveRate  = document.getElementById('liveRate');
  const liveChart = document.getElementById('liveTrend');
  const inputs    = document.querySelectorAll('[name="name"], [name="email"], [name="phone"]');

  if (!liveScore || !liveLoan || !liveRate || !liveChart || inputs.length === 0) return;

  const bars = Array.from({ length: 5 }, () => {
    const el = document.createElement('span');
    el.style.height = '15%';
    return el;
  });
  const barGrid = document.createElement('div');
  barGrid.className = 'live-chart-bars';
  bars.forEach(b => barGrid.appendChild(b));
  liveChart.appendChild(barGrid);

  const normalize = value => Math.min(100, Math.max(35, value));

  const updateLiveState = () => {
    const nameLen  = document.querySelector('[name="name"]').value.trim().length;
    const emailLen = document.querySelector('[name="email"]').value.trim().length;
    const phoneLen = document.querySelector('[name="phone"]').value.trim().length;
    const fileReady = fileInput && fileInput.files[0];

    const baseScore = 520 + Math.min(150, nameLen * 4 + emailLen * 2 + (phoneLen >= 10 ? 30 : 0));
    const score = normalize(baseScore + (fileReady ? 40 : 0));
    const loan  = Math.round((score / 900) * 500000 / 1000) * 1000;
    const rate  = (12.8 - (score - 500) * 0.008).toFixed(1);

    if (liveScore) liveScore.textContent = `${score}`;
    if (liveLoan)  liveLoan.textContent = `₹${loan.toLocaleString()}`;
    if (liveRate)  liveRate.textContent = `${Math.max(8.5, Math.min(16, rate))}%`;

    bars.forEach((bar, index) => {
      const nextHeight = normalize(30 + Math.sin((Date.now() / 900) + index) * 20 + (index * 8)) + (fileReady ? 8 : 0);
      bar.style.height = `${nextHeight}%`;
      bar.style.background = `linear-gradient(180deg, rgba(59,130,246,${0.65 + index * 0.05}), rgba(99,102,241,0.18))`;
    });
  };

  inputs.forEach(input => input.addEventListener('input', updateLiveState));
  if (fileInput) fileInput.addEventListener('change', updateLiveState);

  setInterval(updateLiveState, 800);
  updateLiveState();
})();
