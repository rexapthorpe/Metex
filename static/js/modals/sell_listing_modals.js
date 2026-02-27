// static/js/modals/sell_listing_modals.js
'use strict';

/* ==========================================================================
   Sell Listing Modals - Two-step confirmation flow
   1. Intercept form submission and show confirmation modal
   2. On confirm, submit via AJAX and show success modal
   3. On close success modal, redirect to Buy page
   ========================================================================== */

let pendingListingForm = null;
let pendingFormData = null;
let _submitting = false; // Submission lock — prevents double-submit
window._sellSubmitting = false; // Exposed for sidebar_controller to check

/**
 * Open confirmation modal with listing summary
 * @param {FormData} formData - Form data from sell form
 */
function openSellConfirmModal(formData) {
  const modal = document.getElementById('sellListingConfirmModal');
  if (!modal) return;

  // Core field values
  const metal      = formData.get('metal') || '—';
  const productType = formData.get('product_type') || '—';
  const year       = formData.get('year') || '';
  const productLine = formData.get('product_line') || '';
  const qty        = parseInt(formData.get('quantity')) || 1;

  // Listing mode
  const isSet      = formData.get('is_set') === '1';
  const isIsolated = formData.get('is_isolated') === '1';

  // Type badge label
  let typeLabel = 'STANDARD LISTING';
  if (isSet) typeLabel = 'SET LISTING';
  else if (isIsolated) typeLabel = 'ONE-OF-A-KIND';

  // Display title: use listing_title for isolated/set; generate for standard
  let listingTitle;
  if (isSet || isIsolated) {
    listingTitle = formData.get('listing_title') || productType || 'New Listing';
  } else {
    listingTitle = [year, productLine, productType].filter(Boolean).join(' ') || 'New Listing';
  }

  // Pricing
  const pricingMode    = formData.get('pricing_mode') || 'static';
  const isPremiumToSpot = pricingMode === 'premium_to_spot';
  let pricePerUnit;
  let priceLabel = 'Price per Unit';
  let spotPremiumDisplay = null;  // for extra rows
  let spotPriceDisplay   = null;  // for extra rows
  if (isPremiumToSpot) {
    const floorPrice   = parseFloat(formData.get('floor_price')) || 0;
    const spotPremium  = parseFloat(formData.get('spot_premium')) || 0;
    const pricingMetal = (formData.get('pricing_metal') || '').toLowerCase();
    const weightStr    = formData.get('weight') || '1';
    const weightMatch  = weightStr.match(/[\d.]+/);
    const weight       = weightMatch ? parseFloat(weightMatch[0]) : 1.0;

    // Top card always shows floor price
    pricePerUnit = floorPrice;
    priceLabel   = 'Floor Price';

    // Populate extra rows if spot prices are loaded
    if (window.spotPrices && pricingMetal && window.spotPrices[pricingMetal]) {
      const spotPrice = window.spotPrices[pricingMetal];
      spotPremiumDisplay = `+${formatPrice(spotPremium)}`;
      spotPriceDisplay   = `${formatPrice(spotPrice)}/oz`;
    }
  } else {
    pricePerUnit = parseFloat(formData.get('price_per_coin')) || 0;
  }
  const totalValue = pricePerUnit * qty;

  // Photo count
  let photoCount = 0;
  if (isSet) {
    const coverFile = formData.get('cover_photo');
    if (coverFile && coverFile.name) photoCount = 1;
  } else {
    for (const key of ['item_photo_1', 'item_photo_2', 'item_photo_3']) {
      const f = formData.get(key);
      if (f && f.name) photoCount++;
    }
  }

  // Populate elements
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

  set('confirm-type-label',    typeLabel);
  set('confirm-listing-title', listingTitle);
  set('confirm-metal',         metal);
  set('confirm-product-type',  productType);
  set('confirm-price',         formatPrice(pricePerUnit));
  set('confirm-quantity',      qty);
  set('confirm-total-value',   formatPrice(totalValue));
  set('confirm-photo-count',   photoCount === 1 ? '1 Photo Uploaded' : `${photoCount} Photos Uploaded`);

  const priceLabelEl = document.getElementById('confirm-price-label');
  if (priceLabelEl) priceLabelEl.textContent = priceLabel;

  // Show/hide and populate premium-to-spot extra rows
  const premiumRowsEl = document.getElementById('confirm-premium-rows');
  if (premiumRowsEl) {
    if (isPremiumToSpot && spotPremiumDisplay !== null) {
      premiumRowsEl.style.display = 'block';
      set('confirm-spot-premium', spotPremiumDisplay);
      set('confirm-spot-price',   spotPriceDisplay || '—');
    } else {
      premiumRowsEl.style.display = 'none';
    }
  }

  // Update confirm button text for edit vs create mode
  const confirmBtn = document.getElementById('confirmListingBtn');
  if (confirmBtn && window.sellEditMode) {
    confirmBtn.textContent = 'Update Listing \u2192';
  }

  // Disable sidebar submit button while confirmation modal is open
  // (prevents rapid-click from dispatching multiple submit events)
  const sidebarBtn = document.getElementById('sidebarSubmitBtn');
  if (sidebarBtn) sidebarBtn.disabled = true;

  // Show modal
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });
}

/**
 * Fetch fee preview from API and display proceeds
 * @param {string} prefix - 'confirm' or 'success' for element IDs
 * @param {number} grossPrice - Total gross price
 * @param {number} quantity - Quantity of items
 */
async function fetchAndDisplayProceeds(prefix, grossPrice, quantity) {
  const netEl = document.getElementById(`${prefix}-net-proceeds`);
  const grossEl = document.getElementById(`${prefix}-gross-price`);
  const feePercentEl = document.getElementById(`${prefix}-fee-percent`);
  const feeAmountEl = document.getElementById(`${prefix}-fee-amount`);
  const feeIndicatorRow = document.getElementById(`${prefix}-fee-indicator-row`);
  const feeBadge = document.getElementById(`${prefix}-fee-badge`);

  try {
    // Fetch fee preview from API
    const unitPrice = quantity > 0 ? grossPrice / quantity : grossPrice;
    const response = await fetch(`/api/fee-preview?gross_price=${unitPrice}&quantity=${quantity}`);
    const data = await response.json();

    if (data.success) {
      // Populate proceeds display
      if (netEl) netEl.textContent = formatPrice(data.net_amount);
      if (grossEl) grossEl.textContent = formatPrice(data.gross_price);
      if (feePercentEl) feePercentEl.textContent = data.fee_percent ? data.fee_percent.toFixed(1) : '—';
      if (feeAmountEl) feeAmountEl.textContent = `−${formatPrice(data.fee_amount)}`;

      // Show fee indicator if non-default
      if (data.fee_indicator && feeIndicatorRow && feeBadge) {
        feeIndicatorRow.style.display = 'flex';
        feeBadge.className = `proceeds-fee-badge fee-${data.fee_indicator}`;
        if (data.fee_indicator === 'reduced') {
          feeBadge.textContent = 'Reduced Fee';
        } else if (data.fee_indicator === 'elevated') {
          feeBadge.textContent = 'Higher Fee';
        } else if (data.fee_indicator === 'custom') {
          feeBadge.textContent = 'Custom Fee';
        }
      } else if (feeIndicatorRow) {
        feeIndicatorRow.style.display = 'none';
      }
    } else {
      // Fallback: calculate with default 2.5% fee
      const defaultFeePercent = 2.5;
      const feeAmount = Math.round(grossPrice * (defaultFeePercent / 100) * 100) / 100;
      const netAmount = grossPrice - feeAmount;

      if (netEl) netEl.textContent = formatPrice(netAmount);
      if (grossEl) grossEl.textContent = formatPrice(grossPrice);
      if (feePercentEl) feePercentEl.textContent = defaultFeePercent.toFixed(1);
      if (feeAmountEl) feeAmountEl.textContent = `−${formatPrice(feeAmount)}`;
      if (feeIndicatorRow) feeIndicatorRow.style.display = 'none';
    }
  } catch (error) {
    console.error('Error fetching fee preview:', error);
    // Fallback: calculate with default 2.5% fee
    const defaultFeePercent = 2.5;
    const feeAmount = Math.round(grossPrice * (defaultFeePercent / 100) * 100) / 100;
    const netAmount = grossPrice - feeAmount;

    if (netEl) netEl.textContent = formatPrice(netAmount);
    if (grossEl) grossEl.textContent = formatPrice(grossPrice);
    if (feePercentEl) feePercentEl.textContent = defaultFeePercent.toFixed(1);
    if (feeAmountEl) feeAmountEl.textContent = `−${formatPrice(feeAmount)}`;
    if (feeIndicatorRow) feeIndicatorRow.style.display = 'none';
  }
}

/**
 * Close confirmation modal
 */
function closeSellConfirmModal() {
  const modal = document.getElementById('sellListingConfirmModal');
  if (!modal) return;

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
    pendingListingForm = null;
    pendingFormData = null;
    // Re-enable the sidebar button by letting updateCTAButton recalculate state
    if (typeof window.updateChecklist === 'function') window.updateChecklist();
  }, 300);
}

/**
 * Open success modal with listing details
 * @param {Object} data - Response data from backend
 */
function openSellSuccessModal(data) {
  const modal = document.getElementById('sellListingSuccessModal');
  if (!modal) return;

  // Extract listing data
  const listing = data.listing || {};

  // Extract all item detail fields
  const metal = listing.metal || '—';
  const productLine = listing.product_line || '—';
  const productType = listing.product_type || '—';
  const weight = listing.weight || '—';
  const purity = listing.purity || '—';
  const mint = listing.mint || '—';
  const year = listing.year || '—';
  const finish = listing.finish || '—';
  const condition = listing.condition_category || '—';
  const seriesVariant = listing.series_variant || '—';

  // Get isolated/set/numismatic information from backend response
  const isIsolated = listing.is_isolated === 1 || listing.is_isolated === '1' || listing.is_isolated === true;
  const isolatedType = listing.isolated_type || '';
  const issueNumber = listing.issue_number || '';
  const issueTotal = listing.issue_total || '';

  // Determine listing type classification
  let listingTypeText = 'Standard pooled listing';
  let showNumismaticRow = false;
  let showSetItemsRow = false;
  let numismaticText = '';
  let setItemsCountText = '';

  if (isolatedType === 'set') {
    listingTypeText = 'Set listing (isolated)';
    showSetItemsRow = true;
    // Get set items count from backend data if available
    const setItems = data.set_items || [];
    setItemsCountText = `${setItems.length} items total`;
  } else if (issueNumber && issueTotal) {
    listingTypeText = 'Numismatic item (isolated)';
    showNumismaticRow = true;
    numismaticText = `Issue #${issueNumber} of ${issueTotal}`;
  } else if (isIsolated) {
    listingTypeText = 'One-of-a-kind (isolated)';
  }

  const quantity = listing.quantity || 0;
  const pricingMode = listing.pricing_mode || 'static';
  const isPremiumToSpot = pricingMode === 'premium_to_spot';

  // Populate ALL item detail fields
  const metalEl = modal.querySelector('#success-metal');
  const productLineEl = modal.querySelector('#success-product-line');
  const productTypeEl = modal.querySelector('#success-product-type');
  const weightEl = modal.querySelector('#success-weight');
  const purityEl = modal.querySelector('#success-purity');
  const mintEl = modal.querySelector('#success-mint');
  const yearEl = modal.querySelector('#success-year');
  const finishEl = modal.querySelector('#success-finish');

  if (metalEl) metalEl.textContent = metal;
  if (productLineEl) productLineEl.textContent = productLine;
  if (productTypeEl) productTypeEl.textContent = productType;
  if (weightEl) weightEl.textContent = weight;
  if (purityEl) purityEl.textContent = purity;
  if (mintEl) mintEl.textContent = mint;
  if (yearEl) yearEl.textContent = year;
  if (finishEl) finishEl.textContent = finish;

  const conditionEl = modal.querySelector('#success-condition');
  const seriesVariantEl = modal.querySelector('#success-series-variant');
  if (conditionEl) conditionEl.textContent = condition;
  if (seriesVariantEl) seriesVariantEl.textContent = seriesVariant;

  // Show packaging/condition fields for isolated (OOK/Set) listings
  if (isIsolated) {
    const packagingType = listing.packaging_type || '';
    const packagingNotes = listing.packaging_notes || '';
    const conditionNotes = listing.condition_notes || '';
    if (packagingType) {
      const row = modal.querySelector('#success-sell-packaging-row');
      const el = modal.querySelector('#success-sell-packaging');
      if (row) row.style.display = '';
      if (el) el.textContent = packagingType;
    }
    if (packagingNotes) {
      const row = modal.querySelector('#success-sell-packaging-notes-row');
      const el = modal.querySelector('#success-sell-packaging-notes');
      if (row) row.style.display = '';
      if (el) el.textContent = packagingNotes;
    }
    if (conditionNotes) {
      const row = modal.querySelector('#success-sell-condition-notes-row');
      const el = modal.querySelector('#success-sell-condition-notes');
      if (row) row.style.display = '';
      if (el) el.textContent = conditionNotes;
    }
  }

  // Populate listing classification fields
  const listingTypeEl = modal.querySelector('#success-listing-type');
  if (listingTypeEl) listingTypeEl.textContent = listingTypeText;

  // Show/hide and populate numismatic row
  const numismaticRowSuccess = modal.querySelector('#success-numismatic-row');
  const numismaticIssueEl = modal.querySelector('#success-numismatic-issue');
  if (numismaticRowSuccess) {
    if (showNumismaticRow) {
      numismaticRowSuccess.style.display = 'flex';
      if (numismaticIssueEl) numismaticIssueEl.textContent = numismaticText;
    } else {
      numismaticRowSuccess.style.display = 'none';
    }
  }

  // Show/hide and populate set items row
  const setItemsRowSuccess = modal.querySelector('#success-set-items-row');
  const setItemsCountEl = modal.querySelector('#success-set-items-count');
  if (setItemsRowSuccess) {
    if (showSetItemsRow) {
      setItemsRowSuccess.style.display = 'flex';
      if (setItemsCountEl) setItemsCountEl.textContent = setItemsCountText;
    } else {
      setItemsRowSuccess.style.display = 'none';
    }
  }

  // Populate pricing fields
  const quantityEl = modal.querySelector('#success-quantity');
  const pricingModeEl = modal.querySelector('#success-pricing-mode');

  if (quantityEl) quantityEl.textContent = quantity;
  if (pricingModeEl) pricingModeEl.textContent = isPremiumToSpot ? 'Premium to Spot' : 'Fixed Price';

  if (isPremiumToSpot) {
    // Premium-to-spot mode
    const spotPremium = parseFloat(listing.spot_premium) || 0;
    const floorPrice = parseFloat(listing.floor_price) || 0;
    const effectivePrice = parseFloat(listing.effective_price || listing.price_per_coin) || floorPrice;
    const totalValue = quantity * effectivePrice;

    // Get all rows
    const staticPriceRow = modal.querySelector('#success-static-price-row');
    const staticTotalRow = modal.querySelector('#success-static-total-row');
    const premiumRow = modal.querySelector('#success-premium-row');
    const floorRow = modal.querySelector('#success-floor-row');
    const effectivePriceRow = modal.querySelector('#success-effective-price-row');
    const effectiveTotalRow = modal.querySelector('#success-effective-total-row');

    // Hide static pricing rows
    if (staticPriceRow) staticPriceRow.style.display = 'none';
    if (staticTotalRow) staticTotalRow.style.display = 'none';

    // Show and populate premium-to-spot rows
    if (premiumRow) {
      premiumRow.style.display = 'flex';
      const premiumEl = modal.querySelector('#success-premium');
      if (premiumEl) premiumEl.textContent = `+${formatPrice(spotPremium)} USD per unit above spot`;
    }
    if (floorRow) {
      floorRow.style.display = 'flex';
      const floorEl = modal.querySelector('#success-floor');
      if (floorEl) floorEl.textContent = `${formatPrice(floorPrice)} USD minimum`;
    }
    if (effectivePriceRow) {
      effectivePriceRow.style.display = 'flex';
      const effectivePriceEl = modal.querySelector('#success-effective-price');
      if (effectivePriceEl) effectivePriceEl.textContent = `${formatPrice(effectivePrice)} USD`;
    }
    if (effectiveTotalRow) {
      effectiveTotalRow.style.display = 'flex';
      const effectiveTotalEl = modal.querySelector('#success-effective-total');
      if (effectiveTotalEl) effectiveTotalEl.textContent = `${formatPrice(totalValue)} USD`;
    }
  } else {
    // Static mode
    const pricePerCoin = parseFloat(listing.price_per_coin) || 0;
    const totalValue = quantity * pricePerCoin;

    // Get all rows
    const staticPriceRow = modal.querySelector('#success-static-price-row');
    const staticTotalRow = modal.querySelector('#success-static-total-row');
    const premiumRow = modal.querySelector('#success-premium-row');
    const floorRow = modal.querySelector('#success-floor-row');
    const effectivePriceRow = modal.querySelector('#success-effective-price-row');
    const effectiveTotalRow = modal.querySelector('#success-effective-total-row');

    // Show static pricing rows
    if (staticPriceRow) {
      staticPriceRow.style.display = 'flex';
      const priceEl = modal.querySelector('#success-price');
      if (priceEl) priceEl.textContent = `${formatPrice(pricePerCoin)} USD`;
    }
    if (staticTotalRow) {
      staticTotalRow.style.display = 'flex';
      const totalValueEl = modal.querySelector('#success-total-value');
      if (totalValueEl) totalValueEl.textContent = `${formatPrice(totalValue)} USD`;
    }

    // Hide premium-to-spot rows
    if (premiumRow) premiumRow.style.display = 'none';
    if (floorRow) floorRow.style.display = 'none';
    if (effectivePriceRow) effectivePriceRow.style.display = 'none';
    if (effectiveTotalRow) effectiveTotalRow.style.display = 'none';
  }

  // Calculate and display seller proceeds preview
  let grossPrice;
  if (isPremiumToSpot) {
    const effectivePrice = parseFloat(listing.effective_price || listing.price_per_coin) || parseFloat(listing.floor_price) || 0;
    grossPrice = effectivePrice * quantity;
  } else {
    const pricePerCoin = parseFloat(listing.price_per_coin) || 0;
    grossPrice = pricePerCoin * quantity;
  }

  // Fetch and display proceeds for success modal
  fetchAndDisplayProceeds('success', grossPrice, quantity);

  // Show modal with animation
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });
}

/**
 * Close success modal and redirect to Buy page
 */
function closeSellSuccessModal() {
  const modal = document.getElementById('sellListingSuccessModal');
  if (!modal) return;

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
    // Redirect to Buy page
    window.location.href = '/buy';
  }, 300);
}

/**
 * Show the listing success animation overlay, then redirect to /buy
 */
function showListingSuccessAnimation() {
  const overlay = document.getElementById('listingSuccessAnimation');
  if (!overlay) {
    window.location.href = '/buy';
    return;
  }

  // Reset animation classes so they replay cleanly
  overlay.style.display = 'flex';
  overlay.classList.remove('active');

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      overlay.classList.add('active');
    });
  });

  // Redirect after animation completes (~2s)
  setTimeout(() => {
    window.location.href = '/buy';
  }, 2200);
}

/**
 * Handle confirm listing button click - submit via AJAX
 */
function handleConfirmListing() {
  // Submission lock — prevents duplicate AJAX requests if called more than once
  if (_submitting) {
    console.warn('[SELL] handleConfirmListing called while already submitting — ignoring');
    return;
  }

  if (!pendingListingForm || !pendingFormData) {
    console.error('No pending listing data found');
    return;
  }

  const confirmBtn = document.getElementById('confirmListingBtn');
  if (!confirmBtn) return;

  const isEditMode = window.sellEditMode === true;

  // Determine form URL: in edit mode, always use the edit endpoint.
  // Prefer edit_listing_id from FormData over form action attribute (more reliable).
  let formUrl;
  if (isEditMode) {
    const editId = pendingFormData && pendingFormData.get('edit_listing_id');
    console.log('[SELL] Edit mode — edit_listing_id from FormData:', editId);
    if (editId) {
      formUrl = `/listings/edit_listing/${editId}`;
    } else {
      formUrl = (pendingListingForm && pendingListingForm.getAttribute('action')) || null;
    }
    if (!formUrl) {
      console.error('[EDIT MODE] No edit_listing_id or form action found — aborting to prevent accidental listing creation');
      alert('Error: Could not determine edit endpoint. Please refresh the page and try again.');
      return;
    }
  } else {
    formUrl = (pendingListingForm && pendingListingForm.getAttribute('action')) || '/sell';
  }

  console.log('[SELL] Submitting to URL:', formUrl, '| isEditMode:', isEditMode);

  // Lock submission and disable button
  _submitting = true;
  window._sellSubmitting = true;
  confirmBtn.disabled = true;
  confirmBtn.textContent = isEditMode ? 'Updating Listing...' : 'Creating Listing...';

  // Submit via AJAX to the appropriate route
  fetch(formUrl, {
    method: 'POST',
    body: pendingFormData,
    headers: {
      'X-Requested-With': 'XMLHttpRequest'
    }
  })
    .then(async res => {
      const contentType = res.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        return res.json();
      } else {
        throw new Error('Server returned non-JSON response');
      }
    })
    .then(data => {
      if (data.success) {
        // _submitting and window._sellSubmitting remain true until redirect
        // updateCTAButton checks window._sellSubmitting so sidebar button stays locked
        closeSellConfirmModal();
        if (isEditMode) {
          // In edit mode: redirect to account page after a short delay
          setTimeout(() => { window.location.href = '/account'; }, 350);
        } else {
          // In create mode: show the success animation (which redirects to /buy)
          setTimeout(() => {
            showListingSuccessAnimation();
          }, 350);
        }
      } else {
        // Show error — reset state so user can try again
        const errMsg = isEditMode
          ? (data.message || 'Failed to update listing. Please try again.')
          : (data.message || 'Failed to create listing. Please try again.');
        _submitting = false;
        window._sellSubmitting = false;
        if (confirmBtn) {
          confirmBtn.disabled = false;
          confirmBtn.textContent = isEditMode ? 'Update Listing \u2192' : 'Confirm Listing \u2192';
        }
        alert(errMsg);
        closeSellConfirmModal();
      }
    })
    .catch(err => {
      console.error('Sell listing error:', err);
      const errMsg = isEditMode
        ? 'An error occurred while updating your listing. Please try again.'
        : 'An error occurred while creating your listing. Please try again.';
      // Reset state on error so user can try again
      _submitting = false;
      window._sellSubmitting = false;
      if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = isEditMode ? 'Update Listing \u2192' : 'Confirm Listing \u2192';
      }
      alert(errMsg);
      closeSellConfirmModal();
    });

}

/**
 * Validate only the set-level fields (cover photo + pricing) for a Set listing
 * with 2+ items already built.  Spec fields (metal, year, etc.) are intentionally
 * excluded because they belong to the in-progress item panel, not to the set itself.
 * @param {HTMLFormElement} form
 * @returns {{isValid: boolean, errors: string[]}}
 */
function validateSetLevelFields(form) {
  const errors = [];

  // Cover photo — required for all set listings
  const coverInput = form.elements['cover_photo'];
  const coverBox = document.getElementById('coverPhotoUploadBox');
  const hasCoverPhoto =
    (coverInput && coverInput.files && coverInput.files.length > 0) ||
    (coverBox && coverBox.classList.contains('has-image')) ||
    (coverBox && coverBox.dataset.existingPhotoId);
  if (!hasCoverPhoto) {
    errors.push('Cover Photo is required');
  }

  // Pricing — detect mode via radio buttons or hidden pricing_mode field
  const staticRadio  = form.querySelector('#pricing_mode_static');
  const premiumRadio = form.querySelector('#pricing_mode_premium');
  const pricingModeEl = form.elements['pricing_mode'];
  const isPremium = (premiumRadio && premiumRadio.checked) ||
                    (pricingModeEl && pricingModeEl.value === 'premium_to_spot');

  if (isPremium) {
    const spotPremiumVal = (form.elements['spot_premium'] ? form.elements['spot_premium'].value : '').trim();
    const floorPriceVal  = (form.elements['floor_price']  ? form.elements['floor_price'].value  : '').trim();
    if (!spotPremiumVal) errors.push('Premium above spot is required');
    if (!floorPriceVal)  errors.push('"No lower than" price is required');
  } else {
    const priceVal = (form.elements['price_per_coin'] ? form.elements['price_per_coin'].value : '').trim();
    if (!priceVal) errors.push('Price Per Coin is required');
  }

  return { isValid: errors.length === 0, errors };
}

/**
 * Intercept sell form submission to validate first, then show confirmation modal
 */
function interceptSellForm() {
  const sellForm = document.getElementById('sellForm');
  if (!sellForm) return;

  // Skip if already intercepted
  if (sellForm.dataset.intercepted) return;
  sellForm.dataset.intercepted = 'true';

  sellForm.addEventListener('submit', (e) => {
    e.preventDefault();
    e.stopPropagation();

    // STEP 1: Validate the form
    //
    // SET MODE FAST PATH: when 2+ items are already built, spec-field validation
    // is completely bypassed. We read isSetHidden directly from the DOM as the
    // authoritative source (window.currentMode can lag on first render).
    const isSetHiddenEl = document.getElementById('isSetHidden');
    const isSetByHidden  = !!(isSetHiddenEl && isSetHiddenEl.value === '1');
    const isSetByMode    = window.currentMode === 'set';
    const isSetMode      = isSetByHidden || isSetByMode;
    const setItemsCount  = Array.isArray(window.setItems) ? window.setItems.length : 0;

    console.log('[SELL v7] Submit intercepted | isSetByHidden:', isSetByHidden,
      '| isSetByMode:', isSetByMode, '| setItemsCount:', setItemsCount,
      '| editMode:', !!window.sellEditMode);

    let validation;
    if (isSetMode && setItemsCount >= 2) {
      console.log('[SELL v7] SET MODE BYPASS — using validateSetLevelFields only');
      // Only validate things that belong to the set-level form, not per-item spec fields
      validation = validateSetLevelFields(sellForm);
    } else {
      console.log('[SELL v7] FULL VALIDATION — isSetMode:', isSetMode, 'setItemsCount:', setItemsCount);
      // Standard / isolated / set with <2 items: full spec+photo validation
      validation = window.sellEditMode
        ? window.validateEditListingForm(sellForm)
        : window.validateSellForm(sellForm);
    }

    if (!validation.isValid) {
      // Show validation error modal
      window.showFieldValidationModal(validation.errors);
      return;
    }

    // STEP 2: If validation passes, proceed to confirmation
    // Store form reference and data
    pendingListingForm = sellForm;
    pendingFormData = new FormData(sellForm);

    // For set listings: append stored set item photos (File objects stored in memory).
    // When an item is added to the set, photos are captured into window.setItems[i].photo
    // and the photo inputs are cleared. FormData(sellForm) won't capture them since
    // file inputs have no name attribute and are empty by submission time.
    const isSetForPhotos = isSetMode || window.currentMode === 'set';
    if (isSetForPhotos && Array.isArray(window.setItems)) {
      window.setItems.forEach(function(item, index) {
        const itemIdx = index + 1; // One-indexed to match set_items[N][...] hidden input keys
        const photos = Array.isArray(item.photo) ? item.photo : (item.photo ? [item.photo] : []);
        photos.forEach(function(photoFile, photoIdx) {
          if (photoFile instanceof File) {
            pendingFormData.append('set_item_photo_' + itemIdx + '_' + (photoIdx + 1), photoFile);
          }
        });
      });
    }

    // Show confirmation modal
    openSellConfirmModal(pendingFormData);
  });
}

/**
 * Initialize modal system
 */
document.addEventListener('DOMContentLoaded', () => {
  // Wire up confirmation button
  const confirmBtn = document.getElementById('confirmListingBtn');
  if (confirmBtn) {
    confirmBtn.addEventListener('click', handleConfirmListing);
  }

  // Intercept sell form
  interceptSellForm();

  // Close confirm modal on overlay click (not while submitting)
  document.getElementById('sellListingConfirmModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'sellListingConfirmModal' && !_submitting) {
      closeSellConfirmModal();
    }
  });

  // Close success modal on overlay click
  document.getElementById('sellListingSuccessModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'sellListingSuccessModal') {
      closeSellSuccessModal();
    }
  });

  // Close modals on Escape key (not while submitting)
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (!_submitting) closeSellConfirmModal();
      closeSellSuccessModal();
    }
  });
});

// Expose functions globally
window.openSellConfirmModal = openSellConfirmModal;
window.closeSellConfirmModal = closeSellConfirmModal;
window.openSellSuccessModal = openSellSuccessModal;
window.closeSellSuccessModal = closeSellSuccessModal;
window.showListingSuccessAnimation = showListingSuccessAnimation;
