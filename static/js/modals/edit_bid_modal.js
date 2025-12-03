// static/js/modals/edit_bid_modal.js
'use strict';

/* ==========================================================================
   Edit Bid Modal — open/close + form wiring (3-column UI, Best Bid removed)
   ========================================================================== */

function openEditBidModal(bidId) {
  const modal   = document.getElementById('editBidModal');
  const content = document.getElementById('editBidModalContent');
  if (!modal || !content) {
    console.error('Modal container missing (#editBidModal or #editBidModalContent).');
    return;
  }

  content.innerHTML = '';

  fetch(`/bids/edit_form/${bidId}`, {
    cache: 'no-store',
    redirect: 'follow',
    credentials: 'same-origin',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then(async resp => {
      const text = await resp.text();
      if (!resp.ok) throw new Error(`HTTP ${resp.status} — ${text.slice(0, 500)}`);
      return text;
    })
    .then(html => {
      content.innerHTML = html;

      modal.style.display = 'flex';
      modal.classList.add('active');

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

      try { initEditBidFormSafe(); } catch (e) {
        console.error('Init error inside initEditBidForm:', e);
        const warn = document.createElement('div');
        warn.className = 'error-msg';
        warn.style.marginTop = '12px';
        warn.textContent = 'Form loaded, but initialization failed. See console for details.';
        content.prepend(warn);
      }
    })
    .catch(err => {
      console.error('❌ Edit form fetch error:', err);
      content.innerHTML =
        '<div class="edit-bid-modal"><h2>Edit Your Bid</h2><p class="error-msg">Error loading form. Please try again.</p></div>';
      modal.style.display = 'flex';
      modal.classList.add('active');
    });
}

function closeEditBidModal() {
  const modal   = document.getElementById('editBidModal');
  const content = document.getElementById('editBidModalContent');
  if (modal) {
    modal.style.display = 'none';
    modal.classList.remove('active');
  }
  if (content) content.innerHTML = '';
  if (typeof showTab === 'function') showTab('bids');
}

window.openEditBidModal  = openEditBidModal;
window.closeEditBidModal = closeEditBidModal;

// Close on overlay click
window.addEventListener('click', (e) => {
  const modal = document.getElementById('editBidModal');
  if (e.target === modal) closeEditBidModal();
});

// Close on Escape
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeEditBidModal();
});

/* ==========================================================================
   Init (null-safe)
   ========================================================================== */
function initEditBidFormSafe() {
  const grid = document.getElementById('eb-grid');
  const form = document.getElementById('bid-form');
  if (!form) {
    console.warn('Bid form not found (#bid-form). Aborting init.');
    return;
  }

  /* ----- Grading (header in col1, dropdown body just below) ----- */
  const grading       = document.getElementById('eb-grading');
  const headerBtn     = document.getElementById('eb-grading-header');
  const chev          = document.getElementById('eb-grading-chev');
  const menu          = document.getElementById('eb-grading-menu');

  const requiresGrading = document.getElementById('requires_grading');  // hidden
  const preferredHidden = document.getElementById('preferred_grader');  // hidden

  const swAny  = document.getElementById('grader_any');
  const swPCGS = document.getElementById('grader_pcgs');
  const swNGC  = document.getElementById('grader_ngc');

  headerBtn && headerBtn.addEventListener('click', () => {
    if (!grid) return;
    const open = !grid.classList.contains('grading-open');
    grid.classList.toggle('grading-open', open);
    grading && grading.setAttribute('aria-expanded', open ? 'true' : 'false');
    menu && menu.setAttribute('aria-hidden', open ? 'false' : 'true');
    headerBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (chev) chev.textContent = open ? '▴' : '▾';
  });

  function updatePrefAndFlags() {
    if (swAny && swAny.checked) {
      if (swPCGS) { swPCGS.checked = false; swPCGS.disabled = true; }
      if (swNGC)  { swNGC.checked  = false; swNGC.disabled  = true; }
      if (preferredHidden) preferredHidden.value = 'Any';
    } else {
      if (swPCGS) swPCGS.disabled = false;
      if (swNGC)  swNGC.disabled  = false;
      if (swPCGS && swNGC && swPCGS.checked && swNGC.checked) swNGC.checked = false;

      if (preferredHidden) {
        if (swPCGS && swPCGS.checked) preferredHidden.value = 'PCGS';
        else if (swNGC && swNGC.checked) preferredHidden.value = 'NGC';
        else preferredHidden.value = '';
      }
    }
    const hasChoice = !!(preferredHidden && preferredHidden.value);
    if (requiresGrading) requiresGrading.value = hasChoice ? 'yes' : 'no';
    validateAll();
  }
  swAny && swAny.addEventListener('change', updatePrefAndFlags);
  swPCGS && swPCGS.addEventListener('change', updatePrefAndFlags);
  swNGC && swNGC.addEventListener('change', updatePrefAndFlags);
  updatePrefAndFlags();

  /* ----- Pricing Mode Toggle ----- */
  const pricingModeSelect = document.getElementById('bid-pricing-mode');
  const staticPricingFields = document.getElementById('static-pricing-fields');
  const premiumPricingFields = document.getElementById('premium-pricing-fields');

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
      const priceInput = document.getElementById('bid-price-input');
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
      const premiumInput = document.getElementById('bid-spot-premium');
      const floorInput = document.getElementById('bid-floor-price');
      if (premiumInput) premiumInput.value = '';
      if (floorInput) floorInput.value = '';
    }

    validateAll();
  }

  if (pricingModeSelect) {
    pricingModeSelect.addEventListener('change', updatePricingFieldsVisibility);
    // Initialize visibility on load
    updatePricingFieldsVisibility();
  }

  /* ----- Quantity dial (static mode) ----- */
  const qtyInput = document.getElementById('qty-input'); // hidden number
  const qtyDec   = document.getElementById('qty-dec');
  const qtyInc   = document.getElementById('qty-inc');
  const qtyValue = document.getElementById('qty-value');
  const qtyHint  = document.getElementById('qty-hint');

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

  // click
  qtyDec && qtyDec.addEventListener('click', (e) => { e.preventDefault(); setQty((Number(qtyInput && qtyInput.value) || 1) - 1); });
  qtyInc && qtyInc.addEventListener('click', (e) => { e.preventDefault(); setQty((Number(qtyInput && qtyInput.value) || 1) + 1); });

  // mouse hold
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

  /* ----- Quantity dial (premium mode) ----- */
  const qtyInputPremium = document.getElementById('qty-input-premium');
  const qtyDecPremium   = document.getElementById('qty-dec-premium');
  const qtyIncPremium   = document.getElementById('qty-inc-premium');
  const qtyValuePremium = document.getElementById('qty-value-premium');

  function setQtyPremium(n) {
    const v = clampQty(n);
    if (qtyInputPremium) qtyInputPremium.value = String(v);
    if (qtyValuePremium) qtyValuePremium.textContent = String(v);
    validateAll();
  }
  setQtyPremium(Number((qtyInputPremium && qtyInputPremium.value) || (qtyValuePremium && qtyValuePremium.textContent) || 1));

  let holdTimerPremium = null, stepTimerPremium = null;
  function startHoldPremium(delta) {
    setQtyPremium((Number(qtyInputPremium && qtyInputPremium.value) || 1) + delta);
    holdTimerPremium = setTimeout(() => {
      stepTimerPremium = setInterval(() => setQtyPremium((Number(qtyInputPremium && qtyInputPremium.value) || 1) + delta), 80);
    }, 350);
  }
  function stopHoldPremium() { clearTimeout(holdTimerPremium); clearInterval(stepTimerPremium); }

  // click
  qtyDecPremium && qtyDecPremium.addEventListener('click', (e) => { e.preventDefault(); setQtyPremium((Number(qtyInputPremium && qtyInputPremium.value) || 1) - 1); });
  qtyIncPremium && qtyIncPremium.addEventListener('click', (e) => { e.preventDefault(); setQtyPremium((Number(qtyInputPremium && qtyInputPremium.value) || 1) + 1); });

  // mouse hold
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

  /* ----- Price field (static mode) ----- */
  const priceInput = document.getElementById('bid-price-input');
  const priceHint  = document.getElementById('price-hint');

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

  /* ----- Premium-to-Spot fields (premium mode) ----- */
  const premiumInput = document.getElementById('bid-spot-premium');
  const floorPriceInput = document.getElementById('bid-floor-price');
  const premiumDisplay = document.getElementById('premium-display');
  const effectiveBidPrice = document.getElementById('effective-bid-price');
  const currentSpotPriceElem = document.getElementById('current-spot-price');

  // Function to update effective bid price display
  function updateEffectiveBidPrice() {
    if (!premiumInput || !premiumDisplay || !effectiveBidPrice || !currentSpotPriceElem) return;

    const premium = Number(premiumInput.value) || 0;
    const spotPriceText = currentSpotPriceElem.textContent.replace(/[^0-9.]/g, '');
    const spotPrice = Number(spotPriceText) || 0;
    const effective = spotPrice + premium;

    premiumDisplay.textContent = premium.toFixed(2);
    effectiveBidPrice.textContent = effective.toFixed(2);
  }

  // Enforce numeric input and format on blur for premium field
  if (premiumInput) {
    premiumInput.addEventListener('beforeinput', (e) => {
      if (e.inputType === 'insertText' && /[^\d.]/.test(e.data)) e.preventDefault();
    });
    premiumInput.addEventListener('input', () => {
      let v = premiumInput.value.replace(/[^\d.]/g, '');
      const parts = v.split('.');
      if (parts.length > 2) v = parts[0] + '.' + parts.slice(1).join('');
      premiumInput.value = v;
      updateEffectiveBidPrice();  // Update display in real-time
    });
    premiumInput.addEventListener('blur', () => {
      const n = Number(premiumInput.value);
      if (isFinite(n) && n >= 0) {
        premiumInput.value = (Math.round(n * 100) / 100).toFixed(2);
      }
      updateEffectiveBidPrice();
      validateAll();
    });
  }

  // Enforce numeric input and format on blur for floor price (minimum)
  if (floorPriceInput) {
    floorPriceInput.addEventListener('beforeinput', (e) => {
      if (e.inputType === 'insertText' && /[^\d.]/.test(e.data)) e.preventDefault();
    });
    floorPriceInput.addEventListener('input', () => {
      let v = floorPriceInput.value.replace(/[^\d.]/g, '');
      const parts = v.split('.');
      if (parts.length > 2) v = parts[0] + '.' + parts.slice(1).join('');
      floorPriceInput.value = v;
    });
    floorPriceInput.addEventListener('blur', () => {
      const n = Number(floorPriceInput.value);
      if (isFinite(n) && n > 0) {
        floorPriceInput.value = (Math.round(n * 100) / 100).toFixed(2);
      }
      validateAll();
    });
  }

  /* ----- Address (multi-field) ----- */
  const addr = {
    single:  document.getElementById('address-input'), // legacy single-line (if ever re-enabled)
    first:   document.getElementById('addr-first'),
    last:    document.getElementById('addr-last'),
    line1:   document.getElementById('addr-line1'),
    line2:   document.getElementById('addr-line2'),
    city:    document.getElementById('addr-city'),
    state:   document.getElementById('addr-state'),
    zip:     document.getElementById('addr-zip')
  };
  const addressHint = document.getElementById('address-hint') || document.querySelector('.addr-hint');

  function combinedAddressFromFields() {
    if (addr.single) return addr.single.value.trim();

    const parts = [];
    const first = addr.first && addr.first.value && addr.first.value.trim();
    const last  = addr.last  && addr.last.value  && addr.last.value.trim();
    const nameLine = [first, last].filter(Boolean).join(' ');
    if (nameLine) parts.push(nameLine);

    const line1 = addr.line1 && addr.line1.value && addr.line1.value.trim();
    const line2 = addr.line2 && addr.line2.value && addr.line2.value.trim();
    if (line1) parts.push(line1);
    if (line2) parts.push(line2);

    const city  = addr.city && addr.city.value && addr.city.value.trim();
    const state = addr.state && addr.state.value && addr.state.value.trim();
    const zip   = addr.zip && addr.zip.value && addr.zip.value.trim();
    const cityLine = [city, state, zip].filter(Boolean).join(', ');
    if (cityLine) parts.push(cityLine);

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

  // Required fields: line1, city, state, zip (names not required yet)
  const addrRequiredFields = [addr.line1, addr.city, addr.state, addr.zip];
  addrRequiredFields.forEach(el => el && el.addEventListener('input', validateAll));
  addr.single && addr.single.addEventListener('input', validateAll);

  /* ----- Master validation ----- */
  const confirmBtn = document.getElementById('eb-confirm');

  function validateAll() {
    // Determine which pricing mode is active
    const mode = pricingModeSelect ? pricingModeSelect.value : 'static';
    let pricingOk = false;
    let qtyOk = false;

    if (mode === 'premium_to_spot') {
      // Premium-to-spot mode: validate premium fields
      const premium = Number(premiumInput && premiumInput.value);
      const floor = Number(floorPriceInput && floorPriceInput.value);

      // Premium can be 0 or positive, floor must be > 0
      const premiumValid = isFinite(premium) && premium >= 0;
      const floorValid = isFinite(floor) && floor > 0;

      pricingOk = premiumValid && floorValid;

      // Check premium quantity
      const qPremium = Number(qtyInputPremium && qtyInputPremium.value);
      qtyOk = Number.isInteger(qPremium) && qPremium >= 1;
    } else {
      // Static mode: validate static price
      const p = Number(priceInput && priceInput.value);
      pricingOk = isFinite(p) && p >= 0.01;
      if (priceHint) priceHint.textContent = pricingOk ? '' : 'Price must be at least $0.01';

      // Check static quantity
      const q = Number(qtyInput && qtyInput.value);
      qtyOk = Number.isInteger(q) && q >= 1;
      if (qtyHint) qtyHint.textContent = qtyOk ? '' : 'Quantity must be at least 1';
    }

    // Validate address (same for both modes)
    let addrOk = true;
    if (addr.single) {
      addrOk = addr.single.value.trim().length > 0;
      if (addressHint) addressHint.textContent = addrOk ? '' : 'Delivery address is required.';
    } else {
      addrOk = addrRequiredFields.every(el => el && el.value && el.value.trim().length > 0);
      if (addressHint) addressHint.textContent = addrOk ? '' : 'Please complete address, city, state, and zip.';
    }

    ensureCombinedHidden();
    if (confirmBtn) confirmBtn.disabled = !(pricingOk && qtyOk && addrOk);
  }

  validateAll();

  /* ----- Submit (AJAX) ----- */
  form.addEventListener('submit', (e) => {
    e.preventDefault();

    try { updatePrefAndFlags && updatePrefAndFlags(); } catch {}

    validateAll();
    const btn = document.getElementById('eb-confirm');
    if (btn && btn.disabled) return;

    form.querySelectorAll('.error-msg').forEach(el => el.remove());

    ensureCombinedHidden();

    const formData = new FormData(form);
    fetch(form.action, { method: 'POST', body: formData })
      .then(res => res.json())
      .then(data => {
        if (!data.success) {
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
          } else {
            alert(data.message || 'Something went wrong.');
          }
          return;
        }
        alert('✅ ' + data.message);
        closeEditBidModal();
        location.reload();
      })
      .catch(err => {
        console.error('Form submission failed:', err);
        alert('Server error occurred.');
      });
  });
}
