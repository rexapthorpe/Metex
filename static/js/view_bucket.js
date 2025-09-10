function syncQuantity(targetId) {
  const selectedQty = document.getElementById("quantityInput")?.value || "1";
  const target = document.getElementById(targetId);
  if (target) target.value = selectedQty;
}

/* ===== Bid selection + dial logic (unchanged) ===== */
function setAcceptBarVisibility() {
  const button = document.getElementById('acceptBidsButton');
  if (!button) return;
  const anySelected = !!document.querySelector('.selected-checkbox:checked');
  button.disabled = !anySelected;
}

function updateDialVisual(rowEl, val, max) {
  const valueEl = rowEl.querySelector('.dial-value');
  const minusBtn = rowEl.querySelector('.dial-btn.minus');
  const plusBtn  = rowEl.querySelector('.dial-btn.plus');
  const hiddenInput = rowEl.querySelector('input[type="hidden"][id^="accept_qty_"]');
  if (!valueEl) return;

  const clamped = Math.max(0, Math.min(val, max));
  valueEl.textContent = String(clamped);
  if (hiddenInput) hiddenInput.value = clamped;

  if (minusBtn) minusBtn.disabled = (clamped <= 0);
  if (plusBtn)  plusBtn.disabled  = (clamped >= max);
}

function toggleRowSelection(rowEl) {
  const card = rowEl.querySelector('.bid-card-visual');
  const dialGroup = rowEl.querySelector('.dial-assembly');
  const hiddenCheckbox = rowEl.querySelector('.selected-checkbox');
  const max = parseInt(rowEl.dataset.max, 10) || 0;
  const selecting = !card.classList.contains('selected');

  if (selecting) {
    const currentWidthPx = Math.round(card.getBoundingClientRect().width);
    card.style.width = currentWidthPx + 'px';
    card.classList.add('selected');
    card.setAttribute('aria-pressed', 'true');
    if (dialGroup) dialGroup.style.display = 'flex';
    if (hiddenCheckbox) hiddenCheckbox.checked = true;
    updateDialVisual(rowEl, max, max);
  } else {
    card.classList.remove('selected');
    card.setAttribute('aria-pressed', 'false');
    if (dialGroup) dialGroup.style.display = 'none';
    if (hiddenCheckbox) hiddenCheckbox.checked = false;
    card.style.width = '';
    updateDialVisual(rowEl, 0, max);
  }
  setAcceptBarVisibility();
}

function handleDialAdjust(rowEl, delta) {
  const max = parseInt(rowEl.dataset.max, 10) || 0;
  const hiddenInput = rowEl.querySelector('input[type="hidden"][id^="accept_qty_"]');
  let val = 0;
  if (hiddenInput) val = parseInt(hiddenInput.value || '0', 10);
  val = Math.max(0, Math.min(max, val + delta));
  updateDialVisual(rowEl, val, max);
}

/* ===== Buy-box quantity pill ===== */
function setBuyQty(val, opts = {}) {
  const hidden = document.getElementById('quantityInput');
  const pill   = document.getElementById('buyQtyPill');
  const valueEl = document.getElementById('buyQtyValue');
  if (!pill || !valueEl || !hidden) return;

  const max = parseInt(pill.dataset.max || '0', 10) || 0;
  const clamped = (() => {
    if (max > 0) return Math.max(1, Math.min(val, max));
    return Math.max(1, val);
  })();

  valueEl.textContent = String(clamped);
  hidden.value = String(clamped);

  const minus = document.getElementById('buyQtyMinus');
  const plus  = document.getElementById('buyQtyPlus');
  if (minus) minus.disabled = (clamped <= 1);
  if (plus)  plus.disabled  = (max > 0 ? clamped >= max : false);

  if (opts.bump) {
    pill.style.transform = 'scale(1.03)';
    setTimeout(() => { pill.style.transform = ''; }, 120);
  }
}

/* ===== Grading accordion ===== */
function toggleAccordion(open) {
  const btn = document.getElementById('gradingAccordionButton');
  const panel = document.getElementById('gradingAccordionContent');
  if (!btn || !panel) return;

  if (open === undefined) {
    open = btn.getAttribute('aria-expanded') !== 'true';
  }
  btn.setAttribute('aria-expanded', open ? 'true' : 'false');

  if (open) {
    panel.hidden = false;
    // allow next frame to apply max-height transition
    requestAnimationFrame(() => {
      panel.style.maxHeight = panel.scrollHeight + 'px';
    });
  } else {
    panel.style.maxHeight = panel.scrollHeight + 'px';
    requestAnimationFrame(() => {
      panel.style.maxHeight = '0px';
    });
    panel.addEventListener('transitionend', function onEnd(e) {
      if (e.propertyName === 'max-height') {
        panel.hidden = true;
        panel.removeEventListener('transitionend', onEnd);
      }
    });
  }
}

/* ===== Grading toggle persistence and form injection ===== */
function saveGradingSelection(nameOrNull) {
  if (nameOrNull) {
    localStorage.setItem('gradingFilter', nameOrNull);
  } else {
    localStorage.removeItem('gradingFilter');
  }
}

function appendGradingToForm(form) {
  const filter = localStorage.getItem('gradingFilter');
  if (!filter) return;
  // Signal that graded filtering is required
  const graded = document.createElement('input');
  graded.type = 'hidden'; graded.name = 'graded_only'; graded.value = '1';
  form.appendChild(graded);

  const sel = document.createElement('input');
  sel.type = 'hidden'; sel.name = filter; sel.value = '1';
  form.appendChild(sel);
}

document.addEventListener('DOMContentLoaded', () => {
  /* --- Bid cards --- */
  document.querySelectorAll('.bid-row').forEach(row => {
    const card  = row.querySelector('.bid-card-visual');
    const minus = row.querySelector('.dial-btn.minus');
    const plus  = row.querySelector('.dial-btn.plus');
    const pill  = row.querySelector('.dial-pill');

    if (card) {
      card.addEventListener('click', () => toggleRowSelection(row));
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleRowSelection(row); }
      });
    }
    if (pill) pill.addEventListener('click', (e) => e.stopPropagation());
    [minus, plus].forEach(btn => {
      if (!btn) return;
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        handleDialAdjust(row, btn.classList.contains('plus') ? +1 : -1);
      });
    });
  });
  setAcceptBarVisibility();

  /* --- Buy qty --- */
  const buyMinus = document.getElementById('buyQtyMinus');
  const buyPlus  = document.getElementById('buyQtyPlus');
  const hidden   = document.getElementById('quantityInput');
  if (hidden && (buyMinus || buyPlus)) {
    const startVal = parseInt(hidden.value || '1', 10) || 1;
    setBuyQty(startVal);
    if (buyMinus) buyMinus.addEventListener('click', () => {
      const current = parseInt(hidden.value || '1', 10) || 1;
      setBuyQty(current - 1, { bump: true });
    });
    if (buyPlus) buyPlus.addEventListener('click', () => {
      const current = parseInt(hidden.value || '1', 10) || 1;
      setBuyQty(current + 1, { bump: true });
    });
  }

  /* --- Accordion wiring --- */
  const accBtn = document.getElementById('gradingAccordionButton');
  const accPanel = document.getElementById('gradingAccordionContent');
  if (accBtn && accPanel) {
    accBtn.addEventListener('click', () => toggleAccordion());
  }

  /* --- Grading toggle logic --- */
  const toggles = Array.from(document.querySelectorAll('.grading-toggles .grader-toggle'));

  // Restore saved selection
  const saved = localStorage.getItem('gradingFilter');
  if (saved) {
    const found = toggles.find(t => t.name === saved);
    if (found) {
      found.checked = true;
      // Optionally open accordion if a filter exists
      toggleAccordion(true);
    }
  }

  // Make them mutually exclusive (radio-like)
  toggles.forEach(t => {
    t.addEventListener('change', () => {
      if (t.checked) {
        toggles.forEach(o => { if (o !== t) o.checked = false; });
        saveGradingSelection(t.name);
      } else {
        // If user unchecks the last one, clear selection
        const anyOn = toggles.some(o => o.checked);
        saveGradingSelection(anyOn ? (toggles.find(o => o.checked)?.name) : null);
      }
    });
  });

  // Inject grading params into Buy and Add-to-Cart forms
  const buyForm  = document.querySelector('form[action*="checkout"]');
  const cartForm = document.querySelector('form[action*="auto_fill_bucket_purchase"]');
  if (buyForm)  buyForm.addEventListener('submit', () => appendGradingToForm(buyForm));
  if (cartForm) cartForm.addEventListener('submit', () => appendGradingToForm(cartForm));

  /* --- Flash messages --- */
  const messages = window.flashMessages || [];
  const container = document.getElementById('popup-message-container');
  if (container && messages.length) {
    messages.forEach(([category, message]) => {
      const popup = document.createElement('div');
      popup.className = 'popup-alert ' + category;
      popup.textContent = message;
      container.appendChild(popup);
      setTimeout(() => { popup.remove(); }, 5000);
    });
  }
});
