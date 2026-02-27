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
  'quantity': 'Quantity',
  'price_per_coin': 'Price Per Coin',
  'spot_premium': 'Premium above spot',
  'floor_price': '"No lower than" price',
  'item_photo_1': 'Item Photo',
  'cover_photo': 'Cover Photo'
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

  // Belt-and-suspenders: check both the runtime flag AND the hidden form input
  const isSetHidden = document.getElementById('isSetHidden');
  const isSetMode = window.currentMode === 'set' || (isSetHidden && isSetHidden.value === '1');
  const isIsolatedHidden = document.getElementById('isIsolatedHidden');
  const isIsolatedMode = window.currentMode === 'isolated' ||
    (!isSetMode && isIsolatedHidden && isIsolatedHidden.value === '1');
  const capturedSetItems = window.setItems || [];

  // STRICT MODE GATE: Set mode requires 2+ items — no other errors shown until this passes
  if (isSetMode && capturedSetItems.length < 2) {
    return { isValid: false, errors: ['Add at least 2 items to publish this set.'] };
  }

  const staticRadio = form.querySelector('#pricing_mode_static');
  const premiumRadio = form.querySelector('#pricing_mode_premium');

  let requiredFields;

  if (isSetMode) {
    // 2+ items (gate passed above): spec fields belong to in-progress item, not required
    requiredFields = [];
  } else {
    requiredFields = [
      'metal', 'product_line', 'product_type', 'weight',
      'purity', 'mint', 'year', 'finish'
    ];
    if (!isIsolatedMode) {
      requiredFields.push('quantity');
    }
  }

  // Pricing always required
  if (staticRadio && staticRadio.checked) {
    requiredFields.push('price_per_coin');
  } else if (premiumRadio && premiumRadio.checked) {
    requiredFields.push('spot_premium');
    requiredFields.push('floor_price');
  } else {
    requiredFields.push('price_per_coin');
  }

  const result = validateForm(form, requiredFields);

  // Cover photo required for set mode
  // Three signals: new file selected, has-image class (UI state), or existingPhotoId dataset
  // attribute (set during edit-mode prefill, cleared only when user explicitly removes photo).
  if (isSetMode) {
    const coverInput = form.elements['cover_photo'];
    const coverBox = document.getElementById('coverPhotoUploadBox');
    const hasCoverPhoto =
      (coverInput && coverInput.files && coverInput.files.length > 0) ||
      (coverBox && coverBox.classList.contains('has-image')) ||
      (coverBox && coverBox.dataset.existingPhotoId);
    if (!hasCoverPhoto) {
      result.errors.push('Cover Photo is required');
      result.isValid = false;
    }
  }

  // Item photo required for standard/isolated modes (any slot counts)
  if (!isSetMode) {
    const p1 = form.elements['item_photo_1'];
    const p2 = form.elements['item_photo_2'];
    const p3 = form.elements['item_photo_3'];
    const b1 = document.getElementById('standardPhotoBox1');
    const b2 = document.getElementById('standardPhotoBox2');
    const b3 = document.getElementById('standardPhotoBox3');
    const hasPhoto =
      (p1 && p1.files && p1.files.length > 0) ||
      (p2 && p2.files && p2.files.length > 0) ||
      (p3 && p3.files && p3.files.length > 0) ||
      (b1 && b1.classList.contains('has-image')) ||
      (b2 && b2.classList.contains('has-image')) ||
      (b3 && b3.classList.contains('has-image'));
    if (!hasPhoto) {
      result.errors.push('Item Photo is required');
      result.isValid = false;
    }
  }

  return result;
}

/**
 * Validate edit listing form
 * @param {HTMLFormElement} form - The form to validate
 * @returns {Object} Validation result {isValid: boolean, errors: string[]}
 */
function validateEditListingForm(form) {
  if (!form) return { isValid: true, errors: [] };

  // Belt-and-suspenders: check both the runtime flag AND the hidden form input
  const isSetHiddenEl = document.getElementById('isSetHidden');
  const isSetMode = window.currentMode === 'set' || (isSetHiddenEl && isSetHiddenEl.value === '1');
  const isIsolatedHiddenEl = document.getElementById('isIsolatedHidden');
  const isIsolatedMode = window.currentMode === 'isolated' ||
    (!isSetMode && isIsolatedHiddenEl && isIsolatedHiddenEl.value === '1');
  const capturedSetItems = window.setItems || [];

  // STRICT MODE GATE: Set mode requires 2+ items — no other errors shown until this passes
  if (isSetMode && capturedSetItems.length < 2) {
    return { isValid: false, errors: ['Add at least 2 items to publish this set.'] };
  }

  // Determine pricing mode from the form (works for both radio buttons and select)
  const pricingModeEl = form.elements['pricing_mode'];
  const pricingMode = pricingModeEl ? pricingModeEl.value : 'static';

  let requiredFields;

  if (isSetMode) {
    // 2+ items (gate passed above): spec fields are for the in-progress item, not required
    requiredFields = [];
  } else {
    // Standard, isolated, or set with <2 items: validate all spec fields
    requiredFields = [
      'metal', 'product_line', 'product_type', 'weight',
      'purity', 'mint', 'year', 'finish'
    ];
    // Quantity only required for standard mode
    if (!isSetMode && !isIsolatedMode) {
      requiredFields.push('quantity');
    }
  }

  // Add pricing-mode-specific required fields
  if (pricingMode === 'premium_to_spot') {
    requiredFields.push('spot_premium');
    requiredFields.push('floor_price');
  } else {
    requiredFields.push('price_per_coin');
  }

  const result = validateForm(form, requiredFields);

  // Cover photo required for set mode
  // Three signals: new file selected, has-image class (UI state), or existingPhotoId dataset
  // attribute (set during edit-mode prefill, cleared only when user explicitly removes photo).
  if (isSetMode) {
    const coverInput = form.elements['cover_photo'];
    const coverBox = document.getElementById('coverPhotoUploadBox');
    const hasCoverPhoto =
      (coverInput && coverInput.files && coverInput.files.length > 0) ||
      (coverBox && coverBox.classList.contains('has-image')) ||
      (coverBox && coverBox.dataset.existingPhotoId);
    if (!hasCoverPhoto) {
      result.errors.push('Cover Photo is required');
      result.isValid = false;
    }
  }

  return result;
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
