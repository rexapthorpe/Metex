// static/js/modals/bid_modal.js
'use strict';

/* ==========================================================================
   Unified Bid Modal — handles both CREATE and EDIT operations
   ========================================================================== */

/**
 * Open bid modal for creating or editing a bid
 * @param {number} bucketId - Category ID
 * @param {number|null} bidId - Bid ID for edit mode, null for create mode
 */
function openBidModal(bucketId, bidId = null) {
  // Fast auth check: show login prompt immediately without a network round-trip
  if (window.isUserLoggedIn === false) {
    const modal = document.getElementById('bidModal');
    const content = document.getElementById('bidModalContent');
    if (modal && content) {
      content.innerHTML = `
        <button type="button" class="modal-close" onclick="closeBidModal()" aria-label="Close modal">×</button>
        <div class="bm-auth-prompt">
          <div class="bm-auth-icon"><i class="fa-solid fa-lock"></i></div>
          <div class="bm-auth-logo">MetEx</div>
          <h2 class="bm-auth-title">Sign in to place a bid</h2>
          <p class="bm-auth-sub">Join thousands of buyers and sellers trading precious metals with confidence.</p>
          <div class="bm-auth-actions">
            <button type="button" onclick="window.location.href='/login'" class="bm-auth-btn-primary">
              <i class="fa-solid fa-arrow-right-to-bracket"></i> Log In
            </button>
            <button type="button" onclick="window.location.href='/login?mode=signup'" class="bm-auth-btn-secondary">
              Create an account
            </button>
          </div>
          <p class="bm-auth-dismiss" onclick="closeBidModal()">Continue browsing</p>
        </div>
      `;
      modal.style.display = 'flex';
      modal.classList.add('active');
    }
    return;
  }

  const modal = document.getElementById('bidModal');
  const content = document.getElementById('bidModalContent');

  if (!modal || !content) {
    console.error('Modal container missing (#bidModal or #bidModalContent).');
    return;
  }

  // Clear previous content and show loading state
  content.innerHTML = `
    <button type="button" class="modal-close" onclick="closeBidModal()" aria-label="Close modal">×</button>
    <div class="modal-loading">Loading bid form...</div>
  `;

  // Show modal immediately with loading state
  modal.style.display = 'flex';
  modal.classList.add('active');

  // Build URL based on mode
  const url = bidId
    ? `/bids/form/${bucketId}/${bidId}`  // EDIT mode
    : `/bids/form/${bucketId}`;          // CREATE mode

  // Fetch form via AJAX
  fetch(url, {
    cache: 'no-store',
    redirect: 'follow',
    credentials: 'same-origin',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then(async resp => {
      const text = await resp.text();

      // Handle 401 Unauthorized with specific message
      if (resp.status === 401) {
        throw new Error('AUTHENTICATION_REQUIRED');
      }

      if (!resp.ok) throw new Error(`HTTP ${resp.status} — ${text.slice(0, 500)}`);
      return text;
    })
    .then(html => {
      // Inject close button + fetched form HTML
      content.innerHTML = `
        <button type="button" class="modal-close" onclick="closeBidModal()" aria-label="Close modal">×</button>
        ${html}
      `;

      const form = content.querySelector('#bid-form');
      if (!form) {
        console.error('Injected HTML does not contain #bid-form. First 400 chars:', html.slice(0, 400));
        const warn = document.createElement('div');
        warn.className = 'error-msg';
        warn.style.marginTop = '12px';
        warn.textContent = 'Template loaded but missing #bid-form. Verify templates/tabs/bid_form.html.';
        content.prepend(warn);
        return;
      }

      try {
        initBidForm();
      } catch (e) {
        console.error('❌ Form initialization error:', e);
        const warn = document.createElement('div');
        warn.className = 'error-msg';
        warn.style.marginTop = '12px';
        warn.textContent = 'Form loaded but initialization failed. See console for details.';
        content.prepend(warn);
      }

      // Initialize step wizard on top of field-level logic
      try {
        if (typeof window.initBidModalSteps === 'function') {
          window.initBidModalSteps();
        }
      } catch (e) {
        console.error('❌ Step wizard initialization error:', e);
      }
    })
    .catch(err => {
      console.error('❌ Bid form fetch error:', err);

      // Show specific message for authentication errors
      if (err.message === 'AUTHENTICATION_REQUIRED') {
        content.innerHTML = `
          <button type="button" class="modal-close" onclick="closeBidModal()" aria-label="Close modal">×</button>
          <div class="bm-auth-prompt">
            <div class="bm-auth-icon">
              <i class="fa-solid fa-lock"></i>
            </div>
            <div class="bm-auth-logo">MetEx</div>
            <h2 class="bm-auth-title">Sign in to place a bid</h2>
            <p class="bm-auth-sub">Join thousands of buyers and sellers trading precious metals with confidence.</p>
            <div class="bm-auth-actions">
              <button type="button" onclick="window.location.href='/login'" class="bm-auth-btn-primary">
                <i class="fa-solid fa-arrow-right-to-bracket"></i> Log In
              </button>
              <button type="button" onclick="window.location.href='/login?mode=signup'" class="bm-auth-btn-secondary">
                Create an account
              </button>
            </div>
            <p class="bm-auth-dismiss" onclick="closeBidModal()">Continue browsing</p>
          </div>
        `;
      } else {
        content.innerHTML = `
          <button type="button" class="modal-close" onclick="closeBidModal()" aria-label="Close modal">×</button>
          <div class="bid-modal-form">
            <h2>Error Loading Form</h2>
            <p class="error-msg">Unable to load bid form. Please try again.</p>
            <button type="button" onclick="closeBidModal()" class="eb-confirm" style="margin-top: 16px;">Close</button>
          </div>
        `;
      }
    });
}

function closeBidModal() {
  const modal = document.getElementById('bidModal');
  const content = document.getElementById('bidModalContent');

  if (modal) {
    window.animatedModalClose(modal, function() {
      modal.style.display = 'none';
      modal.classList.remove('active');
      if (content) content.innerHTML = '';
    });
  }
}

// Global exposure
window.openBidModal = openBidModal;
window.closeBidModal = closeBidModal;

// Close on overlay click
window.addEventListener('click', (e) => {
  const modal = document.getElementById('bidModal');
  if (e.target === modal) closeBidModal();
});

// Close on Escape
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeBidModal();
});

/* ==========================================================================
   Form Initialization (same logic as edit_bid_modal.js but generalized)
   ========================================================================== */
function initBidForm() {
  const grid = document.getElementById('eb-grid');
  const form = document.getElementById('bid-form');
  if (!form) {
    console.warn('Bid form not found (#bid-form). Aborting init.');
    return;
  }

  /* ----- Get all elements first ----- */
  // Pricing Mode
  const pricingModeSelect = document.getElementById('bid-pricing-mode');
  const staticPricingFields = document.getElementById('static-pricing-fields');
  const premiumPricingFields = document.getElementById('premium-pricing-fields');
  const premiumDisplay = document.getElementById('premium-display');
  const effectiveBidPrice = document.getElementById('effective-bid-price');
  const currentSpotPriceElem = document.getElementById('current-spot-price');

  // Phase 0A: grading deactivated — always treat as not required
  const requiresGrading = document.getElementById('requires_grading');  // hidden (kept for form compat)
  const requireTPGToggle = null;  // grading toggle removed from UI

  // Quantity
  const qtyInput = document.getElementById('qty-input');
  const qtyDec   = document.getElementById('qty-dec');
  const qtyInc   = document.getElementById('qty-inc');
  const qtyValue = document.getElementById('qty-value');
  const qtyHint  = document.getElementById('qty-hint');

  // Price
  const priceInput = document.getElementById('bid-price-input');
  const priceHint  = document.getElementById('price-hint');

  // Address
  const addrSelector = document.getElementById('addr-selector');
  const customAddressFields = document.getElementById('custom-address-fields');
  const addr = {
    single:  document.getElementById('address-input'),
    first:   document.getElementById('addr-first'),
    last:    document.getElementById('addr-last'),
    line1:   document.getElementById('addr-line1'),
    line2:   document.getElementById('addr-line2'),
    city:    document.getElementById('addr-city'),
    state:   document.getElementById('addr-state'),
    zip:     document.getElementById('addr-zip')
  };
  const addressHint = document.getElementById('address-hint') || document.querySelector('.addr-hint');
  const addrRequiredFields = [addr.line1, addr.city, addr.state, addr.zip];

  // Confirm button
  const confirmBtn = document.getElementById('eb-confirm');

  /* ----- Helper functions ----- */
  function combinedAddressFromFields() {
    if (addr.single) return addr.single.value.trim();

    const parts = [];
    // ✅ FIX: Do NOT include name in delivery_address
    // Name is stored separately in users table (first_name, last_name)
    // Including it causes parsing issues on Sold tab and other places
    // Old code that included name:
    // const first = addr.first && addr.first.value && addr.first.value.trim();
    // const last  = addr.last  && addr.last.value  && addr.last.value.trim();
    // const nameLine = [first, last].filter(Boolean).join(' ');
    // if (nameLine) parts.push(nameLine);

    const line1 = addr.line1 && addr.line1.value && addr.line1.value.trim();
    const line2 = addr.line2 && addr.line2.value && addr.line2.value.trim();
    if (line1) parts.push(line1);
    if (line2) parts.push(line2);

    const city  = addr.city && addr.city.value && addr.city.value.trim();
    const state = addr.state && addr.state.value && addr.state.value.trim();
    const zip   = addr.zip && addr.zip.value && addr.zip.value.trim();

    // ✅ State and ZIP must be joined with SPACE (not comma) for correct parsing
    // Format: "City, State ZIP" (comma after city, space between state and zip)
    const stateZipPart = [state, zip].filter(Boolean).join(' ');
    const cityLine = [city, stateZipPart].filter(Boolean).join(', ');
    if (cityLine) parts.push(cityLine);

    // ✅ Final format: "Street • [Street2 •] City, State ZIP" (no name)
    return parts.join(' • ');
  }

  function ensureCombinedHidden() {
    let hidden = document.getElementById('delivery-address-combined');
    if (!hidden) {
      hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'delivery_address';
      hidden.id   = 'delivery-address-combined';
      form.appendChild(hidden);
    }
    hidden.value = combinedAddressFromFields();
    return hidden;
  }

  /* ----- Master validation (defined early so it can be called by other functions) ----- */
  function validateAll() {
    // Determine which pricing mode is active
    const pricingMode = pricingModeSelect ? pricingModeSelect.value : 'static';

    let priceOk = false;
    let qtyOk = false;

    if (pricingMode === 'premium_to_spot') {
      // Validate premium mode fields
      const premiumQtyInput = document.getElementById('qty-input-premium');
      const premiumInput = document.getElementById('bid-spot-premium');
      const ceilingPriceInput = document.getElementById('bid-ceiling-price');

      // Quantity validation (premium mode)
      const q = Number(premiumQtyInput && premiumQtyInput.value);
      qtyOk = Number.isInteger(q) && q >= 1;

      // Premium validation (can be 0 or positive)
      const premium = Number(premiumInput && premiumInput.value);
      const premiumOk = isFinite(premium) && premium >= 0;

      // Floor price validation (must be positive)
      const floor = Number(ceilingPriceInput && ceilingPriceInput.value);
      const floorOk = isFinite(floor) && floor >= 0.01;

      priceOk = premiumOk && floorOk;
    } else {
      // Validate static mode fields
      const p = Number(priceInput && priceInput.value);
      priceOk = isFinite(p) && p >= 0.01;
      if (priceHint) priceHint.textContent = priceOk ? '' : 'Price must be at least $0.01';

      const q = Number(qtyInput && qtyInput.value);
      qtyOk = Number.isInteger(q) && q >= 1;
      if (qtyHint) qtyHint.textContent = qtyOk ? '' : 'Quantity must be at least 1';
    }

    let addrOk = true;
    if (addr.single) {
      addrOk = addr.single.value.trim().length > 0;
      if (addressHint) addressHint.textContent = addrOk ? '' : 'Delivery address is required.';
    } else {
      addrOk = addrRequiredFields.every(el => el && el.value && el.value.trim().length > 0);
      if (addressHint) addressHint.textContent = addrOk ? '' : 'Please complete address, city, state, and zip.';
    }

    ensureCombinedHidden();
    if (confirmBtn) confirmBtn.disabled = !(priceOk && qtyOk && addrOk);
  }

  /* ----- Grading toggle logic (Phase 0A: deactivated) ----- */
  function syncTPGToggle() {
    // Always set requires_grading to 'no' — grading deactivated
    if (requiresGrading) requiresGrading.value = 'no';
    validateAll();
  }
  syncTPGToggle();

  /* ----- Pricing Mode Toggle ----- */
  function updatePricingFieldsVisibility() {
    if (!pricingModeSelect || !staticPricingFields || !premiumPricingFields) return;

    const mode = pricingModeSelect.value;
    console.log('[Bid Pricing Mode] Selected mode:', mode);

    if (mode === 'premium_to_spot') {
      // Show premium fields, hide static fields
      staticPricingFields.style.display = 'none';
      premiumPricingFields.style.display = 'block';

      // Sync quantity from static to premium
      const staticQty = document.getElementById('qty-input');
      const premiumQty = document.getElementById('qty-input-premium');
      if (staticQty && premiumQty) {
        premiumQty.value = staticQty.value;
        const premiumQtyValue = document.getElementById('qty-value-premium');
        if (premiumQtyValue) premiumQtyValue.textContent = staticQty.value;
      }

      // Clear static price field (won't be submitted)
      if (priceInput) priceInput.value = '';
    } else {
      // Show static fields, hide premium fields
      staticPricingFields.style.display = 'block';
      premiumPricingFields.style.display = 'none';

      // Sync quantity from premium to static
      const staticQty = document.getElementById('qty-input');
      const premiumQty = document.getElementById('qty-input-premium');
      if (staticQty && premiumQty) {
        staticQty.value = premiumQty.value;
        const staticQtyValue = document.getElementById('qty-value');
        if (staticQtyValue) staticQtyValue.textContent = premiumQty.value;
      }

      // Clear premium fields (won't be submitted)
      const premInput = document.getElementById('bid-spot-premium');
      const floorInput = document.getElementById('bid-ceiling-price');
      if (premInput) premInput.value = '';
      if (floorInput) floorInput.value = '';
    }

    validateAll();
  }

  // Parse a weight string (e.g. "1/10 oz", "5 g", "1 kilo") to troy ounces.
  // Returns 1.0 as a safe fallback if absent or unparseable.
  function parseWeightOz(str) {
    if (!str) return 1;
    str = str.trim();
    const kiloM = str.match(/^(\d+(?:\.\d+)?)\s*kilo/i);
    if (kiloM) return parseFloat(kiloM[1]) * (1000 / 31.1035);
    const gramM = str.match(/^(\d+(?:\.\d+)?)\s*g\b/i);
    if (gramM) return parseFloat(gramM[1]) / 31.1035;
    const fracM = str.match(/^(\d+)\s*\/\s*(\d+)\s*oz/i);
    if (fracM) return parseInt(fracM[1]) / parseInt(fracM[2]);
    const ozM = str.match(/^(\d+(?:\.\d+)?)\s*oz/i);
    if (ozM) return parseFloat(ozM[1]);
    return 1;
  }

  // Function to update effective bid price display
  function updateEffectiveBidPrice() {
    const premInput = document.getElementById('bid-spot-premium');
    const calcLine = document.getElementById('bid-spot-calc-line');
    if (!premInput || !currentSpotPriceElem || !calcLine) return;

    const premium = Number(premInput.value) || 0;
    const spotPriceText = currentSpotPriceElem.textContent.replace(/[^0-9.]/g, '');
    const spotPrice = Number(spotPriceText) || 0;

    const bidForm = document.getElementById('bid-form');
    const weightStr = (bidForm && bidForm.dataset.bucketWeight) || '';
    const weightOz = parseWeightOz(weightStr);
    const weightLabel = weightStr || '1 oz';

    const rawEffective = spotPrice * weightOz + premium;

    const ceilingInput = document.getElementById('bid-ceiling-price');
    const ceiling = ceilingInput ? Number(ceilingInput.value) : 0;
    const ceilingActive = ceiling > 0 && rawEffective > ceiling;
    const effective = ceilingActive ? ceiling : rawEffective;

    if (ceilingActive) {
      calcLine.innerHTML =
        'Your bid: <span style="color:#d97706;font-weight:600;" title="(Spot × ' + weightLabel + ') + premium ($' + formatWithCommas(rawEffective, 2) + ') exceeds your max — ceiling price applies">' +
        '<i class="fa-solid fa-circle-exclamation" style="font-size:11px;margin-right:3px;"></i>Capped at max price</span>' +
        ' = $<span id="effective-bid-price">' + formatWithCommas(effective, 2) + '</span>';
    } else {
      calcLine.innerHTML =
        'Your bid: (Spot × ' + weightLabel + ') + $<span id="premium-display">' + formatWithCommas(premium, 2) + '</span>' +
        ' = $<span id="effective-bid-price">' + formatWithCommas(effective, 2) + '</span>';
    }
  }

  if (pricingModeSelect) {
    pricingModeSelect.addEventListener('change', updatePricingFieldsVisibility);
    // Initialize visibility on load
    updatePricingFieldsVisibility();
  }

  /* ----- Quantity dial (static mode) ----- */
  function clampQty(n) { return Math.max(1, Math.round(n || 1)); }
  function setQty(n) {
    const v = clampQty(n);
    if (qtyInput) qtyInput.value = String(v);
    if (qtyValue) qtyValue.textContent = String(v);
    validateAll();
  }
  setQty(Number((qtyInput && qtyInput.value) || (qtyValue && qtyValue.textContent) || 1));

  let holdTimer = null, stepTimer = null;
  function startHold(delta) {
    setQty((Number(qtyInput && qtyInput.value) || 1) + delta);
    holdTimer = setTimeout(() => {
      stepTimer = setInterval(() => setQty((Number(qtyInput && qtyInput.value) || 1) + delta), 80);
    }, 350);
  }
  function stopHold() { clearTimeout(holdTimer); clearInterval(stepTimer); }

  // mouse hold (handles both single click and hold-to-repeat)
  qtyDec && qtyDec.addEventListener('mousedown', () => startHold(-1));
  qtyInc && qtyInc.addEventListener('mousedown', () => startHold(+1));
  ['mouseup','mouseleave'].forEach(ev => {
    qtyDec && qtyDec.addEventListener(ev, stopHold);
    qtyInc && qtyInc.addEventListener(ev, stopHold);
  });

  // touch hold
  qtyDec && qtyDec.addEventListener('touchstart', (e) => { e.preventDefault(); startHold(-1); }, { passive: false });
  qtyInc && qtyInc.addEventListener('touchstart', (e) => { e.preventDefault(); startHold(+1); }, { passive: false });
  ['touchend','touchcancel'].forEach(ev => {
    qtyDec && qtyDec.addEventListener(ev, stopHold);
    qtyInc && qtyInc.addEventListener(ev, stopHold);
  });

  qtyInput && qtyInput.addEventListener('change', () => setQty(Number(qtyInput.value)));

  /* ----- Price field ----- */
  // Enforce numeric input only and a single decimal point
  if (priceInput) {
    priceInput.addEventListener('beforeinput', (e) => {
      if (e.inputType === 'insertText' && /[^\d.]/.test(e.data)) e.preventDefault();
    });
    priceInput.addEventListener('input', () => {
      let v = priceInput.value.replace(/[^\d.]/g, '');
      const parts = v.split('.');
      if (parts.length > 2) v = parts[0] + '.' + parts.slice(1).join('');
      priceInput.value = v;
    });
  }

  priceInput && priceInput.addEventListener('blur', () => {
    const n = Number(priceInput.value);
    if (!isFinite(n) || n <= 0) {
      if (priceHint) priceHint.textContent = 'Enter a positive price.';
    } else {
      priceInput.value = (Math.round(n * 100) / 100).toFixed(2);
      if (priceHint) priceHint.textContent = '';
    }
    validateAll();
  });

  /* ----- Quantity dial (premium mode) ----- */
  const qtyDecPremium = document.getElementById('qty-dec-premium');
  const qtyIncPremium = document.getElementById('qty-inc-premium');
  const qtyInputPremium = document.getElementById('qty-input-premium');
  const qtyValuePremium = document.getElementById('qty-value-premium');

  function setQtyPremium(n) {
    const v = clampQty(n);
    if (qtyInputPremium) qtyInputPremium.value = String(v);
    if (qtyValuePremium) qtyValuePremium.textContent = String(v);
    validateAll();
  }

  if (qtyInputPremium && qtyValuePremium) {
    setQtyPremium(Number(qtyInputPremium.value || qtyValuePremium.textContent || 1));
  }

  let holdTimerPremium = null, stepTimerPremium = null;
  function startHoldPremium(delta) {
    setQtyPremium((Number(qtyInputPremium && qtyInputPremium.value) || 1) + delta);
    holdTimerPremium = setTimeout(() => {
      stepTimerPremium = setInterval(() => setQtyPremium((Number(qtyInputPremium && qtyInputPremium.value) || 1) + delta), 80);
    }, 350);
  }
  function stopHoldPremium() { clearTimeout(holdTimerPremium); clearInterval(stepTimerPremium); }

  // mouse hold (handles both single click and hold-to-repeat)
  qtyDecPremium && qtyDecPremium.addEventListener('mousedown', () => startHoldPremium(-1));
  qtyIncPremium && qtyIncPremium.addEventListener('mousedown', () => startHoldPremium(+1));
  ['mouseup','mouseleave'].forEach(ev => {
    qtyDecPremium && qtyDecPremium.addEventListener(ev, stopHoldPremium);
    qtyIncPremium && qtyIncPremium.addEventListener(ev, stopHoldPremium);
  });

  // touch hold
  qtyDecPremium && qtyDecPremium.addEventListener('touchstart', (e) => { e.preventDefault(); startHoldPremium(-1); }, { passive: false });
  qtyIncPremium && qtyIncPremium.addEventListener('touchstart', (e) => { e.preventDefault(); startHoldPremium(+1); }, { passive: false });
  ['touchend','touchcancel'].forEach(ev => {
    qtyDecPremium && qtyDecPremium.addEventListener(ev, stopHoldPremium);
    qtyIncPremium && qtyIncPremium.addEventListener(ev, stopHoldPremium);
  });

  qtyInputPremium && qtyInputPremium.addEventListener('change', () => setQtyPremium(Number(qtyInputPremium.value)));

  /* ----- Premium Above Spot field ----- */
  const premiumInput = document.getElementById('bid-spot-premium');

  if (premiumInput) {
    // Enforce numeric input only and a single decimal point
    premiumInput.addEventListener('beforeinput', (e) => {
      if (e.inputType === 'insertText' && /[^\d.]/.test(e.data)) e.preventDefault();
    });
    premiumInput.addEventListener('input', () => {
      let v = premiumInput.value.replace(/[^\d.]/g, '');
      const parts = v.split('.');
      if (parts.length > 2) v = parts[0] + '.' + parts.slice(1).join('');
      premiumInput.value = v;
      updateEffectiveBidPrice();
    });
    premiumInput.addEventListener('blur', () => {
      const n = Number(premiumInput.value);
      if (!isFinite(n) || n < 0) {
        premiumInput.value = '0.00';
      } else {
        premiumInput.value = (Math.round(n * 100) / 100).toFixed(2);
      }
      updateEffectiveBidPrice();
      validateAll();
    });
  }

  /* ----- Floor Price (Minimum) field ----- */
  const ceilingPriceInput = document.getElementById('bid-ceiling-price');

  if (ceilingPriceInput) {
    // Enforce numeric input only and a single decimal point
    ceilingPriceInput.addEventListener('beforeinput', (e) => {
      if (e.inputType === 'insertText' && /[^\d.]/.test(e.data)) e.preventDefault();
    });
    ceilingPriceInput.addEventListener('input', () => {
      let v = ceilingPriceInput.value.replace(/[^\d.]/g, '');
      const parts = v.split('.');
      if (parts.length > 2) v = parts[0] + '.' + parts.slice(1).join('');
      ceilingPriceInput.value = v;
      updateEffectiveBidPrice();
    });
    ceilingPriceInput.addEventListener('blur', () => {
      const n = Number(ceilingPriceInput.value);
      if (!isFinite(n) || n <= 0) {
        // Don't auto-fill - let user enter value
      } else {
        ceilingPriceInput.value = (Math.round(n * 100) / 100).toFixed(2);
      }
      updateEffectiveBidPrice();
      validateAll();
    });
  }

  /* ----- Address selector dropdown ----- */
  if (addrSelector && customAddressFields) {
    // Handle address selection
    addrSelector.addEventListener('change', () => {
      const selectedOption = addrSelector.options[addrSelector.selectedIndex];

      if (selectedOption.value === 'custom') {
        // Show custom address fields
        customAddressFields.style.display = 'block';
      } else {
        // Hide custom fields and populate from saved address
        customAddressFields.style.display = 'none';

        // Populate fields from data attributes
        if (addr.first) addr.first.value = selectedOption.dataset.first || '';
        if (addr.last) addr.last.value = selectedOption.dataset.last || '';
        if (addr.line1) addr.line1.value = selectedOption.dataset.line1 || '';
        if (addr.line2) addr.line2.value = selectedOption.dataset.line2 || '';
        if (addr.city) addr.city.value = selectedOption.dataset.city || '';
        if (addr.state) addr.state.value = selectedOption.dataset.state || '';
        if (addr.zip) addr.zip.value = selectedOption.dataset.zip || '';
      }

      validateAll();
    });

    // Initialize: show/hide fields based on initial selection
    if (addrSelector.value === 'custom') {
      // Custom is selected (default when no saved addresses) - show fields
      customAddressFields.style.display = 'block';
    } else {
      // Saved address is selected - hide custom fields
      customAddressFields.style.display = 'none';
    }
  }

  /* ----- Address input listeners ----- */
  addrRequiredFields.forEach(el => el && el.addEventListener('input', validateAll));
  addr.single && addr.single.addEventListener('input', validateAll);

  /* ----- Initial validation ----- */
  validateAll();
  updateEffectiveBidPrice();

  /* ----- Submit (AJAX) - intercepted for confirmation modal ----- */
  form.addEventListener('submit', (e) => {
    e.preventDefault();

    try { syncTPGToggle && syncTPGToggle(); } catch {}

    validateAll();
    const btn = document.getElementById('eb-confirm');
    if (btn && btn.disabled) return;

    // Clear previous errors
    form.querySelectorAll('.error-msg').forEach(el => el.remove());

    ensureCombinedHidden();

    // Extract form data for confirmation modal
    const formData = new FormData(form);
    const pricingMode = formData.get('bid_pricing_mode') || 'static';
    const requiresGrading = formData.get('requires_grading') === 'yes';

    // Extract pricing fields based on mode
    let bidPrice, bidQuantity, spotPremium, ceilingPrice, pricingMetal;

    if (pricingMode === 'premium_to_spot') {
      bidQuantity = parseInt(formData.get('bid_quantity_premium')) || 0;
      spotPremium = parseFloat(formData.get('bid_spot_premium')) || 0;
      ceilingPrice = parseFloat(formData.get('bid_ceiling_price')) || 0;
      pricingMetal = formData.get('bid_pricing_metal') || '';
      // For display, use floor price as the base price
      bidPrice = ceilingPrice;
    } else {
      bidQuantity = parseInt(formData.get('bid_quantity')) || 0;
      bidPrice = parseFloat(formData.get('bid_price')) || 0;
    }

    // Get bucket description from form title or hidden data
    const formTitle = document.querySelector('.bid-modal-form h2');
    const isEdit = formTitle && formTitle.textContent.includes('Edit');

    // Extract metal and weight from bucketSpecs (if available)
    const metal = (window.bucketSpecs && window.bucketSpecs['Metal']) || pricingMetal || '';
    const weightStr = (window.bucketSpecs && window.bucketSpecs['Weight']) || '1 oz';

    // Extract delivery address from form (fields don't have name attributes, use IDs)
    const addressLine1 = document.getElementById('addr-line1')?.value || '';
    const addressLine2 = document.getElementById('addr-line2')?.value || '';
    const city = document.getElementById('addr-city')?.value || '';
    const state = document.getElementById('addr-state')?.value || '';
    const zipCode = document.getElementById('addr-zip')?.value || '';

    // Format address in bullet-separated format for modal display
    let deliveryAddress = '';
    if (addressLine1 || city || state || zipCode) {
      const parts = [];
      if (addressLine1) parts.push(addressLine1);
      if (addressLine2) parts.push(addressLine2);

      // Build city/state/zip string
      const cityStateZip = [city, state && zipCode ? `${state} ${zipCode}` : state || zipCode]
        .filter(Boolean)
        .join(', ');

      if (cityStateZip) parts.push(cityStateZip);

      deliveryAddress = parts.join(' • ');
    }

    console.log('[BID MODAL] Extracted delivery address:', deliveryAddress);

    // Add address fields to formData (they don't have name attributes in template)
    formData.append('address_line1', addressLine1);
    formData.append('address_line2', addressLine2);
    formData.append('city', city);
    formData.append('state', state);
    formData.append('zip_code', zipCode);

    // Store form reference and action for later submission
    window.pendingBidFormData = {
      form: form,
      formData: formData,
      action: form.action,
      itemDesc: undefined,
      metal: metal,
      weight: weightStr
    };

    // Wizard mode: skip the extra confirmation modal and submit directly
    if (window.bidWizardMode) {
      window.bidWizardMode = false;
      submitBidForm();
      return;
    }

    // Open confirmation modal with data
    openBidConfirmModal({
      itemDesc: 'Bid item',  // Will be populated by bid_confirm_modal.js
      requiresGrading: requiresGrading,
      price: bidPrice,
      quantity: bidQuantity,
      isEdit: isEdit,
      pricingMode: pricingMode,
      spotPremium: spotPremium,
      ceilingPrice: ceilingPrice,
      pricingMetal: pricingMetal,
      metal: metal,
      weight: weightStr,
      deliveryAddress: deliveryAddress
    });
  });
}

/* ----- Actual bid submission (called after confirmation) ----- */
window.submitBidForm = function() {
  const pending = window.pendingBidFormData;
  if (!pending) {
    console.error('No pending bid form data found');
    return;
  }

  const form = pending.form;
  const formData = pending.formData;
  const btn = document.getElementById('eb-confirm');
  const wizardBtn = document.getElementById('bm-submit');

  // Disable button to prevent double submission
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Submitting...';
  }

  fetch(pending.action, { method: 'POST', body: formData })
    .then(res => res.json())
    .then(data => {
      if (!data.success) {
        // Re-enable buttons
        if (btn)       { btn.disabled = false;       btn.textContent = 'Confirm'; }
        if (wizardBtn) { wizardBtn.disabled = false;  wizardBtn.textContent = 'Confirm Bid'; }

        // Show validation errors
        if (data.errors) {
          Object.entries(data.errors).forEach(([name, msg]) => {
            const input = form.querySelector(`[name="${name}"]`);
            if (input) {
              const err = document.createElement('p');
              err.className = 'error-msg';
              err.textContent = msg;
              input.insertAdjacentElement('afterend', err);
            }
          });
          closeBidConfirmModal();
        } else if (data.strike_blocked) {
          // Account restricted — replace bid modal content with a clear message
          closeBidConfirmModal();
          const content = document.getElementById('bidModalContent');
          if (content) {
            content.innerHTML = `
              <button type="button" class="modal-close" onclick="closeBidModal()" aria-label="Close modal">×</button>
              <div class="bm-auth-prompt">
                <div class="bm-auth-icon" style="background: rgba(239,68,68,0.1);">
                  <i class="fa-solid fa-ban" style="color: #ef4444;"></i>
                </div>
                <div class="bm-auth-logo">MetEx</div>
                <h2 class="bm-auth-title" style="color: #ef4444;">Bid Placement Restricted</h2>
                <p class="bm-auth-sub">Your account has been restricted from placing bids due to multiple payment failures. Please contact support to restore access.</p>
                <div class="bm-auth-actions">
                  <button type="button" onclick="closeBidModal()" class="bm-auth-btn-primary">Close</button>
                </div>
              </div>
            `;
          }
        } else if (data.requires_saved_card) {
          // No saved card — prompt buyer to add one
          closeBidConfirmModal();
          const content = document.getElementById('bidModalContent');
          if (content) {
            content.innerHTML = `
              <button type="button" class="modal-close" onclick="closeBidModal()" aria-label="Close modal">×</button>
              <div class="bm-auth-prompt">
                <div class="bm-auth-icon" style="background: rgba(59,130,246,0.1);">
                  <i class="fa-solid fa-credit-card" style="color: #3b82f6;"></i>
                </div>
                <div class="bm-auth-logo">MetEx</div>
                <h2 class="bm-auth-title">Payment Method Required</h2>
                <p class="bm-auth-sub">A saved payment card is required to place a bid. Your card is only charged if a seller accepts your bid — there's no charge now.</p>
                <div class="bm-auth-actions">
                  <button type="button" onclick="window.location.href='/account'" class="bm-auth-btn-primary">
                    <i class="fa-solid fa-plus"></i> Add a Card
                  </button>
                  <button type="button" onclick="closeBidModal()" class="bm-auth-btn-secondary">Cancel</button>
                </div>
              </div>
            `;
          }
        } else {
          alert(data.message || 'Something went wrong.');
          closeBidConfirmModal();
        }

        return;
      }

      // Success!
      // Wizard mode: show inline checkmark animation (skips the success modal)
      if (document.querySelector('.bm-wizard') && typeof window.showWizardSuccess === 'function') {
        window.pendingBidFormData = null;
        window.showWizardSuccess();
        return;
      }

      // Non-wizard fallback: old success modal flow
      closeBidConfirmModal();
      closeBidModal();

      // Extract bid data for success modal
      const pricingMode = formData.get('bid_pricing_mode') || 'static';
      let bidPrice, bidQuantity, spotPremium, ceilingPrice, pricingMetal;

      if (pricingMode === 'premium_to_spot') {
        bidQuantity = parseInt(formData.get('bid_quantity_premium')) || 0;
        spotPremium = parseFloat(formData.get('bid_spot_premium')) || 0;
        ceilingPrice = parseFloat(formData.get('bid_ceiling_price')) || 0;
        pricingMetal = formData.get('bid_pricing_metal') || '';
        bidPrice = ceilingPrice; // Use floor as display price
      } else {
        bidQuantity = parseInt(formData.get('bid_quantity') || formData.get('quantity_requested')) || 0;
        bidPrice = parseFloat(formData.get('bid_price') || formData.get('price_per_coin')) || 0;
      }

      // Extract delivery address from DOM (fields don't have name attributes, but we added them to formData)
      const addressLine1 = formData.get('address_line1') || document.getElementById('addr-line1')?.value || '';
      const addressLine2 = formData.get('address_line2') || document.getElementById('addr-line2')?.value || '';
      const city = formData.get('city') || document.getElementById('addr-city')?.value || '';
      const state = formData.get('state') || document.getElementById('addr-state')?.value || '';
      const zipCode = formData.get('zip_code') || document.getElementById('addr-zip')?.value || '';

      // Construct delivery address in bullet-separated format
      let deliveryAddress = '';
      if (addressLine1 || city || state || zipCode) {
        const parts = [];
        if (addressLine1) parts.push(addressLine1);
        if (addressLine2) parts.push(addressLine2);

        // Build city/state/zip string
        const cityStateZip = [city, state && zipCode ? `${state} ${zipCode}` : state || zipCode]
          .filter(Boolean)
          .join(', ');

        if (cityStateZip) parts.push(cityStateZip);

        deliveryAddress = parts.join(' • ');
      }

      // Extract bucket specs from form data attributes for Item Details section
      let bucketMetal = '', bucketProductLine = '', bucketProductType = '', bucketWeight = '';
      let bucketYear = '', bucketMint = '', bucketPurity = '', bucketFinish = '';

      if (form) {
        bucketMetal = form.dataset.bucketMetal || '';
        bucketProductLine = form.dataset.bucketProductLine || '';
        bucketProductType = form.dataset.bucketProductType || '';
        bucketWeight = form.dataset.bucketWeight || '';
        bucketYear = form.dataset.bucketYear || '';
        bucketMint = form.dataset.bucketMint || '';
        bucketPurity = form.dataset.bucketPurity || '';
        bucketFinish = form.dataset.bucketFinish || '';
      }

      const bidData = {
        quantity: bidQuantity,
        price: bidPrice,
        itemDesc: pending.itemDesc || getBucketDescription(),
        pricingMode: pricingMode,
        spotPremium: spotPremium,
        ceilingPrice: ceilingPrice,
        pricingMetal: pricingMetal,
        metal: pending.metal || pricingMetal,
        weight: pending.weight,
        // Grading preference
        requiresGrading: formData.get('requires_grading') === 'yes',
        // Include server response data (takes priority over client-side calculations)
        effectivePrice: data.effective_price,
        currentSpotPrice: data.current_spot_price,
        // Include delivery address for success modal
        deliveryAddress: deliveryAddress,
        // Include all bucket specs for Item Details section
        bucketMetal: bucketMetal,
        bucketProductLine: bucketProductLine,
        bucketProductType: bucketProductType,
        bucketWeight: bucketWeight,
        bucketYear: bucketYear,
        bucketMint: bucketMint,
        bucketPurity: bucketPurity,
        bucketFinish: bucketFinish
      };

      // Debug logging
      console.log('Success modal data:', bidData);
      console.log('Server response:', data);

      // Show success modal (will reload page when closed)
      if (typeof window.openBidSuccessModal === 'function') {
        window.openBidSuccessModal(bidData);
      } else {
        // Fallback: just reload if success modal not available
        location.reload();
      }

      // Clear pending data
      window.pendingBidFormData = null;
    })
    .catch(err => {
      console.error('❌ Form submission failed:', err);

      // Re-enable buttons
      if (btn)       { btn.disabled = false;       btn.textContent = 'Confirm'; }
      if (wizardBtn) { wizardBtn.disabled = false;  wizardBtn.textContent = 'Confirm Bid'; }

      alert('Server error occurred. Please try again.');
      closeBidConfirmModal();
    });
};
