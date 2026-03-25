/* static/js/modals/bid_modal_steps.js — 5-step wizard navigation */
'use strict';

(function () {

  /* Payment method display labels (legacy — kept for review fallback) */
  const PM_LABELS = {
    credit_card:   { name: 'Credit / Debit Card', icon: 'fa-regular fa-credit-card' },
    bank_transfer: { name: 'ACH Bank Transfer',   icon: 'fa-solid fa-building-columns' },
  };

  // Label of the currently selected saved card (set by initPaymentOptions)
  let selectedCardLabel = null;
  // 'card' or 'bank_account' — drives fee calculation
  let selectedPmType = 'card';

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
    selectedCardLabel = null;
    selectedPmType = 'card';

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

    /* ── Payment option selection ── */
    initPaymentOptions();

    /* ── Initialize at step 1 ── */
    goToStep(1);
  }

  /* ══════════════════════════════════════════════════════════════
     STEP NAVIGATION
     ══════════════════════════════════════════════════════════════ */
  async function goToStep(n) {
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
    if (n === TOTAL_STEPS) await populateReview();

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
    // If there's a no-card block visible, block progression
    const noCardBlock = document.getElementById('bm-no-card-block');
    if (noCardBlock) {
      const hint = document.getElementById('payment-hint');
      if (hint) {
        hint.style.color = '#dc2626';
        hint.textContent = 'You must add a saved card before placing a bid.';
      }
      return false;
    }

    // Saved-card flow: ensure a card is selected
    const pmIdHidden = document.getElementById('selected-pm-id');
    if (!pmIdHidden || !pmIdHidden.value) {
      const hint = document.getElementById('payment-hint');
      if (hint) {
        hint.style.color = '#dc2626';
        hint.textContent = 'Please select a payment card to continue';
      }
      return false;
    }

    // Set payment_method hidden field based on selected PM type
    const pmValue = selectedPmType === 'bank_account' ? 'bank_transfer' : 'credit_card';
    const pmHidden = document.getElementById('payment_method');
    if (pmHidden) pmHidden.value = pmValue;
    selectedPaymentMethod = pmValue;

    return true;
  }

  /* ══════════════════════════════════════════════════════════════
     REVIEW STEP — populate summary
     ══════════════════════════════════════════════════════════════ */
  async function populateReview() {
    const modeEl  = document.getElementById('bid-pricing-mode');
    const mode    = modeEl ? modeEl.value : 'static';

    let price = 0, qty = 1, priceLabel = 'Fixed Price';

    if (mode === 'static') {
      price = parseFloat(document.getElementById('bid-price-input')?.value) || 0;
      qty   = parseInt(document.getElementById('qty-input')?.value) || 1;
      priceLabel = 'Fixed Price';
    } else {
      const ceilingPrice = parseFloat(document.getElementById('bid-ceiling-price')?.value) || 0;
      const spotPremium  = parseFloat(document.getElementById('bid-spot-premium')?.value) || 0;
      qty = parseInt(document.getElementById('qty-input-premium')?.value) || 1;

      // Determine metal and weight from the form's data attributes
      const form      = document.getElementById('bid-form');
      const metalEl   = document.getElementById('bid-pricing-metal');
      const metal     = (metalEl ? metalEl.value : (form ? form.dataset.bucketMetal : '')) || '';
      const weightStr = (form ? form.dataset.bucketWeight : '1') || '1';
      const weightMatch = weightStr.toString().match(/[\d.]+/);
      const weight    = weightMatch ? parseFloat(weightMatch[0]) : 1.0;

      // Fetch live spot price and calculate effective price = min(spot*weight + premium, ceiling)
      try {
        const response = await fetch('/api/spot-prices');
        const spotData = await response.json();
        if (spotData.success && spotData.prices && metal && spotData.prices[metal.toLowerCase()]) {
          const spotPrice  = spotData.prices[metal.toLowerCase()];
          const calculated = (spotPrice * weight) + spotPremium;
          price      = ceilingPrice > 0 ? Math.min(calculated, ceilingPrice) : calculated;
          priceLabel = 'Effective Bid Price';
        } else {
          price      = ceilingPrice;
          priceLabel = 'Max Price (ceiling)';
        }
      } catch (e) {
        price      = ceilingPrice;
        priceLabel = 'Max Price (ceiling)';
      }
    }

    const itemTotal  = price * qty;

    // 3rd party grading fee: $70/item when grading is requested
    const reqEl  = document.getElementById('requires_grading');
    const hasGrading = reqEl && reqEl.value === 'yes';
    const gradingFee = hasGrading ? 70.00 * qty : 0;

    const subtotal = itemTotal + gradingFee;
    const tax      = subtotal * 0.0825;

    // Processing fee: free for ACH, 2.99% for card/debit
    const isACH = selectedPmType === 'bank_account';
    const fee   = isACH ? 0 : subtotal * 0.0299;

    const total = subtotal + tax + fee;

    setText('rv-price-label', priceLabel);
    setText('rv-price-val',   fmt(price));
    setText('rv-qty',         '×' + qty);
    setText('rv-subtotal',    fmt(subtotal));
    setText('rv-tax',         fmt(tax));

    // Processing fee label + value — green "Free" for ACH
    const feeLabelEl = document.getElementById('rv-fee-label');
    if (feeLabelEl) feeLabelEl.textContent = isACH ? 'Processing fee (ACH)' : 'Processing fee (2.99%)';
    const feeEl = document.getElementById('rv-fee');
    if (feeEl) {
      feeEl.textContent = isACH ? 'Free' : fmt(fee);
      feeEl.classList.toggle('bm-review-fee--free', isACH);
    }

    // Grading fee row (lives in the top/inputs section)
    const gradingRow = document.getElementById('rv-grading-row');
    if (gradingRow) {
      if (hasGrading) {
        setText('rv-grading-label', `3rd Party Grading ×${qty}`);
        setText('rv-grading', fmt(gradingFee));
        gradingRow.style.display = '';
      } else {
        gradingRow.style.display = 'none';
      }
    }

    setText('rv-total', fmt(total));

    /* Payment method — show saved label + correct icon */
    const cardLabel = selectedCardLabel || (PM_LABELS[selectedPaymentMethod] || PM_LABELS['credit_card']).name;
    setText('rv-pm-name', cardLabel);

    const pmIcon = document.getElementById('rv-pm-icon');
    if (pmIcon) {
      pmIcon.className = isACH
        ? 'bm-rv-pm-icon fa-solid fa-building-columns'
        : 'bm-rv-pm-icon fa-regular fa-credit-card';
    }
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
     PAYMENT OPTIONS (saved-card selector)
     ══════════════════════════════════════════════════════════════ */
  function initPaymentOptions() {
    const opts = document.querySelectorAll('.bm-card-opt');

    // Auto-select first method if none selected
    const pmIdHidden = document.getElementById('selected-pm-id');
    if (opts.length > 0 && pmIdHidden && !pmIdHidden.value) {
      const first = opts[0];
      first.classList.add('selected');
      const vis = first.querySelector('.bm-radio-vis');
      if (vis) vis.classList.add('checked');
      pmIdHidden.value = first.dataset.pmId || '';
      selectedCardLabel = first.dataset.cardLabel || '';
      selectedPmType = first.dataset.pmType || 'card';
      selectedPaymentMethod = selectedPmType === 'bank_account' ? 'bank_transfer' : 'credit_card';
    } else if (opts.length > 0 && pmIdHidden && pmIdHidden.value) {
      opts.forEach(opt => {
        if (opt.dataset.pmId === pmIdHidden.value) {
          selectedCardLabel = opt.dataset.cardLabel || '';
          selectedPmType = opt.dataset.pmType || 'card';
          selectedPaymentMethod = selectedPmType === 'bank_account' ? 'bank_transfer' : 'credit_card';
        }
      });
    }

    opts.forEach(opt => {
      opt.addEventListener('click', () => {
        // Update selected state
        opts.forEach(o => {
          o.classList.remove('selected');
          const vis = o.querySelector('.bm-radio-vis');
          if (vis) vis.classList.remove('checked');
        });
        opt.classList.add('selected');
        const vis = opt.querySelector('.bm-radio-vis');
        if (vis) vis.classList.add('checked');

        // Store selected PM ID and type
        const pmId = opt.dataset.pmId || '';
        if (pmIdHidden) pmIdHidden.value = pmId;
        selectedCardLabel = opt.dataset.cardLabel || '';
        selectedPmType = opt.dataset.pmType || 'card';
        selectedPaymentMethod = selectedPmType === 'bank_account' ? 'bank_transfer' : 'credit_card';

        const hint = document.getElementById('payment-hint');
        if (hint) {
          hint.style.color = '#9ca3af';
          hint.textContent = 'Your payment method is only charged when your bid is accepted.';
        }
      });
    });
  }

  /* ══════════════════════════════════════════════════════════════
     HELPERS
     ══════════════════════════════════════════════════════════════ */
  function fmt(n) {
    return formatPrice(Math.round(n * 100) / 100);
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
