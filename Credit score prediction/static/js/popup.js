/* popup.js — Loan popup logic */

/* ═══════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════ */
function showPopup(overlayId, popupId) {
  document.getElementById(overlayId).classList.add('show');
  document.getElementById(popupId).classList.add('show');
  document.body.style.overflow = 'hidden';
}

function hidePopup(overlayId, popupId) {
  document.getElementById(overlayId).classList.remove('show');
  document.getElementById(popupId).classList.remove('show');
  document.body.style.overflow = '';
}

/* ═══════════════════════════════════════════════════
   WELCOME POPUP — shows after 1.8s on first visit
   ═══════════════════════════════════════════════════ */
(function initWelcomePopup() {
  const shown = sessionStorage.getItem('welcome_shown');
  if (shown) return;

  setTimeout(() => {
    showPopup('welcomeOverlay', 'welcomePopup');
    sessionStorage.setItem('welcome_shown', '1');
    startCountdown('wCountdown', 10 * 60); // 10 min countdown
  }, 1800);

  document.getElementById('closeWelcome').addEventListener('click', () =>
    hidePopup('welcomeOverlay', 'welcomePopup'));

  document.getElementById('welcomeOverlay').addEventListener('click', () =>
    hidePopup('welcomeOverlay', 'welcomePopup'));

  document.getElementById('welcomeApply').addEventListener('click', () =>
    hidePopup('welcomeOverlay', 'welcomePopup'));
})();

/* ═══════════════════════════════════════════════════
   COUNTDOWN TIMER
   ═══════════════════════════════════════════════════ */
function startCountdown(elId, totalSeconds) {
  const el = document.getElementById(elId);
  if (!el) return;
  let remaining = totalSeconds;

  const tick = () => {
    const m = String(Math.floor(remaining / 60)).padStart(2, '0');
    const s = String(remaining % 60).padStart(2, '0');
    el.textContent = `${m}:${s}`;
    if (remaining > 0) { remaining--; setTimeout(tick, 1000); }
    else { el.textContent = '00:00'; el.style.color = '#ef4444'; }
  };
  tick();
}

/* ═══════════════════════════════════════════════════
   SCROLL POPUP — fires once after 60% scroll
   ═══════════════════════════════════════════════════ */
(function initScrollPopup() {
  let fired = false;
  const shown = sessionStorage.getItem('scroll_popup_shown');
  if (shown) return;

  window.addEventListener('scroll', () => {
    if (fired) return;
    const scrolled  = window.scrollY + window.innerHeight;
    const docHeight = document.documentElement.scrollHeight;
    if (scrolled / docHeight >= 0.60) {
      fired = true;
      sessionStorage.setItem('scroll_popup_shown', '1');
      setTimeout(() => showPopup('scrollOverlay', 'scrollPopup'), 400);
    }
  });

  document.getElementById('closeScroll').addEventListener('click', () =>
    hidePopup('scrollOverlay', 'scrollPopup'));

  document.getElementById('scrollOverlay').addEventListener('click', () =>
    hidePopup('scrollOverlay', 'scrollPopup'));

  document.getElementById('scrollApply').addEventListener('click', () =>
    hidePopup('scrollOverlay', 'scrollPopup'));
})();

/* ═══════════════════════════════════════════════════
   STICKY BOTTOM BAR — slides up after 3s
   ═══════════════════════════════════════════════════ */
(function initStickyBar() {
  const bar = document.getElementById('stickyBar');
  if (!bar) return;

  const dismissed = sessionStorage.getItem('sticky_bar_dismissed');
  if (!dismissed) {
    setTimeout(() => bar.classList.add('show'), 3000);
  }

  document.getElementById('closeStickyBar').addEventListener('click', () => {
    bar.classList.remove('show');
    sessionStorage.setItem('sticky_bar_dismissed', '1');
  });
})();

/* ═══════════════════════════════════════════════════
   CHAT BUBBLE TOGGLE
   ═══════════════════════════════════════════════════ */
(function initChatBubble() {
  const bubble  = document.getElementById('chatBubble');
  const tooltip = document.getElementById('chatTooltip');
  if (!bubble || !tooltip) return;

  // Auto-show tooltip once after 8s
  setTimeout(() => {
    tooltip.classList.add('show');
    // Auto-hide after 6s if not interacted
    setTimeout(() => tooltip.classList.remove('show'), 6000);
  }, 8000);

  bubble.addEventListener('click', () => {
    tooltip.classList.toggle('show');
    // remove badge on first click
    const badge = bubble.querySelector('.chat-badge');
    if (badge) badge.style.display = 'none';
  });
})();

/* ═══════════════════════════════════════════════════
   Close popups on Escape key
   ═══════════════════════════════════════════════════ */
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  hidePopup('welcomeOverlay', 'welcomePopup');
  hidePopup('scrollOverlay',  'scrollPopup');
});
