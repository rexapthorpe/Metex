/* static/js/modals/bid_modal_steps.js — 5-step wizard navigation */
'use strict';

(function () {

  /* Payment method display labels */
  const PM_LABELS = {
    credit_card:   { name: 'Credit Card',     icon: 'fa-regular fa-credit-card' },
    paypal:        { name: 'PayPal',           icon: 'fa-brands fa-paypal' },
    bank_transfer: { name: 'Bank Transfer',    icon: 'fa-solid fa-building-columns' },
    crypto:        { name: 'Cryptocurrency',   icon: 'fa-brands fa-bitcoin' },
  };

  const TOTAL_STEPS = 5;
  let currentStep = 1;
  let selectedPaymentMethod = null;

  /* ══════════════════════════════════════════════════════════════
     INIT — called by bid_modal.js after form HTML is injected
     ══════════════════════════════════════════════════════════════ */
  function initBidModalSteps() {
    const wizard = document.querySelector('.bm-wizard');
    if (!wizard) return;

    currentStep = 1;
    selectedPaymentMethod = null;

    const btnBack     = document.getElementById('bm-back');
    const btnContinue = document.getElementById('bm-continue');
    const btnSubmit   = document.getElementById('bm-submit');

    if (!btnBack || !btnContinue || !btnSubmit) {
      console.warn('[BidSteps] Navigation buttons not found');
      return;
    }

    /* ── Back ── */
    btnBack.addEventListener('click', () => {
      if (currentStep > 1) goToStep(currentStep - 1);
    });

    /* ── Continue ── */
    btnContinue.addEventListener('click', () => {
      if (validateStep(currentStep)) {
        if (currentStep < TOTAL_STEPS) goToStep(currentStep + 1);
      }
    });

    /* ── Confirm Bid (step 5 submit) — bypass the extra confirm modal ── */
    btnSubmit.addEventListener('click', () => {
      const form = document.getElementById('bid-form');
      if (form) {
        btnSubmit.disabled = true;
        btnSubmit.innerHTML = 'Submitting…';
        window.bidWizardMode = true;  // signal to initBidForm to skip confirm modal
        form.requestSubmit();
      }
    });

    /* ── Pricing mode switcher ── */
    initPricingModeToggle();

    /* ── Grading toggles (mutual exclusivity) ── */
    initGradingToggles();

    /* ── Payment option selection ── */
    initPaymentOptions();

    /* ── Initialize at step 1 ── */
    goToStep(1);
  }

  /* ══════════════════════════════════════════════════════════════
     STEP NAVIGATION
     ══════════════════════════════════════════════════════════════ */
  function goToStep(n) {
    if (n < 1 || n > TOTAL_STEPS) return;

    /* Update step content */
    document.querySelectorAll('.bm-step-content').forEach((el, i) => {
      el.classList.toggle('active', i + 1 === n);
    });

    /* Update stepper circles and connector lines */
    const stepItems = document.querySelectorAll('.bm-step-item');
    const stepLines = document.querySelectorAll('.bm-step-line');

    stepItems.forEach((item, i) => {
      const stepNum = i + 1;
      item.classList.remove('active', 'completed');
      if (stepNum < n)      item.classList.add('completed');
      else if (stepNum === n) item.classList.add('active');
    });

    stepLines.forEach((line, i) => {
      /* Line i connects step i+1 → i+2; completed when both sides done */
      line.classList.toggle('completed', i + 1 < n);
    });

    /* Update footer buttons */
    const btnBack     = document.getElementById('bm-back');
    const btnContinue = document.getElementById('bm-continue');
    const btnSubmit   = document.getElementById('bm-submit');

    if (btnBack)     btnBack.style.display     = n === 1 ? 'none' : 'inline-flex';
    if (btnContinue) btnContinue.style.display = n === TOTAL_STEPS ? 'none' : 'inline-flex';
    if (btnSubmit)   btnSubmit.style.display   = n === TOTAL_STEPS ? 'inline-flex' : 'none';

    /* Populate review on step 5 */
    if (n === TOTAL_STEPS) populateReview();

    currentStep = n;
  }

  /* ══════════════════════════════════════════════════════════════
     PER-STEP VALIDATION
     ══════════════════════════════════════════════════════════════ */
  function validateStep(step) {
    switch (step) {
      case 1: return validatePricing();
      case 2: return true; /* options always valid */
      case 3: return validateDelivery();
      case 4: return validatePayment();
      default: return true;
    }
  }

  function validatePricing() {
    const modeEl = document.getElementById('bid-pricing-mode');
    const mode   = modeEl ? modeEl.value : 'static';

    if (mode === 'static') {
      const qtyEl   = document.getElementById('qty-input');
      const priceEl = document.getElementById('bid-price-input');
      const qty     = parseInt(qtyEl && qtyEl.value) || 0;
      const price   = parseFloat(priceEl && priceEl.value) || 0;

      if (qty < 1) {
        showHint('qty-hint', 'Quantity must be at least 1');
        return false;
      }
      if (price <= 0) {
        showHint('price-hint', 'Price must be greater than $0');
        return false;
      }
    } else {
      const qtyEl     = document.getElementById('qty-input-premium');
      const ceilingEl = document.getElementById('bid-ceiling-price');
      const qty     = parseInt(qtyEl && qtyEl.value) || 0;
      const ceiling = parseFloat(ceilingEl && ceilingEl.value) || 0;

      if (qty < 1)     { alert('Quantity must be at least 1'); return false; }
      if (ceiling <= 0){ alert('Please enter a valid max price'); return false; }
    }

    clearHint('qty-hint');
    clearHint('price-hint');
    return true;
  }

  function validateDelivery() {
    const line1 = (document.getElementById('addr-line1')?.value || '').trim();
    const city  = (document.getElementById('addr-city')?.value  || '').trim();
    const state = (document.getElementById('addr-state')?.value  || '').trim();
    const zip   = (document.getElementById('addr-zip')?.value   || '').trim();

    if (!line1 || !city || !state || !zip) {
      showHint('address-hint', 'Please fill in all required address fields');
      return false;
    }
    clearHint('address-hint');
    return true;
  }

  function validatePayment() {
    if (!selectedPaymentMethod) {
      const hint = document.getElementById('payment-hint');
      if (hint) {
        hint.style.color = '#dc2626';
        hint.textContent = 'Please select a payment method to continue';
      }
      return false;
    }

    /* Write selected payment to hidden input */
    const pmHidden = document.getElementById('payment_method');
    if (pmHidden) pmHidden.value = selectedPaymentMethod;

    return true;
  }

  /* ══════════════════════════════════════════════════════════════
     REVIEW STEP — populate summary
     ══════════════════════════════════════════════════════════════ */
  function populateReview() {
    const modeEl  = document.getElementById('bid-pricing-mode');
    const mode    = modeEl ? modeEl.value : 'static';

    let price = 0, qty = 1, priceLabel = 'Fixed Price';

    if (mode === 'static') {
      price = parseFloat(document.getElementById('bid-price-input')?.value) || 0;
      qty   = parseInt(document.getElementById('qty-input')?.value) || 1;
      priceLabel = 'Fixed Price';
    } else {
      price = parseFloat(document.getElementById('bid-ceiling-price')?.value) || 0;
      qty   = parseInt(document.getElementById('qty-input-premium')?.value) || 1;
      priceLabel = 'Max Price (ceiling)';
    }

    const subtotal = price * qty;
    const tax      = subtotal * 0.0825;
    const fee      = subtotal > 0 ? 0.65 : 0;
    const total    = subtotal + tax + fee;

    setText('rv-price-label', priceLabel);
    setText('rv-price-val',   fmt(price));
    setText('rv-qty',         '×' + qty);
    setText('rv-subtotal',    fmt(subtotal));
    setText('rv-tax',         fmt(tax));
    setText('rv-fee',         fmt(fee));
    setText('rv-total',       fmt(total));

    /* Payment method */
    const pm = PM_LABELS[selectedPaymentMethod] || PM_LABELS['credit_card'];
    setText('rv-pm-name', pm.name);

    const pmIcon = document.getElementById('rv-pm-icon');
    if (pmIcon) pmIcon.className = 'bm-rv-pm-icon ' + pm.icon;
  }

  /* ══════════════════════════════════════════════════════════════
     PRICING MODE TOGGLE
     ══════════════════════════════════════════════════════════════ */
  function initPricingModeToggle() {
    const modeEl   = document.getElementById('bid-pricing-mode');
    const staticEl = document.getElementById('static-pricing-fields');
    const premEl   = document.getElementById('premium-pricing-fields');
    const helperEl = document.getElementById('pricing-mode-helper');

    if (!modeEl) return;

    function applyMode(mode) {
      if (!staticEl || !premEl) return;
      const isStatic = mode === 'static';
      staticEl.style.display = isStatic ? ''      : 'none';
      premEl.style.display   = isStatic ? 'none'  : '';
      if (helperEl) {
        helperEl.textContent = isStatic
          ? 'Set a specific dollar amount for your bid.'
          : 'Bid tracks live spot price plus your premium.';
      }
    }

    modeEl.addEventListener('change', () => applyMode(modeEl.value));
    applyMode(modeEl.value);
  }

  /* ══════════════════════════════════════════════════════════════
     GRADING TOGGLES (mutual-exclusivity handled by initBidForm too,
     but we also wire it here so step 2 feels responsive)
     ══════════════════════════════════════════════════════════════ */
  function initGradingToggles() {
    const anyEl  = document.getElementById('grader_any');
    const pcgsEl = document.getElementById('grader_pcgs');
    const ngcEl  = document.getElementById('grader_ngc');
    const reqEl  = document.getElementById('requires_grading');
    const prefEl = document.getElementById('preferred_grader');

    if (!anyEl || !pcgsEl || !ngcEl) return;

    [anyEl, pcgsEl, ngcEl].forEach(cb => {
      cb.addEventListener('change', function () {
        if (this.checked) {
          [anyEl, pcgsEl, ngcEl].forEach(other => { if (other !== this) other.checked = false; });
          if (reqEl)  reqEl.value  = 'yes';
          if (prefEl) prefEl.value = this === anyEl ? 'Any' : this === pcgsEl ? 'PCGS' : 'NGC';
        } else {
          const anyChecked = [anyEl, pcgsEl, ngcEl].some(c => c.checked);
          if (!anyChecked) {
            if (reqEl)  reqEl.value  = 'no';
            if (prefEl) prefEl.value = '';
          }
        }
      });
    });
  }

  /* ══════════════════════════════════════════════════════════════
     PAYMENT OPTIONS
     ══════════════════════════════════════════════════════════════ */
  function initPaymentOptions() {
    const opts = document.querySelectorAll('.bm-payment-opt');
    opts.forEach(opt => {
      opt.addEventListener('click', () => {
        opts.forEach(o => o.classList.remove('selected'));
        opt.classList.add('selected');

        selectedPaymentMethod = opt.dataset.value || null;

        const radio = opt.querySelector('input[type="radio"]');
        if (radio) radio.checked = true;

        const hint = document.getElementById('payment-hint');
        if (hint) {
          hint.style.color = '#9ca3af';
          hint.textContent = '';
        }

        const pmHidden = document.getElementById('payment_method');
        if (pmHidden && selectedPaymentMethod) pmHidden.value = selectedPaymentMethod;
      });
    });
  }

  /* ══════════════════════════════════════════════════════════════
     HELPERS
     ══════════════════════════════════════════════════════════════ */
  function fmt(n) {
    return '$' + (Math.round(n * 100) / 100).toFixed(2);
  }

  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  function showHint(id, msg) {
    const el = document.getElementById(id);
    if (el) el.textContent = msg;
  }

  function clearHint(id) {
    const el = document.getElementById(id);
    if (el) el.textContent = '';
  }

  /* ══════════════════════════════════════════════════════════════
     SUCCESS ANIMATION — called by submitBidForm() on success
     ══════════════════════════════════════════════════════════════ */
  function showWizardSuccess() {
    const wizard = document.querySelector('.bm-wizard');
    if (!wizard) return;

    // Replace entire wizard contents with success view
    wizard.innerHTML = `
      <div class="bm-success">
        <div class="bm-success-icon">
          <svg class="bm-check-svg" viewBox="0 0 52 52" xmlns="http://www.w3.org/2000/svg">
            <circle class="bm-check-circle" cx="26" cy="26" r="25"/>
            <path class="bm-check-path" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
          </svg>
        </div>
        <div class="bm-success-title">Bid Placed!</div>
        <div class="bm-success-msg">Your bid has been submitted successfully.</div>
      </div>
    `;

    // Auto-close and reload after 2.5s
    setTimeout(() => {
      if (typeof window.closeBidModal === 'function') window.closeBidModal();
      location.reload();
    }, 2500);
  }

  /* ── Exports ── */
  window.initBidModalSteps = initBidModalSteps;
  window.showWizardSuccess  = showWizardSuccess;

})();
