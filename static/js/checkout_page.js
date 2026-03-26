// static/js/checkout_page.js
// Checkout page functionality - 3-step checkout flow

// ---------------------------------------------------------------------------
// Stripe setup
// ---------------------------------------------------------------------------
let _stripe = null;
let _stripeElements = null;
let _stripePaymentIntentId = null;
let _stripeInitStarted = false;     // guard against double-init
let _stripeSelectedMethod = 'card'; // tracks active Stripe Payment Element tab
let _clientSecret = null;           // stored for saved-card confirmation
let _selectedSavedPmId = null;      // null = new card; 'pm_xxx' = saved card selected
let _savedCardInfo = {};            // pm_id → {brand, last4, exp_month, exp_year}
let _paymentElementMounted = false; // guard against double-mount

function _showPaymentLoading(visible) {
  const el = document.getElementById('payment-loading-message');
  if (el) el.style.display = visible ? 'block' : 'none';
}

function _showPaymentError(msg) {
  _showPaymentLoading(false);
  const el = document.getElementById('payment-element-error');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
  console.error('[Stripe]', msg);
}

/**
 * Called the first time step 2 (Payment) becomes visible.
 * Always fetches a PaymentIntent (for clientSecret).
 * Mounts the Stripe Payment Element only in new-card mode.
 */
async function initStripeElements() {
  if (_stripeInitStarted) return;
  _stripeInitStarted = true;

  console.log('[Stripe] initStripeElements starting');

  const key = window.stripePublishableKey;
  if (!key) {
    _showPaymentError('Payment system configuration error. Please contact support.');
    return;
  }

  if (typeof Stripe === 'undefined') {
    _showPaymentError('Stripe.js failed to load. Please refresh the page.');
    return;
  }

  _stripe = Stripe(key);
  _showPaymentLoading(true);

  try {
    const res = await fetch('/create-payment-intent', { method: 'POST' });
    console.log('[Stripe] create-payment-intent status:', res.status);

    if (!res.ok) {
      const text = await res.text();
      console.error('[Stripe] server error body:', text);
      _showPaymentError('Could not start payment session (HTTP ' + res.status + '). Please refresh.');
      return;
    }

    const data = await res.json();

    if (data.error) {
      _showPaymentError('Payment setup failed: ' + data.error);
      return;
    }

    if (!data.clientSecret) {
      _showPaymentError('Payment setup returned no client secret. Please refresh.');
      return;
    }

    _clientSecret = data.clientSecret;
    _stripePaymentIntentId = data.paymentIntentId;

    // If the user already selected a saved card (cards loaded before step 2),
    // skip mounting the Payment Element — the saved card is all we need.
    if (_selectedSavedPmId) {
      _showPaymentLoading(false);
      console.log('[Stripe] saved card pre-selected — skipping Payment Element mount');
      return;
    }

    // New-card mode: mount the Stripe Payment Element.
    await _mountPaymentElement();

  } catch (err) {
    _showPaymentError('Payment form failed to load. Please refresh. (' + err.message + ')');
  }
}

/**
 * Mount the Stripe Payment Element into #payment-element.
 * Safe to call multiple times — guarded by _paymentElementMounted flag.
 * Requires _stripe and _clientSecret to already be set.
 */
async function _mountPaymentElement() {
  if (_paymentElementMounted) return;
  if (!_stripe || !_clientSecret) return;

  _paymentElementMounted = true;

  const mountTarget = document.getElementById('payment-element');
  if (!mountTarget) {
    _showPaymentError('Payment form container missing. Please refresh.');
    return;
  }

  _stripeElements = _stripe.elements({ clientSecret: _clientSecret });
  const paymentEl = _stripeElements.create('payment');
  paymentEl.mount('#payment-element');
  _showPaymentLoading(false);
  console.log('[Stripe] Payment Element mounted successfully');

  // Fee badge — always shows both options; ACH always highlighted green.
  var feeBadge = document.getElementById('payment-fee-badge');
  function _setFeeBadge(type) {
    _stripeSelectedMethod = type || 'card';
    if (!feeBadge) return;
    feeBadge.style.display = 'block';
    feeBadge.style.background = '';
    feeBadge.style.color = '';
    feeBadge.style.border = '';
    feeBadge.innerHTML =
      '<span style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">' +
        '<i class="fa-solid fa-circle-info" style="color:#6b7280;"></i>' +
        '<span style="color:#374151;">Card payment &mdash; <strong>2.99% processing fee</strong></span>' +
      '</span>' +
      '<span style="display:flex;align-items:center;gap:6px;background:#ecfdf5;color:#065f46;border:1px solid #6ee7b7;border-radius:5px;padding:4px 8px;">' +
        '<i class="fa-solid fa-circle-check" style="color:#10b981;"></i>' +
        '<span>ACH Bank Transfer &mdash; <strong>Free</strong></span>' +
      '</span>';
    updateOrderSummary();
  }
  _setFeeBadge('card');
  paymentEl.on('change', function(event) {
    var type = event && event.value && event.value.type;
    _setFeeBadge(type || 'card');
  });
}

document.addEventListener('DOMContentLoaded', function() {
  initSavedAddresses();
  initPaymentMethodSelection();
  initCardFormatting();
  loadUserInfo();
  loadSavedPaymentMethods();
  updateOrderSummary();
  _restoreCheckoutDraft();
  // Do NOT call initStripeElements() here — #payment-element is inside a
  // display:none step at this point.  It is called lazily from goToStep(2).
});

// Current step tracking
let currentStep = 1;

/**
 * Navigate to a specific step
 */
function goToStep(step) {
  // Validate current step before moving forward
  if (step > currentStep) {
    if (!validateStep(currentStep)) {
      return;
    }
  }

  // Update progress indicators
  updateProgress(step);

  // Hide all steps and show target
  document.querySelectorAll('.checkout-step').forEach(s => s.classList.remove('active'));

  const stepIds = ['step-shipping', 'step-payment', 'step-review'];
  const targetStep = document.getElementById(stepIds[step - 1]);
  if (targetStep) {
    targetStep.classList.add('active');
  }

  // Lazy-init Stripe the first time the payment step becomes visible.
  // Must happen AFTER the step div gains display:block (active class added above).
  if (step === 2) {
    initStripeElements();
  }

  // If going to review step, populate review data
  if (step === 3) {
    populateReviewData();
  }

  currentStep = step;

  // Scroll to top
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
window.goToStep = goToStep;

/**
 * Update progress indicators
 */
function updateProgress(step) {
  const steps = document.querySelectorAll('.progress-step');
  const connectors = document.querySelectorAll('.progress-connector');

  steps.forEach((s, index) => {
    const stepNum = index + 1;
    s.classList.remove('active', 'completed');

    if (stepNum < step) {
      s.classList.add('completed');
    } else if (stepNum === step) {
      s.classList.add('active');
    }
  });

  connectors.forEach((c, index) => {
    if (index < step - 1) {
      c.classList.add('active');
    } else {
      c.classList.remove('active');
    }
  });
}

/**
 * Validate current step
 */
function validateStep(step) {
  if (step === 1) {
    return validateShippingForm();
  } else if (step === 2) {
    return validatePaymentForm();
  }
  return true;
}

/**
 * Validate shipping form
 */
function validateShippingForm() {
  const form = document.getElementById('shippingForm');
  const requiredFields = ['firstName', 'lastName', 'email', 'phone', 'streetAddress', 'city', 'state', 'zipCode'];

  let isValid = true;

  requiredFields.forEach(fieldId => {
    const field = document.getElementById(fieldId);
    if (!field.value.trim()) {
      field.style.borderColor = '#ef4444';
      isValid = false;
    } else {
      field.style.borderColor = '#e5e7eb';
    }
  });

  // Validate email format
  const email = document.getElementById('email');
  if (email.value && !isValidEmail(email.value)) {
    email.style.borderColor = '#ef4444';
    isValid = false;
  }

  if (!isValid) {
    alert('Please fill in all required fields.');
  }

  return isValid;
}

/**
 * Validate payment form.
 * A selected saved card is always valid.
 * For new-card mode, Stripe Elements handles its own validation — just check it loaded.
 */
function validatePaymentForm() {
  if (_selectedSavedPmId) return true;
  if (!_stripeElements) {
    alert('Payment form is still loading. Please wait a moment and try again.');
    return false;
  }
  return true;
}

/**
 * Validate email format
 */
function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/**
 * Populate review data from forms
 */
function populateReviewData() {
  // Shipping data
  const firstName = document.getElementById('firstName').value;
  const lastName = document.getElementById('lastName').value;
  const street = document.getElementById('streetAddress').value;
  const apartment = document.getElementById('apartment').value;
  const city = document.getElementById('city').value;
  const state = document.getElementById('state').value;
  const zipCode = document.getElementById('zipCode').value;
  const email = document.getElementById('email').value;
  const phone = document.getElementById('phone').value;

  document.getElementById('reviewName').textContent = `${firstName} ${lastName}`;

  let addressLines = street;
  if (apartment) addressLines += `, ${apartment}`;
  addressLines += `\n${city}, ${state} ${zipCode}`;
  document.getElementById('reviewAddress').innerHTML = addressLines.replace('\n', '<br>');

  document.getElementById('reviewEmail').textContent = email;
  document.getElementById('reviewPhone').textContent = phone;

  // Payment data
  const paymentDisplay = document.getElementById('paymentDisplay');
  if (paymentDisplay) {
    if (_selectedSavedPmId && _savedCardInfo[_selectedSavedPmId]) {
      const c = _savedCardInfo[_selectedSavedPmId];
      const exp = String(c.exp_month).padStart(2, '0') + '/' + String(c.exp_year).slice(-2);
      paymentDisplay.innerHTML =
        '<i class="' + getCardIcon(c.brand) + '"></i> <span>' +
        capitalizeFirst(c.brand) + ' •••• ' + c.last4 + ' · exp ' + exp + '</span>';
    } else {
      paymentDisplay.innerHTML = '<i class="fa-solid fa-credit-card"></i> <span>Secure payment via Stripe</span>';
    }
  }
}

/**
 * Initialize saved addresses dropdown
 */
function initSavedAddresses() {
  const btn = document.getElementById('savedAddressesBtn');
  const menu = document.getElementById('savedAddressesMenu');

  if (!btn || !menu) return;

  btn.addEventListener('click', function(e) {
    e.stopPropagation();
    menu.classList.toggle('show');

    if (menu.classList.contains('show')) {
      loadSavedAddresses();
    }
  });

  // Close on click outside
  document.addEventListener('click', function(e) {
    if (!e.target.closest('.saved-addresses-dropdown')) {
      menu.classList.remove('show');
    }
  });
}

/**
 * Load saved addresses from API
 */
function loadSavedAddresses() {
  const menu = document.getElementById('savedAddressesMenu');

  fetch('/account/get_addresses')
    .then(response => response.json())
    .then(data => {
      if (data.success && data.addresses && data.addresses.length > 0) {
        menu.innerHTML = data.addresses.map(addr => `
          <div class="saved-address-item" onclick="selectAddress(${JSON.stringify(addr).replace(/"/g, '&quot;')})">
            <div class="saved-address-name">${addr.name || 'Address'}</div>
            <div class="saved-address-preview">${addr.street}, ${addr.city}</div>
          </div>
        `).join('');
      } else {
        menu.innerHTML = '<div class="saved-address-item"><div class="saved-address-preview">No saved addresses</div></div>';
      }
    })
    .catch(err => {
      console.error('Error loading addresses:', err);
      menu.innerHTML = '<div class="saved-address-item"><div class="saved-address-preview">Error loading addresses</div></div>';
    });
}

/**
 * Select a saved address
 */
function selectAddress(addr) {
  document.getElementById('streetAddress').value = addr.street || '';
  document.getElementById('apartment').value = addr.street_line2 || '';
  document.getElementById('city').value = addr.city || '';
  document.getElementById('state').value = addr.state || '';
  document.getElementById('zipCode').value = addr.zip_code || '';
  document.getElementById('country').value = addr.country || 'United States';

  // Close dropdown
  document.getElementById('savedAddressesMenu').classList.remove('show');
}
window.selectAddress = selectAddress;

/**
 * Load user info (name, email) for pre-fill
 */
function loadUserInfo() {
  fetch('/account/get_addresses')
    .then(response => response.json())
    .then(data => {
      if (data.success && data.user_info) {
        const firstName = document.getElementById('firstName');
        const lastName = document.getElementById('lastName');

        if (firstName && !firstName.value && data.user_info.first_name) {
          firstName.value = data.user_info.first_name;
        }
        if (lastName && !lastName.value && data.user_info.last_name) {
          lastName.value = data.user_info.last_name;
        }
      }
    })
    .catch(err => console.error('Error loading user info:', err));
}

/**
 * Update the order summary sidebar based on selected payment method.
 * Processing fee: 2.99% for card, Free for ACH.
 * Grading fee: injected from server via window.checkoutGradingFee.
 */
function updateOrderSummary() {
  const checkedRadio = document.querySelector('input[name="payment_method"]:checked');
  const method = checkedRadio ? checkedRadio.value : 'card';
  // Also treat Stripe Element's ACH tab as ACH
  const isACH = method === 'ach' || _stripeSelectedMethod === 'us_bank_account';

  const subtotal    = window.checkoutSubtotal   || 0;
  const gradingFee  = window.checkoutGradingFee || 0;
  const processingFee = isACH ? 0 : (subtotal + gradingFee) * 0.0299;

  const total = subtotal + gradingFee + processingFee;

  const feeEl = document.getElementById('summary-processing-fee');
  if (feeEl) {
    feeEl.textContent = isACH ? 'Free' : '$' + processingFee.toFixed(2);
    feeEl.classList.toggle('summary-value-free', isACH);
  }

  const totalEl = document.getElementById('summary-total');
  if (totalEl) totalEl.textContent = '$' + total.toFixed(2);

  const placeOrderTotal = document.getElementById('place-order-total');
  if (placeOrderTotal) placeOrderTotal.textContent = '$' + total.toFixed(2);
}
window.updateOrderSummary = updateOrderSummary;

/**
 * Initialize payment method selection
 */
function initPaymentMethodSelection() {
  const paymentOptions = document.querySelectorAll('.payment-option');
  const cardForm = document.getElementById('cardForm');
  const achForm = document.getElementById('achForm');

  paymentOptions.forEach(option => {
    option.addEventListener('click', function() {
      // Update selected state
      paymentOptions.forEach(o => o.classList.remove('selected'));
      this.classList.add('selected');

      // Check the radio
      const radio = this.querySelector('input[type="radio"]');
      radio.checked = true;

      // Show/hide appropriate form
      const method = radio.value;

      if (cardForm) cardForm.style.display = method === 'card' ? 'block' : 'none';
      if (achForm) achForm.style.display = method === 'ach' ? 'block' : 'none';

      // Recalculate order summary totals
      updateOrderSummary();
    });
  });
}

/**
 * Initialize card number formatting
 */
function initCardFormatting() {
  const cardNumber = document.getElementById('cardNumber');
  const expiryDate = document.getElementById('expiryDate');
  const cvv = document.getElementById('cvv');

  if (cardNumber) {
    cardNumber.addEventListener('input', function(e) {
      let value = this.value.replace(/\D/g, '');
      let formatted = '';

      for (let i = 0; i < value.length && i < 16; i++) {
        if (i > 0 && i % 4 === 0) {
          formatted += ' ';
        }
        formatted += value[i];
      }

      this.value = formatted;
    });
  }

  if (expiryDate) {
    expiryDate.addEventListener('input', function(e) {
      let value = this.value.replace(/\D/g, '');

      if (value.length >= 2) {
        value = value.slice(0, 2) + '/' + value.slice(2, 4);
      }

      this.value = value;
    });
  }

  if (cvv) {
    cvv.addEventListener('input', function(e) {
      this.value = this.value.replace(/\D/g, '').slice(0, 4);
    });
  }
}

/**
 * Load saved payment methods from Stripe (via account API) and render them
 * in the saved-cards section of the payment step.
 * Called at DOMContentLoaded so cards are usually ready before the user
 * reaches step 2.
 */
function loadSavedPaymentMethods() {
  fetch('/account/api/payment-methods')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success && data.payment_methods && data.payment_methods.length > 0) {
        _renderSavedCards(data.payment_methods);
      }
    })
    .catch(function(err) { console.error('[PM] Error loading payment methods:', err); });
}

/**
 * Render saved card rows into #saved-cards-list and activate the section.
 * Selects the default card (or first card) automatically.
 */
function _renderSavedCards(cards) {
  var section = document.getElementById('saved-cards-section');
  var list    = document.getElementById('saved-cards-list');
  if (!section || !list) return;

  // Cache display info for use in review step
  cards.forEach(function(card) {
    _savedCardInfo[card.id] = {
      brand: card.brand,
      last4: card.last4,
      exp_month: card.exp_month,
      exp_year: card.exp_year,
    };
  });

  list.innerHTML = cards.map(function(card) {
    var icon = getCardIcon(card.brand);
    var exp  = String(card.exp_month).padStart(2, '0') + '/' + String(card.exp_year).slice(-2);
    var badge = card.is_default
      ? '<span class="co-pm-default-badge">Default</span>'
      : '';
    return [
      '<div class="co-pm-row" id="co-pm-' + card.id + '"',
      '     onclick="selectCheckoutSavedCard(\'' + card.id + '\')" role="button" tabindex="0">',
      '  <div class="co-pm-radio">',
      '    <input type="radio" name="checkout_pm" value="' + card.id + '"',
      '      onclick="event.stopPropagation(); selectCheckoutSavedCard(\'' + card.id + '\')">',
      '  </div>',
      '  <div class="co-pm-info">',
      '    <span class="co-pm-icon"><i class="' + icon + '"></i></span>',
      '    <div>',
      '      <div class="co-pm-name">' + capitalizeFirst(card.brand) + ' •••• ' + card.last4 + badge + '</div>',
      '      <div class="co-pm-exp">Expires ' + exp + '</div>',
      '    </div>',
      '  </div>',
      '</div>',
    ].join('\n');
  }).join('\n');

  // Show saved-cards section; hide Payment Element (not needed for saved cards)
  section.style.display = 'block';
  var stripeSection = document.getElementById('stripe-element-section');
  if (stripeSection) stripeSection.style.display = 'none';

  // Auto-select default card, or first card
  var defaultCard = cards.find(function(c) { return c.is_default; }) || cards[0];
  selectCheckoutSavedCard(defaultCard.id);
}

/**
 * Select a saved card as the payment method for this checkout.
 */
function selectCheckoutSavedCard(pmId) {
  _selectedSavedPmId = pmId;

  // Sync radio buttons
  document.querySelectorAll('input[name="checkout_pm"]').forEach(function(r) {
    r.checked = (r.value === pmId);
  });

  // Highlight selected row, clear others
  document.querySelectorAll('.co-pm-row').forEach(function(row) {
    row.classList.toggle('co-pm-row-selected', row.id === 'co-pm-' + pmId);
  });

  // Hide Payment Element (saved card needs no re-entry)
  var stripeSection = document.getElementById('stripe-element-section');
  if (stripeSection) stripeSection.style.display = 'none';

  // Show fee badge — always shows both options
  var feeBadge = document.getElementById('payment-fee-badge');
  if (feeBadge) {
    feeBadge.style.display = 'block';
    feeBadge.style.background = '';
    feeBadge.style.color = '';
    feeBadge.style.border = '';
    feeBadge.innerHTML =
      '<span style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">' +
        '<i class="fa-solid fa-circle-info" style="color:#6b7280;"></i>' +
        '<span style="color:#374151;">Card payment &mdash; <strong>2.99% processing fee</strong></span>' +
      '</span>' +
      '<span style="display:flex;align-items:center;gap:6px;background:#ecfdf5;color:#065f46;border:1px solid #6ee7b7;border-radius:5px;padding:4px 8px;">' +
        '<i class="fa-solid fa-circle-check" style="color:#10b981;"></i>' +
        '<span>ACH Bank Transfer &mdash; <strong>Free</strong></span>' +
      '</span>';
  }
  _stripeSelectedMethod = 'card';
  updateOrderSummary();
}
window.selectCheckoutSavedCard = selectCheckoutSavedCard;

/**
 * Switch to "new card" mode — show and initialize the Stripe Payment Element.
 */
function selectCheckoutNewCard() {
  _selectedSavedPmId = null;

  var radio = document.getElementById('radio-new-card');
  if (radio) radio.checked = true;

  // Highlight the new-card row
  document.querySelectorAll('.co-pm-row').forEach(function(row) {
    row.classList.toggle('co-pm-row-selected', row.id === 'co-new-card-row');
  });

  // Show the Stripe Payment Element section
  var stripeSection = document.getElementById('stripe-element-section');
  if (stripeSection) stripeSection.style.display = 'block';

  // Mount the element if we have credentials but haven't mounted yet
  if (_stripe && _clientSecret && !_paymentElementMounted) {
    _mountPaymentElement();
  } else if (!_stripeInitStarted) {
    // Step 2 was not yet entered — init will handle mounting
    initStripeElements();
  }
}
window.selectCheckoutNewCard = selectCheckoutNewCard;

/**
 * Get Font Awesome icon for card type
 */
function getCardIcon(cardType) {
  const icons = {
    'visa': 'fa-brands fa-cc-visa',
    'mastercard': 'fa-brands fa-cc-mastercard',
    'amex': 'fa-brands fa-cc-amex',
    'discover': 'fa-brands fa-cc-discover',
    'unknown': 'fa-solid fa-credit-card'
  };
  return icons[cardType] || icons['unknown'];
}

/**
 * Capitalize first letter
 */
function capitalizeFirst(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Reinitialize payment selection after adding saved cards
 */
function reinitPaymentSelection() {
  const paymentOptions = document.querySelectorAll('.payment-option');
  const cardForm = document.getElementById('cardForm');
  const achForm = document.getElementById('achForm');

  paymentOptions.forEach(option => {
    // Remove existing listeners by cloning
    const newOption = option.cloneNode(true);
    option.parentNode.replaceChild(newOption, option);

    newOption.addEventListener('click', function() {
      // Update selected state
      document.querySelectorAll('.payment-option').forEach(o => o.classList.remove('selected'));
      this.classList.add('selected');

      // Check the radio
      const radio = this.querySelector('input[type="radio"]');
      radio.checked = true;

      // Show/hide appropriate form
      const method = radio.value;

      // Hide all forms by default
      if (cardForm) cardForm.style.display = 'none';
      if (achForm) achForm.style.display = 'none';

      // Show the appropriate form
      if (method === 'card') {
        if (cardForm) cardForm.style.display = 'block';
      } else if (method === 'ach') {
        if (achForm) achForm.style.display = 'block';
      }
      // Saved cards don't need a form

      // Recalculate order summary totals
      updateOrderSummary();
    });
  });
}

/**
 * Save card to user's account
 */
function saveCardToAccount() {
  const cardNumber = document.getElementById('cardNumber').value;
  const cardholderName = document.getElementById('cardholderName').value;
  const expiryDate = document.getElementById('expiryDate').value;

  return fetch('/account/api/payment-methods', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      card_number: cardNumber,
      cardholder_name: cardholderName,
      expiry_date: expiryDate
    })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      console.log('Card saved successfully:', data);
    } else {
      console.error('Failed to save card:', data.error);
    }
    return data;
  })
  .catch(err => {
    console.error('Error saving card:', err);
    return { success: false };
  });
}

/**
 * Gather shipping address from form fields and return formatted string + parts.
 */
function _gatherShippingInfo() {
  const firstName = document.getElementById('firstName').value;
  const lastName  = document.getElementById('lastName').value;
  const street    = document.getElementById('streetAddress').value;
  const apartment = document.getElementById('apartment').value;
  const city      = document.getElementById('city').value;
  const state     = document.getElementById('state').value;
  const zipCode   = document.getElementById('zipCode').value;
  const country   = document.getElementById('country').value;
  const email     = document.getElementById('email').value;
  const phone     = document.getElementById('phone').value;

  let addressParts = [`${firstName} ${lastName}`, street];
  if (apartment) addressParts.push(apartment);
  addressParts.push(`${city}, ${state} ${zipCode}`);
  if (country && country !== 'United States') addressParts.push(country);
  addressParts.push(`Email: ${email}`, `Phone: ${phone}`);

  return {
    shippingAddress: addressParts.join(' • '),
    firstName,
    lastName,
  };
}

/**
 * Place the order via AJAX, then confirm payment with Stripe.
 *
 * Phase 1: POST /checkout (creates order record, decrements inventory)
 * Phase 2: stripe.confirmPayment() — charges the card
 *          On success (no 3DS): redirect to /order-success
 *          On redirect (3DS):   Stripe handles redirect to /order-success
 * On SPOT_EXPIRED: show recalculate modal.
 */
async function placeOrder() {
  const btn = document.getElementById('placeOrderBtn');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';

  // Always show errors in the step-3 error div (visible at review step).
  const _showError = (msg) => {
    const div = document.getElementById('step3-error');
    if (div) { div.textContent = msg; div.style.display = 'block'; }
    else { alert(msg); }
  };
  const _clearError = () => {
    const div = document.getElementById('step3-error');
    if (div) { div.style.display = 'none'; div.textContent = ''; }
  };
  const _resetBtn = () => {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-lock"></i> Place Order • <span id="place-order-total">' +
      document.getElementById('place-order-total').textContent + '</span>';
  };

  _clearError();

  if (!_stripe) {
    _showError('Payment system not ready. Please wait a moment and try again.');
    _resetBtn();
    return;
  }
  if (!_selectedSavedPmId && !_stripeElements) {
    _showError('Payment form is still loading. Please wait a moment and try again.');
    _resetBtn();
    return;
  }
  if (!_clientSecret) {
    _showError('Payment system is still initializing. Please wait a moment and try again.');
    _resetBtn();
    return;
  }

  try {
    const { shippingAddress, firstName, lastName } = _gatherShippingInfo();

    // Phase 1: Create the order record in our DB.
    // We include the payment_intent_id so the server stores it on the order immediately —
    // this lets /order-success find the order by PI ID without needing metadata stamping.
    const response = await fetch('/checkout', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({
        shipping_address: shippingAddress,
        payment_method: 'card',
        recipient_first: firstName,
        recipient_last: lastName,
        checkout_nonce: window.checkoutNonce,
        payment_intent_id: _stripePaymentIntentId,
      }),
    });

    if (!response.ok && response.status !== 409) {
      const text = await response.text();
      console.error('[placeOrder] /checkout HTTP error', response.status, text);
      _showError('Server error processing your order (HTTP ' + response.status + '). Please try again.');
      _resetBtn();
      return;
    }

    const data = await response.json();

    if (!data.success) {
      if (data.error_code === 'SPOT_EXPIRED') {
        showSpotExpiredModal();
      } else if (data.error_code === 'SPOT_UNAVAILABLE') {
        _showError(data.message || 'Live pricing temporarily unavailable. Please try again in a moment.');
      } else {
        _showError(data.message || 'Error processing order. Please try again.');
      }
      _resetBtn();
      return;
    }

    // Phase 1 succeeded — order created. Now confirm payment with Stripe.
    console.log('[placeOrder] Phase 1 complete, order_id=' + data.order_id + '. Confirming payment...');

    // Phase 2: Confirm payment with Stripe.
    let confirmResult;
    try {
      if (_selectedSavedPmId) {
        confirmResult = await _stripe.confirmPayment({
          clientSecret: _clientSecret,
          confirmParams: {
            payment_method: _selectedSavedPmId,
            return_url: window.location.origin + '/order-success',
          },
          redirect: 'if_required',
        });
      } else {
        confirmResult = await _stripe.confirmPayment({
          elements: _stripeElements,
          confirmParams: {
            return_url: window.location.origin + '/order-success',
          },
          redirect: 'if_required',
        });
      }
    } catch (stripeErr) {
      // Stripe SDK threw (network error, etc.). Order exists — go to success page
      // and let the webhook confirm payment status asynchronously.
      console.error('[placeOrder] stripe.confirmPayment threw:', stripeErr);
      window.location.href = '/order-success?payment_intent=' + (_stripePaymentIntentId || '');
      return;
    }

    const { error, paymentIntent } = confirmResult;

    if (error) {
      console.error('[Stripe] confirmPayment error:', error);

      // Transient errors: network blip or internal Stripe error. The order was already
      // created in Phase 1 and the payment may have reached Stripe before the error.
      // Navigate to /order-success and let the webhook determine the real outcome
      // rather than incorrectly telling the user the payment failed.
      if (error.type === 'api_connection_error' || error.type === 'api_error') {
        console.warn('[placeOrder] Transient Stripe error (' + error.type + ') — order exists, navigating to order-success');
        window.location.href = '/order-success?payment_intent=' + (_stripePaymentIntentId || '');
        return;
      }

      // Definitive errors (card declined, 3DS auth failure, validation, etc.) — show and allow retry.
      const errMsg = error.message || 'Payment failed. Please check your payment details and try again.';
      const errDiv = document.getElementById('step3-error');
      if (errDiv) {
        errDiv.innerHTML = '';
        const msgSpan = document.createElement('span');
        msgSpan.textContent = errMsg;
        errDiv.appendChild(msgSpan);
        // If a saved card was used, offer a quick link to go back and change it.
        if (_selectedSavedPmId) {
          errDiv.appendChild(document.createTextNode(' '));
          const link = document.createElement('a');
          link.href = 'javascript:void(0)';
          link.textContent = 'Change payment method';
          link.style.cssText = 'color:#1f2937;font-weight:600;text-decoration:underline;';
          link.addEventListener('click', function() { goToStep(2); });
          errDiv.appendChild(link);
        }
        errDiv.style.display = 'block';
      } else {
        alert(errMsg);
      }
      _resetBtn();
      return;
    }

    // Payment confirmed — navigate to the confirmation page.
    console.log('[placeOrder] Payment confirmed, pi=' + paymentIntent.id + ' status=' + paymentIntent.status);
    window.location.href = '/order-success?payment_intent=' + paymentIntent.id;

  } catch (err) {
    console.error('[placeOrder] unexpected error:', err);
    _showError('An unexpected error occurred. Please refresh the page and try again.');
    _resetBtn();
  }
}
window.placeOrder = placeOrder;

// ---------------------------------------------------------------------------
// Spot-expired modal
// ---------------------------------------------------------------------------

function showSpotExpiredModal() {
  const modal = document.getElementById('spotExpiredModal');
  if (modal) modal.style.display = 'flex';
}
window.showSpotExpiredModal = showSpotExpiredModal;

function closeSpotExpiredModal() {
  const modal = document.getElementById('spotExpiredModal');
  if (modal) modal.style.display = 'none';
}
window.closeSpotExpiredModal = closeSpotExpiredModal;

// ---------------------------------------------------------------------------
// Checkout form draft — save/restore across spot-price page reload
// ---------------------------------------------------------------------------

const _CHECKOUT_DRAFT_KEY = 'checkoutFormDraft';

function _saveCheckoutDraft() {
  const v = id => { const el = document.getElementById(id); return el ? el.value : ''; };
  const radio = name => {
    const el = document.querySelector(`input[name="${name}"]:checked`);
    return el ? el.value : '';
  };
  const chk = id => { const el = document.getElementById(id); return el ? el.checked : false; };

  sessionStorage.setItem(_CHECKOUT_DRAFT_KEY, JSON.stringify({
    step:           currentStep,
    firstName:      v('firstName'),
    lastName:       v('lastName'),
    email:          v('email'),
    phone:          v('phone'),
    streetAddress:  v('streetAddress'),
    apartment:      v('apartment'),
    city:           v('city'),
    state:          v('state'),
    zipCode:        v('zipCode'),
    paymentMethod:  radio('payment_method'),
    cardNumber:     v('cardNumber'),
    cardholderName: v('cardholderName'),
    expiryDate:     v('expiryDate'),
    routingNumber:  v('routingNumber'),
    accountNumber:  v('accountNumber'),
    accountType:    v('accountType'),
    saveCard:       chk('saveCard'),
  }));
}

function _restoreCheckoutDraft() {
  const raw = sessionStorage.getItem(_CHECKOUT_DRAFT_KEY);
  if (!raw) return;
  sessionStorage.removeItem(_CHECKOUT_DRAFT_KEY);

  let d;
  try { d = JSON.parse(raw); } catch (e) { return; }

  const set = (id, val) => { const el = document.getElementById(id); if (el && val) el.value = val; };

  set('firstName',      d.firstName);
  set('lastName',       d.lastName);
  set('email',          d.email);
  set('phone',          d.phone);
  set('streetAddress',  d.streetAddress);
  set('apartment',      d.apartment);
  set('city',           d.city);
  set('state',          d.state);
  set('zipCode',        d.zipCode);
  set('cardNumber',     d.cardNumber);
  set('cardholderName', d.cardholderName);
  set('expiryDate',     d.expiryDate);
  set('routingNumber',  d.routingNumber);
  set('accountNumber',  d.accountNumber);
  set('accountType',    d.accountType);

  if (d.saveCard !== undefined) {
    const el = document.getElementById('saveCard');
    if (el) el.checked = d.saveCard;
  }

  // Restore payment method — click the wrapper div so show/hide and fee update run
  if (d.paymentMethod) {
    const radio = document.querySelector(`input[name="payment_method"][value="${d.paymentMethod}"]`);
    if (radio) {
      const option = radio.closest('.payment-option');
      if (option) option.click();
      else radio.checked = true;
    }
  }

  // Restore the step the user was on
  if (d.step && d.step > 1) {
    _goToStepDirect(d.step);
  }

  _showSpotUpdatedToast('Prices refreshed with latest spot rate');
}

function _goToStepDirect(step) {
  updateProgress(step);
  document.querySelectorAll('.checkout-step').forEach(s => s.classList.remove('active'));
  const stepIds = ['step-shipping', 'step-payment', 'step-review'];
  const target = document.getElementById(stepIds[step - 1]);
  if (target) target.classList.add('active');
  currentStep = step;
  if (step === 3) populateReviewData();
}

/**
 * Save form state, then reload the page so the server re-renders prices
 * using the latest spot snapshot. _restoreCheckoutDraft() on DOMContentLoaded
 * puts everything back where the user left off.
 */
function recalculateSpot() {
  const btn = document.getElementById('recalcBtn');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Updating...';
  _saveCheckoutDraft();
  location.reload();
}
window.recalculateSpot = recalculateSpot;

function _showSpotUpdatedToast(msg) {
  const toast = document.getElementById('spotUpdatedToast');
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add('visible');
  setTimeout(() => toast.classList.remove('visible'), 3500);
}
