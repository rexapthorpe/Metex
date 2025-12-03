// static/js/modals/field_validation_modal.js
'use strict';

/* ==========================================================================
   Field Validation Modal
   Shows user which required fields are missing
   ========================================================================== */

/**
 * Field labels mapping for user-friendly display
 */
const FIELD_LABELS = {
  'metal': 'Metal',
  'product_line': 'Product Line',
  'product_type': 'Product Type',
  'weight': 'Weight',
  'purity': 'Purity',
  'mint': 'Mint',
  'year': 'Year',
  'finish': 'Finish',
  'grade': 'Grade',
  'quantity': 'Quantity',
  'price_per_coin': 'Price Per Coin',
  'spot_premium': 'Premium above spot',
  'floor_price': '"No lower than" price',
  'item_photo': 'Item Photo'
};

/**
 * Show the field validation modal with validation errors
 * @param {string[]} errors - Array of error messages
 */
function showFieldValidationModal(errors) {
  const modal = document.getElementById('fieldValidationModal');
  if (!modal) return;

  const messageEl = document.getElementById('validationMessage');
  const listEl = document.getElementById('missingFieldsList');

  // Set message based on number of errors
  if (errors.length === 1) {
    messageEl.textContent = 'Please fix the following issue:';
  } else {
    messageEl.textContent = `Please fix the following ${errors.length} issues:`;
  }

  // Build error list
  listEl.innerHTML = '';
  errors.forEach(errorMsg => {
    const li = document.createElement('li');
    li.textContent = errorMsg;
    listEl.appendChild(li);
  });

  // Show modal with animation
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });
}

/**
 * Close the field validation modal
 */
function closeFieldValidationModal() {
  const modal = document.getElementById('fieldValidationModal');
  if (!modal) return;

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
  }, 300);
}

/**
 * Validate a form and return array of validation errors
 * @param {HTMLFormElement} form - The form to validate
 * @param {string[]} requiredFields - Array of required field names
 * @returns {Object} Object with {isValid: boolean, errors: string[]}
 */
function validateForm(form, requiredFields) {
  const errors = [];

  requiredFields.forEach(fieldName => {
    const field = form.elements[fieldName];

    if (!field) {
      return; // Field doesn't exist in this form
    }

    // Handle file inputs
    if (field.type === 'file') {
      if (!field.files || field.files.length === 0) {
        errors.push(`${FIELD_LABELS[fieldName] || fieldName} is required`);
      }
    }
    // Handle text/select inputs
    else {
      const value = (field.value || '').trim();

      // Check if empty
      if (!value || value === '') {
        errors.push(`${FIELD_LABELS[fieldName] || fieldName} is required`);
      }
      // Check if field has datalist validation
      else if (field.classList.contains('validated-datalist')) {
        const listId = field.dataset.listId;
        const listEl = document.getElementById(listId);

        if (listEl) {
          // Get allowed values from datalist
          const allowed = Array.from(listEl.options).map(opt => (opt.value || '').trim());

          // Check if value is in allowed list (case-sensitive)
          if (!allowed.includes(value)) {
            errors.push(`"${value}" is not a valid option for ${FIELD_LABELS[fieldName] || fieldName}. Please choose from the dropdown list.`);
          }
        }
      }
    }
  });

  return {
    isValid: errors.length === 0,
    errors: errors
  };
}

/**
 * Validate sell form
 * @param {HTMLFormElement} form - The form to validate
 * @returns {Object} Validation result {isValid: boolean, errors: string[]}
 */
function validateSellForm(form) {
  if (!form) return { isValid: true, errors: [] };

  // Base required fields (always required regardless of pricing mode)
  const baseRequiredFields = [
    'metal',
    'product_line',
    'product_type',
    'weight',
    'purity',
    'mint',
    'year',
    'finish',
    'grade',
    'quantity',
    'item_photo'
  ];

  // Determine pricing mode from the form
  const staticRadio = form.querySelector('#pricing_mode_static');
  const premiumRadio = form.querySelector('#pricing_mode_premium');

  let requiredFields = [...baseRequiredFields];

  // Add pricing-mode-specific required fields
  if (staticRadio && staticRadio.checked) {
    // Static mode: require Price Per Coin
    requiredFields.push('price_per_coin');
  } else if (premiumRadio && premiumRadio.checked) {
    // Premium-to-spot mode: require premium and floor
    requiredFields.push('spot_premium');
    requiredFields.push('floor_price');
  } else {
    // Default to static mode if no radio is explicitly checked
    requiredFields.push('price_per_coin');
  }

  return validateForm(form, requiredFields);
}

/**
 * Validate edit listing form
 * @param {HTMLFormElement} form - The form to validate
 * @returns {Object} Validation result {isValid: boolean, errors: string[]}
 */
function validateEditListingForm(form) {
  if (!form) return { isValid: true, errors: [] };

  // Base required fields (always required regardless of pricing mode)
  const baseRequiredFields = [
    'metal',
    'product_line',
    'product_type',
    'weight',
    'purity',
    'mint',
    'year',
    'finish',
    'grade',
    'quantity'
    // Note: photo is not required for editing
  ];

  // Determine pricing mode from the form
  const pricingModeSelect = form.elements['pricing_mode'];
  const pricingMode = pricingModeSelect ? pricingModeSelect.value : 'static';

  let requiredFields = [...baseRequiredFields];

  // Add pricing-mode-specific required fields
  if (pricingMode === 'premium_to_spot') {
    // Premium-to-spot mode: require premium and floor
    requiredFields.push('spot_premium');
    requiredFields.push('floor_price');
    // pricing_metal is auto-filled, not required from user
  } else {
    // Static mode: require Price Per Coin
    requiredFields.push('price_per_coin');
  }

  return validateForm(form, requiredFields);
}

/**
 * Initialize validation modal
 */
document.addEventListener('DOMContentLoaded', () => {
  // Close modal on overlay click
  const modal = document.getElementById('fieldValidationModal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        closeFieldValidationModal();
      }
    });
  }

  // Close modal on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeFieldValidationModal();
    }
  });
});

// Expose functions globally
window.showFieldValidationModal = showFieldValidationModal;
window.closeFieldValidationModal = closeFieldValidationModal;
window.validateForm = validateForm;
window.validateSellForm = validateSellForm;
window.validateEditListingForm = validateEditListingForm;
