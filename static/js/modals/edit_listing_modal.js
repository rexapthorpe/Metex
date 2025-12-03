/**
 * Set up the photo upload box functionality for a specific listing
 * Matches the Sell page photo upload behavior
 */
function setupPhotoUpload(listingId) {
  const photoBox = document.getElementById(`photoUploadBox-${listingId}`);
  const photoInput = document.getElementById(`photoUpload-${listingId}`);
  const photoPreview = document.getElementById(`photoPreview-${listingId}`);
  const clearBtn = document.getElementById(`photoClearBtn-${listingId}`);

  if (!photoBox || !photoInput || !photoPreview || !clearBtn) return;

  // If there's already a photo, add the has-image class and make photo optional
  if (photoPreview.style.display !== 'none') {
    photoBox.classList.add('has-image');
    // Photo exists, so uploading a new one is optional
    photoInput.required = false;
  } else {
    // No photo exists, so one must be uploaded
    photoInput.required = true;
  }

  // Click on box triggers file input (only when no image)
  photoBox.addEventListener('click', (e) => {
    // Don't open file chooser if clicking clear button
    if (e.target.closest('.photo-clear-btn')) {
      return;
    }
    // Only open file chooser if no image is currently displayed
    if (!photoBox.classList.contains('has-image')) {
      photoInput.click();
    }
  });

  // Handle file selection
  photoInput.addEventListener('change', (e) => {
    const file = e.target.files[0];

    if (file) {
      // Validate it's an image
      if (!file.type.startsWith('image/')) {
        alert('Please select an image file (JPG, PNG, etc.)');
        photoInput.value = '';
        return;
      }

      // Create preview
      const reader = new FileReader();
      reader.onload = (event) => {
        photoPreview.src = event.target.result;
        photoPreview.style.display = 'block';
        clearBtn.style.display = 'flex';
        photoBox.classList.add('has-image');
        photoInput.required = false; // Photo is now present
      };
      reader.readAsDataURL(file);
    } else {
      // No file selected, reset to default state
      clearImage();
    }
  });

  // Clear button functionality
  clearBtn.addEventListener('click', (e) => {
    e.stopPropagation(); // Prevent triggering photoBox click
    clearImage();
  });

  // Helper function to clear the image and reset to default state
  function clearImage() {
    photoPreview.style.display = 'none';
    photoPreview.src = '';
    clearBtn.style.display = 'none';
    photoBox.classList.remove('has-image');
    photoInput.value = ''; // Clear the file input
    photoInput.required = true; // Now a photo is required since there isn't one
  }
}

/**
 * Set up Price input formatting for a specific listing
 * - Format to always show exactly two decimal places
 * - Example: 10 → 10.00, 10.5 → 10.50, 10.123 → 10.12
 */
function setupPriceInput(listingId) {
  const priceInput = document.getElementById(`pricePerCoin-${listingId}`);
  if (!priceInput) return;

  // Format on blur (when user leaves the field)
  priceInput.addEventListener('blur', () => {
    formatPriceValue();
  });

  // Allow only numbers and decimal point during typing
  priceInput.addEventListener('input', (e) => {
    let value = e.target.value;

    // Remove any non-numeric characters except decimal point
    value = value.replace(/[^\d.]/g, '');

    // Allow only one decimal point
    const parts = value.split('.');
    if (parts.length > 2) {
      value = parts[0] + '.' + parts.slice(1).join('');
    }

    // Limit to 2 decimal places
    if (parts[1] && parts[1].length > 2) {
      value = parts[0] + '.' + parts[1].substring(0, 2);
    }

    e.target.value = value;
  });

  function formatPriceValue() {
    let value = priceInput.value.trim();

    if (value === '') {
      priceInput.value = '0.00';
      return;
    }

    // Parse the value as a float
    const numValue = parseFloat(value);

    // Check if it's a valid number
    if (!isNaN(numValue) && numValue >= 0) {
      // Format to exactly 2 decimal places
      priceInput.value = numValue.toFixed(2);
    } else {
      // Invalid input, set to 0.00
      priceInput.value = '0.00';
    }
  }
}

/**
 * Validate datalist inputs before form submission (matching sell.js)
 */
function validateDatalistInputs(form) {
  const inputs = form.querySelectorAll('.validated-datalist');

  for (const input of inputs) {
    const listId = input.dataset.listId;
    const listEl = document.getElementById(listId);
    if (!listEl) continue;

    const value = (input.value || '').trim();
    if (value === '') {
      alert(`Please select a value for "${input.name}".`);
      input.focus();
      return false;
    }

    const allowed = Array.from(listEl.options).map((opt) => (opt.value || '').trim());
    const isValid = allowed.includes(value); // exact match

    if (!isValid) {
      alert(`"${value}" is not a valid option for "${input.name}". Please choose from the dropdown list.`);
      input.focus();
      return false;
    }
  }

  return true; // all good
}

/**
 * Build a custom dropdown for an input, using the associated <datalist> options.
 * This replaces the browser's native datalist popup so we can control width/position.
 * (matching sell.js)
 */
function setupCustomDropdown(input) {
  const listId = input.dataset.listId;
  const dataList = document.getElementById(listId);
  if (!dataList) return;

  const options = Array.from(dataList.options)
    .map((opt) => (opt.value || '').trim())
    .filter((v) => v !== '');

  const wrapper = input.closest('.field-group') || input.parentElement;

  // Create the dropdown menu container
  const menu = document.createElement('div');
  menu.className = 'custom-dropdown-menu';
  wrapper.appendChild(menu);

  function hideMenu() {
    menu.style.display = 'none';
  }

  function showMenu() {
    if (menu.children.length > 0) {
      menu.style.display = 'block';
    } else {
      menu.style.display = 'none';
    }
  }

  function renderSuggestions(filterText) {
    const term = (filterText || '').toLowerCase();
    menu.innerHTML = '';

    const filtered = options.filter((value) => value.toLowerCase().includes(term));

    if (filtered.length === 0) {
      hideMenu();
      return;
    }

    filtered.forEach((value) => {
      const item = document.createElement('div');
      item.className = 'custom-dropdown-item';
      item.textContent = value;

      // Use mousedown so it fires before input loses focus
      item.addEventListener('mousedown', (e) => {
        e.preventDefault();
        input.value = value;
        hideMenu();
      });

      menu.appendChild(item);
    });

    showMenu();
  }

  // Show suggestions when the input gains focus
  input.addEventListener('focus', () => {
    renderSuggestions(input.value);
  });

  // Filter suggestions as user types
  input.addEventListener('input', () => {
    renderSuggestions(input.value);
  });

  // Hide menu shortly after blur (so clicks still register)
  input.addEventListener('blur', () => {
    setTimeout(hideMenu, 150);
  });

  // Optional: down-arrow to open menu when empty
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') {
      renderSuggestions(input.value);
      menu.focus?.();
    }
  });
}

/**
 * Set up pricing mode toggle (static vs premium-to-spot)
 */
function setupPricingModeToggle(listingId) {
  const pricingModeSelect = document.getElementById(`pricingMode-${listingId}`);
  const staticFields = document.getElementById(`staticPricingFields-${listingId}`);
  const premiumFields = document.getElementById(`premiumPricingFields-${listingId}`);
  const pricePerCoinInput = document.getElementById(`pricePerCoin-${listingId}`);
  const spotPremiumInput = document.getElementById(`spotPremium-${listingId}`);
  const floorPriceInput = document.getElementById(`floorPrice-${listingId}`);
  const pricingMetalInput = document.getElementById(`pricingMetal-${listingId}`);

  if (!pricingModeSelect) {
    console.warn('Pricing mode select not found for listing', listingId);
    return;
  }

  function togglePricingFields() {
    const mode = pricingModeSelect.value;
    console.log(`[Pricing Mode Toggle] Mode: ${mode}`);

    if (mode === 'static') {
      // Show static price field, hide premium fields
      if (staticFields) staticFields.style.display = 'block';
      if (premiumFields) premiumFields.style.display = 'none';

      // Make static field required, premium fields NOT required
      // Don't disable fields - just control with required attribute
      if (pricePerCoinInput) {
        pricePerCoinInput.required = true;
      }
      if (spotPremiumInput) {
        spotPremiumInput.required = false;
        spotPremiumInput.value = '0.00'; // Clear value when not in use
      }
      if (floorPriceInput) {
        floorPriceInput.required = false;
        floorPriceInput.value = '0.00'; // Clear value when not in use
      }
      if (pricingMetalInput) {
        pricingMetalInput.required = false;
      }
    } else {
      // Show premium fields, hide static price field
      if (staticFields) staticFields.style.display = 'none';
      if (premiumFields) premiumFields.style.display = 'block';

      // Make premium fields required, static field NOT required
      // Don't disable fields - just control with required attribute
      if (pricePerCoinInput) {
        pricePerCoinInput.required = false;
        pricePerCoinInput.value = '0.00'; // Clear value when not in use
      }
      if (spotPremiumInput) {
        spotPremiumInput.required = true;
      }
      if (floorPriceInput) {
        floorPriceInput.required = true;
      }
      if (pricingMetalInput) {
        pricingMetalInput.required = false;
      }
    }
  }

  // Set up event listener
  pricingModeSelect.addEventListener('change', togglePricingFields);

  // Initialize on page load
  togglePricingFields();

  // Set up input formatting for premium/floor fields
  if (spotPremiumInput) {
    setupNumericInput(spotPremiumInput);
  }
  if (floorPriceInput) {
    setupNumericInput(floorPriceInput);
  }
}

/**
 * Set up numeric input formatting (2 decimal places)
 */
function setupNumericInput(input) {
  if (!input) return;

  // Format on blur
  input.addEventListener('blur', () => {
    let value = input.value.trim();
    if (value === '') {
      input.value = '0.00';
      return;
    }
    const numValue = parseFloat(value);
    if (!isNaN(numValue) && numValue >= 0) {
      input.value = numValue.toFixed(2);
    } else {
      input.value = '0.00';
    }
  });

  // Allow only numbers and decimal point during typing
  input.addEventListener('input', (e) => {
    let value = e.target.value;
    value = value.replace(/[^\d.]/g, '');
    const parts = value.split('.');
    if (parts.length > 2) {
      value = parts[0] + '.' + parts.slice(1).join('');
    }
    if (parts[1] && parts[1].length > 2) {
      value = parts[0] + '.' + parts[1].substring(0, 2);
    }
    e.target.value = value;
  });
}

// 1) Remove any existing modal(s) to avoid stacking
// 2) Fetch & inject the HTML, wire up toggle & submit
function openEditListingModal(listingId) {
  console.log('=== openEditListingModal called for listing ID:', listingId, '===');

  // remove prior modals
  console.log('Removing any existing modals...');
  const existingModals = document.querySelectorAll('[id^="editListingModalWrapper-"]');
  console.log('Found', existingModals.length, 'existing modals to remove');
  existingModals.forEach((el) => el.remove());

  const fetchUrl = `/listings/edit_listing/${listingId}`;
  console.log('Fetching modal HTML from:', fetchUrl);

  fetch(fetchUrl, {
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then((r) => {
      console.log('✓ Fetch response received - Status:', r.status);
      if (!r.ok) {
        throw new Error(`HTTP error! status: ${r.status}`);
      }
      return r.text();
    })
    .then((html) => {
      console.log('✓ Modal HTML received, length:', html.length, 'characters');
      // inject
      const wrapper = document.createElement('div');
      wrapper.innerHTML = html;
      document.body.appendChild(wrapper);
      console.log('✓ Modal HTML injected into DOM');

      // 3) Wire up the grading toggle
      console.log('Setting up grading service toggle...');
      toggleGradingService(listingId);
      const gradedSel = document.getElementById(`gradedSelect-${listingId}`);
      if (gradedSel) {
        gradedSel.addEventListener('change', () => toggleGradingService(listingId));
        console.log('✓ Grading toggle wired up');
      } else {
        console.error('✗ Graded select not found!');
      }

      // 4) Set up custom dropdowns for all searchable fields (scoped to this modal)
      console.log('Setting up custom dropdowns...');
      const dropdownInputs = wrapper.querySelectorAll('.custom-dropdown-input');
      console.log('Found', dropdownInputs.length, 'dropdown inputs');
      dropdownInputs.forEach(setupCustomDropdown);
      console.log('✓ Custom dropdowns set up');

      // 4.5) Set up photo upload functionality
      console.log('Setting up photo upload...');
      setupPhotoUpload(listingId);
      console.log('✓ Photo upload set up');

      // 4.6) Set up price input formatting
      console.log('Setting up price input...');
      setupPriceInput(listingId);
      console.log('✓ Price input set up');

      // 4.7) Set up pricing mode toggle
      console.log('Setting up pricing mode toggle...');
      setupPricingModeToggle(listingId);
      console.log('✓ Pricing mode toggle set up');

      // 5) Handle submit via AJAX with validation
      const form = document.getElementById(`editListingForm-${listingId}`);

      if (!form) {
        console.error('CRITICAL ERROR: Form not found with ID:', `editListingForm-${listingId}`);
        alert('Error: Form element not found. Cannot set up submission handler.');
        return;
      }

      console.log('Setting up form submission handler for listing', listingId);

      form.addEventListener('submit', (e) => {
        // CRITICAL: Prevent default form submission at the very start
        e.preventDefault();

        console.log('✓ Form submit event triggered for listing', listingId);

        // Validate form and show modal if fields are missing
        if (typeof window.validateEditListingForm === 'function') {
          const validationResult = window.validateEditListingForm(form);
          if (!validationResult.isValid) {
            console.warn('⚠ Field validation failed - modal shown');
            if (typeof window.showFieldValidationModal === 'function') {
              window.showFieldValidationModal(validationResult.errors);
            }
            return;
          }
          console.log('✓ Field validation passed');
        } else {
          // Fallback to HTML5 validation if custom validation not available
          if (!form.checkValidity()) {
            console.warn('⚠ HTML5 validation failed');
            form.reportValidity();
            return;
          }
          console.log('✓ HTML5 validation passed (fallback)');
        }

        // Validate datalist inputs using the new boolean-returning function
        if (!validateDatalistInputs(form)) {
          console.warn('⚠ Datalist validation failed');
          return;
        }
        console.log('✓ Datalist validation passed');

        console.log('✓ All validation passed, preparing confirmation modal');
        const formData = new FormData(form);

        // Log form data for debugging
        console.log('Form data contents:');
        for (let [key, value] of formData.entries()) {
          if (value instanceof File) {
            console.log(`  ${key}: [File] ${value.name || '(no file)'}`);
          } else {
            console.log(`  ${key}: ${value}`);
          }
        }

        // Extract listing data for confirmation modal
        const metal = formData.get('metal') || '';
        const productLine = formData.get('product_line') || '';
        const productType = formData.get('product_type') || '';
        const weight = formData.get('weight') || '';
        const year = formData.get('year') || '';
        const mint = formData.get('mint') || '';
        const finish = formData.get('finish') || '';
        const grade = formData.get('grade') || '';
        const purity = formData.get('purity') || '';
        const quantity = formData.get('quantity') || '';
        const graded = formData.get('graded') === '1' || formData.get('graded') === 'true';
        const gradingService = formData.get('grading_service') || '';
        const pricingMode = formData.get('pricing_mode') || 'static';
        const pricePerCoin = formData.get('price_per_coin') || '';
        const spotPremium = formData.get('spot_premium') || '';
        const floorPrice = formData.get('floor_price') || '';
        const pricingMetal = formData.get('pricing_metal') || metal;

        // Check if photo is included - either new upload OR existing photo
        const photoFile = formData.get('photo');
        const hasNewPhoto = photoFile && photoFile.size > 0;

        // Check if there's an existing photo displayed in the preview
        const photoPreview = document.getElementById(`photoPreview-${listingId}`);
        const hasExistingPhoto = photoPreview && photoPreview.style.display !== 'none' && photoPreview.src;

        const hasPhoto = hasNewPhoto || hasExistingPhoto;

        // Prepare data for confirmation modal
        const confirmData = {
          listingId: listingId,
          metal: metal,
          productLine: productLine,
          productType: productType,
          weight: weight,
          year: year,
          mint: mint,
          finish: finish,
          grade: grade,
          purity: purity,
          quantity: quantity,
          graded: graded,
          gradingService: gradingService,
          pricingMode: pricingMode,
          pricePerCoin: pricePerCoin,
          spotPremium: spotPremium,
          floorPrice: floorPrice,
          pricingMetal: pricingMetal,
          hasPhoto: hasPhoto,
          formData: formData
        };

        console.log('✓ Opening edit listing confirmation modal');

        // Open confirmation modal instead of directly submitting
        if (typeof window.openEditListingConfirmModal === 'function') {
          window.openEditListingConfirmModal(confirmData);
        } else {
          console.error('✗ openEditListingConfirmModal function not found');
          alert('Error: Confirmation modal not available. Please refresh the page.');
        }
      });

      console.log('✓ Form submission handler successfully attached for listing', listingId);
      console.log('=== Modal setup complete for listing', listingId, '===');
    })
    .catch((err) => {
      console.error('✗ Error loading modal:', err);
      alert('Error loading edit modal: ' + err.message);
    });
}

function closeEditListingModal(listingId) {
  const wrapper = document.getElementById(`editListingModalWrapper-${listingId}`);
  if (wrapper) wrapper.remove();
}

function toggleGradingService(listingId) {
  const sel = document.getElementById(`gradedSelect-${listingId}`);
  const svc = document.getElementById(`gradingServiceContainer-${listingId}`);
  const gradingServiceSelect = document.getElementById(`gradingServiceSelect-${listingId}`);

  if (sel.value === 'yes') {
    svc.style.display = 'block';
    if (gradingServiceSelect) {
      gradingServiceSelect.required = true;
    }
  } else {
    svc.style.display = 'none';
    if (gradingServiceSelect) {
      gradingServiceSelect.required = false;
    }
  }
}
