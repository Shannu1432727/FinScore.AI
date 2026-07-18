/* dashboard.js — Chart.js visualisations + animated score counter */

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

/* ─── Animated score counter ─────────────────────────────────────────────────── */
const scoreEl = document.getElementById('scoreNum');
const TARGET  = R.score;
let current   = 300;
const step    = Math.max(1, Math.ceil((TARGET - 300) / 60));
const timer   = setInterval(() => {
  current = Math.min(current + step, TARGET);
  if (scoreEl) scoreEl.textContent = current;
  if (current >= TARGET) clearInterval(timer);
}, 25);

/* ─── Chart helpers ──────────────────────────────────────────────────────────── */
const isDark  = () => document.documentElement.getAttribute('data-theme') === 'dark';
const gridCol = () => isDark() ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)';

Chart.defaults.color       = isDark() ? '#94a3b8' : '#334155';
Chart.defaults.borderColor = gridCol();
Chart.defaults.font.family = 'Inter';
Chart.defaults.font.size   = 12;

/* ─── Score Gauge (half-doughnut) ────────────────────────────────────────────── */
function scoreColor(s) {
  if (s >= 750) return '#22c55e';
  if (s >= 700) return '#60a5fa';
  if (s >= 650) return '#fbbf24';
  if (s >= 600) return '#fb923c';
  return '#f87171';
}

const gaugeCtx = document.getElementById('gaugeChart');
if (gaugeCtx) {
  new Chart(gaugeCtx, {
    type: 'doughnut',
    data: {
      datasets: [{
        data: [TARGET - 300, 600 - (TARGET - 300), 600],
        backgroundColor: [scoreColor(TARGET), 'rgba(255,255,255,0.06)', 'transparent'],
        borderWidth: 0,
        circumference: 180,
        rotation: 270,
      }]
    },
    options: {
      responsive: false,
      cutout: '72%',
      plugins: { legend: { display: false }, tooltip: { enabled: false } }
    }
  });
}

/* ─── Expense Pie ────────────────────────────────────────────────────────────── */
const pieCtx = document.getElementById('expensePie');
if (pieCtx) {
  const cd = R.chart_data;
  new Chart(pieCtx, {
    type: 'doughnut',
    data: {
      labels: ['Expenses', 'EMI', 'Cash', 'Savings'],
      datasets: [{
        data: [cd.expense || 0, cd.emi || 0, cd.cash || 0, cd.savings || 0],
        backgroundColor: ['#ef4444', '#f59e0b', '#8b5cf6', '#22c55e'],
        borderColor:     ['#ef444420', '#f59e0b20', '#8b5cf620', '#22c55e20'],
        borderWidth: 2,
        hoverOffset: 8
      }]
    },
    options: {
      plugins: { legend: { position: 'bottom', labels: { padding: 16, boxWidth: 12 } } },
      cutout: '55%'
    }
  });
}

/* ─── Financial Bar ──────────────────────────────────────────────────────────── */
const barCtx = document.getElementById('finBar');
if (barCtx) {
  const f = R.features;
  new Chart(barCtx, {
    type: 'bar',
    data: {
      labels: ['Income', 'Expense', 'Net Savings'],
      datasets: [{
        label: 'Amount (₹)',
        data: [f.monthly_income, f.monthly_expense, f.net_savings],
        backgroundColor: [
          'rgba(34,197,94,0.75)',
          'rgba(239,68,68,0.75)',
          'rgba(59,130,246,0.75)'
        ],
        borderRadius: 8,
        borderSkipped: false,
      }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: gridCol() } },
        y: {
          grid: { color: gridCol() },
          ticks: { callback: v => '₹' + (v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v) }
        }
      }
    }
  });
}

/* ─── Savings Rate Line (simulated 6-month trend) ────────────────────────────── */
const lineCtx = document.getElementById('savingsLine');
if (lineCtx) {
  const base   = R.features.savings_rate * 100;
  const months = ['Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const vals   = months.map(() => Math.max(0, +(base + (Math.random() - 0.5) * 8)).toFixed(1));

  new Chart(lineCtx, {
    type: 'line',
    data: {
      labels: months,
      datasets: [{
        label: 'Savings Rate %',
        data: vals,
        borderColor:     '#3b82f6',
        backgroundColor: 'rgba(59,130,246,0.12)',
        fill: true,
        tension: 0.45,
        pointBackgroundColor: '#3b82f6',
        pointRadius: 4
      }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: gridCol() } },
        y: {
          grid: { color: gridCol() },
          ticks: { callback: v => v + '%' },
          min: 0, max: 100
        }
      }
    }
  });
}

/* ─── Radar — credit factors ─────────────────────────────────────────────────── */
const radarCtx = document.getElementById('radarChart');
if (radarCtx) {
  const f  = R.features;
  const sr = Math.min(f.savings_rate * 100, 100);
  const ns = Math.max(0, Math.min((f.net_savings / Math.max(f.monthly_income, 1)) * 100, 100));
  const sf = Math.min(f.salary_frequency * 35, 100);
  const dc = Math.max(0, 100 - f.debit_credit_ratio * 60);
  const cw = Math.max(0, 100 - f.cash_withdrawal_ratio * 100);
  const cf = R.confidence;

  new Chart(radarCtx, {
    type: 'radar',
    data: {
      labels: ['Savings Rate', 'Net Savings', 'Salary Credits', 'Debit Ratio', 'Cash Discipline', 'Confidence'],
      datasets: [{
        label: 'Your Profile',
        data: [sr, ns, sf, dc, cw, cf],
        borderColor:          '#3b82f6',
        backgroundColor:      'rgba(59,130,246,0.18)',
        pointBackgroundColor: '#3b82f6',
        pointRadius: 4
      }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        r: {
          min: 0, max: 100,
          ticks:      { stepSize: 25, font: { size: 10 } },
          grid:       { color: gridCol() },
          angleLines: { color: gridCol() }
        }
      }
    }
  });
}

/* ─── Floating particles on bg canvas ───────────────────────────────────────── */
(function particles() {
  const container = document.getElementById('bgCanvas');
  if (!container) return;
  const style = document.createElement('style');
  style.textContent = `@keyframes floatDot{0%,100%{transform:translateY(0)}50%{transform:translateY(-20px)}}`;
  document.head.appendChild(style);
  for (let i = 0; i < 18; i++) {
    const dot  = document.createElement('div');
    const size = 2 + Math.random() * 3;
    dot.style.cssText = `
      position:absolute; border-radius:50%;
      width:${size}px; height:${size}px;
      background:rgba(59,130,246,${(0.2 + Math.random() * 0.3).toFixed(2)});
      left:${(Math.random() * 100).toFixed(1)}%;
      top:${(Math.random() * 100).toFixed(1)}%;
      animation:floatDot ${(6 + Math.random() * 8).toFixed(1)}s ease-in-out infinite;
      animation-delay:${(Math.random() * 6).toFixed(1)}s;
    `;
    container.appendChild(dot);
  }
})();
document.querySelectorAll('.finscore-toast').forEach((toastElement) => {
  bootstrap.Toast.getOrCreateInstance(toastElement).show();
});
