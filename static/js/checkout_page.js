// static/js/checkout_page.js
// Checkout page functionality - 3-step checkout flow

document.addEventListener('DOMContentLoaded', function() {
  initSavedAddresses();
  initPaymentMethodSelection();
  initCardFormatting();
  loadUserInfo();
  loadSavedPaymentMethods();
  updateOrderSummary();
  _restoreCheckoutDraft();
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
 * Validate payment form
 */
function validatePaymentForm() {
  const paymentMethod = document.querySelector('input[name="payment_method"]:checked').value;

  // Saved cards don't need validation
  if (paymentMethod.startsWith('saved_card_')) {
    return true;
  }

  if (paymentMethod === 'card') {
    const cardNumber = document.getElementById('cardNumber');
    const cardholderName = document.getElementById('cardholderName');
    const expiryDate = document.getElementById('expiryDate');
    const cvv = document.getElementById('cvv');

    let isValid = true;

    if (!cardNumber.value.replace(/\s/g, '').match(/^\d{13,19}$/)) {
      cardNumber.style.borderColor = '#ef4444';
      isValid = false;
    } else {
      cardNumber.style.borderColor = '#e5e7eb';
    }

    if (!cardholderName.value.trim()) {
      cardholderName.style.borderColor = '#ef4444';
      isValid = false;
    } else {
      cardholderName.style.borderColor = '#e5e7eb';
    }

    if (!expiryDate.value.match(/^\d{2}\/\d{2}$/)) {
      expiryDate.style.borderColor = '#ef4444';
      isValid = false;
    } else {
      expiryDate.style.borderColor = '#e5e7eb';
    }

    if (!cvv.value.match(/^\d{3,4}$/)) {
      cvv.style.borderColor = '#ef4444';
      isValid = false;
    } else {
      cvv.style.borderColor = '#e5e7eb';
    }

    if (!isValid) {
      alert('Please fill in all payment details correctly.');
    }

    return isValid;
  } else if (paymentMethod === 'ach') {
    const routingNumber = document.getElementById('routingNumber');
    const accountNumber = document.getElementById('accountNumber');

    let isValid = true;

    if (!routingNumber.value.match(/^\d{9}$/)) {
      routingNumber.style.borderColor = '#ef4444';
      isValid = false;
    } else {
      routingNumber.style.borderColor = '#e5e7eb';
    }

    if (!accountNumber.value.trim()) {
      accountNumber.style.borderColor = '#ef4444';
      isValid = false;
    } else {
      accountNumber.style.borderColor = '#e5e7eb';
    }

    if (!isValid) {
      alert('Please fill in all bank details correctly.');
    }

    return isValid;
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
  const paymentMethod = document.querySelector('input[name="payment_method"]:checked').value;
  const paymentDisplay = document.getElementById('paymentDisplay');

  if (paymentMethod.startsWith('saved_card_')) {
    // Get saved card details from the selected option
    const selectedOption = document.querySelector(`input[value="${paymentMethod}"]`)?.closest('.payment-option');
    const cardName = selectedOption?.querySelector('.payment-name')?.textContent || 'Saved Card';
    const cardIcon = selectedOption?.querySelector('.payment-icon i')?.className || 'fa-solid fa-credit-card';
    paymentDisplay.innerHTML = `<i class="${cardIcon}"></i> <span>${cardName}</span>`;
  } else if (paymentMethod === 'card') {
    const cardNumber = document.getElementById('cardNumber').value.replace(/\s/g, '');
    const lastFour = cardNumber.slice(-4);
    paymentDisplay.innerHTML = `<i class="fa-solid fa-credit-card"></i> <span>Card ending in ****${lastFour}</span>`;
  } else if (paymentMethod === 'ach') {
    paymentDisplay.innerHTML = `<i class="fa-solid fa-building-columns"></i> <span>Bank Transfer (ACH)</span>`;
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
  const isACH = method === 'ach';

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
 * Load saved payment methods
 */
function loadSavedPaymentMethods() {
  fetch('/account/api/payment-methods')
    .then(response => response.json())
    .then(data => {
      if (data.success && data.payment_methods && data.payment_methods.length > 0) {
        displaySavedCards(data.payment_methods);
      }
    })
    .catch(err => console.error('Error loading payment methods:', err));
}

/**
 * Display saved cards in the payment options
 */
function displaySavedCards(cards) {
  const paymentOptions = document.querySelector('.payment-options');
  if (!paymentOptions) return;

  // Find the card payment option
  const cardOption = paymentOptions.querySelector('input[value="card"]')?.closest('.payment-option');
  if (!cardOption) return;

  // Create saved cards section
  const savedCardsHtml = cards.map((card, index) => {
    const cardIcon = getCardIcon(card.card_type);
    const expiry = `${String(card.expiry_month).padStart(2, '0')}/${String(card.expiry_year).slice(-2)}`;
    const isDefault = card.is_default ? ' (Default)' : '';

    return `
      <label class="payment-option saved-card-option" data-card-id="${card.id}">
        <input type="radio" name="payment_method" value="saved_card_${card.id}">
        <div class="payment-option-content">
          <div class="payment-icon">
            <i class="${cardIcon}"></i>
          </div>
          <div class="payment-details">
            <span class="payment-name">${capitalizeFirst(card.card_type)} •••• ${card.last_four}${isDefault}</span>
            <span class="payment-subtitle">Expires ${expiry}</span>
          </div>
        </div>
        <div class="payment-check">
          <i class="fa-solid fa-circle-check"></i>
        </div>
      </label>
    `;
  }).join('');

  // Insert saved cards before the "new card" option
  cardOption.insertAdjacentHTML('beforebegin', savedCardsHtml);

  // Update the card option label to indicate it's for a new card
  const cardNameSpan = cardOption.querySelector('.payment-name');
  if (cardNameSpan) {
    cardNameSpan.textContent = 'Add New Card';
  }

  // Reinitialize payment selection to include saved cards
  reinitPaymentSelection();

  // Select the default card if there is one
  const defaultCard = cards.find(c => c.is_default);
  if (defaultCard) {
    const defaultOption = document.querySelector(`input[value="saved_card_${defaultCard.id}"]`);
    if (defaultOption) {
      defaultOption.click();
    }
  }
}

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
 * Place the order via AJAX.
 * On success: redirect to confirmation page.
 * On SPOT_EXPIRED: show recalculate modal.
 * On SPOT_UNAVAILABLE / other error: show alert.
 */
async function placeOrder() {
  const btn = document.getElementById('placeOrderBtn');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';

  try {
    const saveCardCheckbox = document.getElementById('saveCard');
    const paymentMethod = document.querySelector('input[name="payment_method"]:checked').value;

    if (saveCardCheckbox && saveCardCheckbox.checked && paymentMethod === 'card') {
      await saveCardToAccount();
    }

    const { shippingAddress, firstName, lastName } = _gatherShippingInfo();

    const response = await fetch('/checkout', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({
        shipping_address: shippingAddress,
        payment_method: paymentMethod,
        recipient_first: firstName,
        recipient_last: lastName,
        checkout_nonce: window.checkoutNonce,
      }),
    });

    const data = await response.json();

    if (data.success) {
      window.location.href = `/checkout/confirm/${data.order_id}`;
      return; // keep button disabled during redirect
    }

    if (data.error_code === 'SPOT_EXPIRED') {
      showSpotExpiredModal();
    } else if (data.error_code === 'SPOT_UNAVAILABLE') {
      alert(data.message || 'Live pricing temporarily unavailable. Please try again in a moment.');
    } else {
      alert(data.message || 'Error processing order. Please try again.');
    }
  } catch (err) {
    console.error('[placeOrder] network error:', err);
    alert('Network error. Please check your connection and try again.');
  }

  // Re-enable button on any non-redirect outcome
  btn.disabled = false;
  btn.innerHTML = '<i class="fa-solid fa-lock"></i> Place Order • <span id="place-order-total">' +
    document.getElementById('place-order-total').textContent + '</span>';
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
