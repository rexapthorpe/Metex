// static/js/checkout_page.js
// Checkout page functionality - 3-step checkout flow

document.addEventListener('DOMContentLoaded', function() {
  initSavedAddresses();
  initPaymentMethodSelection();
  initCardFormatting();
  loadUserInfo();
  loadSavedPaymentMethods();
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
 * Place the order
 */
async function placeOrder() {
  const btn = document.getElementById('placeOrderBtn');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';

  // Check if save card checkbox is checked
  const saveCardCheckbox = document.getElementById('saveCard');
  const paymentMethod = document.querySelector('input[name="payment_method"]:checked').value;

  // Save card if checkbox is checked and using new card
  if (saveCardCheckbox && saveCardCheckbox.checked && paymentMethod === 'card') {
    await saveCardToAccount();
  }

  // Gather shipping address
  const firstName = document.getElementById('firstName').value;
  const lastName = document.getElementById('lastName').value;
  const street = document.getElementById('streetAddress').value;
  const apartment = document.getElementById('apartment').value;
  const city = document.getElementById('city').value;
  const state = document.getElementById('state').value;
  const zipCode = document.getElementById('zipCode').value;
  const country = document.getElementById('country').value;
  const email = document.getElementById('email').value;
  const phone = document.getElementById('phone').value;

  // Format shipping address
  let addressParts = [`${firstName} ${lastName}`, street];
  if (apartment) addressParts.push(apartment);
  addressParts.push(`${city}, ${state} ${zipCode}`);
  if (country && country !== 'United States') addressParts.push(country);
  addressParts.push(`Email: ${email}`, `Phone: ${phone}`);

  const shippingAddress = addressParts.join(' • ');

  // Set hidden form values
  document.getElementById('shippingAddressInput').value = shippingAddress;
  document.getElementById('paymentMethodInput').value = paymentMethod;
  document.getElementById('recipientFirstName').value = firstName;
  document.getElementById('recipientLastName').value = lastName;

  // Submit the form
  document.getElementById('orderForm').submit();
}
window.placeOrder = placeOrder;
