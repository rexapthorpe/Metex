// static/js/modals/bid_confirm_modal.js
'use strict';

/* ==========================================================================
   Bid Confirmation Modal
   Shows before final bid submission to confirm details
   ========================================================================== */

/**
 * Open bid confirmation modal with bid details
 * @param {Object} data - Bid data to display
 * @param {string} data.itemDesc - Item description
 * @param {boolean} data.requiresGrading - Whether grading is required
 * @param {string} data.preferredGrader - Preferred grader (e.g., "PCGS", "NGC", "Any")
 * @param {number} data.price - Price per item (or ceiling price for variable bids)
 * @param {number} data.quantity - Quantity requested
 * @param {boolean} data.isEdit - Whether this is editing an existing bid
 * @param {string} data.pricingMode - Pricing mode ('static' or 'premium_to_spot')
 * @param {number} data.spotPremium - Premium above spot price (for variable bids)
 * @param {number} data.ceilingPrice - Ceiling/maximum price (for variable bids)
 * @param {string} data.pricingMetal - Metal for spot pricing (for variable bids)
 */
async function openBidConfirmModal(data) {
  const modal = document.getElementById('bidConfirmModal');

  if (!modal) {
    console.error('Bid confirmation modal not found (#bidConfirmModal)');
    return;
  }

  // Get bucket description from the bid form
  const bucketDesc = getBucketDescription();

  // Determine pricing mode
  const pricingMode = data.pricingMode || 'static';
  const isVariablePricing = pricingMode === 'premium_to_spot';

  // For variable pricing, fetch current spot prices and calculate effective price
  let currentSpotPrice = null;
  let effectivePrice = data.price || data.ceilingPrice || 0;

  if (isVariablePricing) {
    try {
      const response = await fetch('/api/spot-prices');
      const spotData = await response.json();

      if (spotData.success && spotData.prices) {
        // Get metal from passed data (prioritize pricingMetal, then metal, then fall back to bucketSpecs)
        const metal = data.pricingMetal || data.metal || (window.bucketSpecs && window.bucketSpecs['Metal']) || '';

        // Parse weight from passed data (e.g., "1 oz" → 1.0)
        const weightStr = data.weight || (window.bucketSpecs && window.bucketSpecs['Weight']) || '1';
        const weightMatch = weightStr.toString().match(/[\d.]+/);
        const weight = weightMatch ? parseFloat(weightMatch[0]) : 1.0;

        if (metal && spotData.prices[metal.toLowerCase()]) {
          currentSpotPrice = spotData.prices[metal.toLowerCase()];

          // Calculate effective price: (spot * weight) + premium
          // NOTE: Floor is shown separately but NOT applied to display price
          const spotPremium = parseFloat(data.spotPremium) || 0;
          const ceilingPrice = parseFloat(data.ceilingPrice) || 0;
          const calculatedPrice = (currentSpotPrice * weight) + spotPremium;
          effectivePrice = calculatedPrice;  // Show calculated price, not floor-adjusted

          console.log('Bid confirmation - Spot price calculation:', {
            metal,
            weight,
            currentSpotPrice,
            spotPremium,
            ceilingPrice,
            calculatedPrice,
            effectivePrice,
            note: 'Effective price = spot + premium (ceiling shown separately)'
          });

          // Store calculated values for success modal
          data.currentSpotPrice = currentSpotPrice;
          data.effectivePrice = effectivePrice;
        } else {
          console.warn('Metal not found in spot prices:', metal, 'Available:', Object.keys(spotData.prices));
        }
      }
    } catch (error) {
      console.error('Error fetching spot prices:', error);
      // Fall back to ceiling price if API fails
      effectivePrice = data.ceilingPrice || 0;
    }
  }

  // Populate item specs from form data attributes
  const form = document.getElementById('bid-form');
  let metal = '', productLine = '', productType = '', weight = '', year = '', mint = '', finish = '', grade = '', purity = '';

  if (form) {
    metal = form.dataset.bucketMetal || '';
    productLine = form.dataset.bucketProductLine || '';
    productType = form.dataset.bucketProductType || '';
    weight = form.dataset.bucketWeight || '';
    year = form.dataset.bucketYear || '';
    mint = form.dataset.bucketMint || '';
    finish = form.dataset.bucketFinish || '';
    grade = form.dataset.bucketGrade || '';
    purity = form.dataset.bucketPurity || '';
  }

  // Populate item detail spec fields
  const metalSpec = modal.querySelector('#confirm-spec-metal .spec-value');
  const productLineSpec = modal.querySelector('#confirm-spec-product-line .spec-value');
  const productTypeSpec = modal.querySelector('#confirm-spec-product-type .spec-value');
  const weightSpec = modal.querySelector('#confirm-spec-weight .spec-value');
  const gradeSpec = modal.querySelector('#confirm-spec-grade .spec-value');
  const yearSpec = modal.querySelector('#confirm-spec-year .spec-value');
  const mintSpec = modal.querySelector('#confirm-spec-mint .spec-value');
  const puritySpec = modal.querySelector('#confirm-spec-purity .spec-value');
  const finishSpec = modal.querySelector('#confirm-spec-finish .spec-value');

  if (metalSpec) metalSpec.textContent = metal || '—';
  if (productLineSpec) productLineSpec.textContent = productLine || '—';
  if (productTypeSpec) productTypeSpec.textContent = productType || '—';
  if (weightSpec) weightSpec.textContent = weight || '—';
  if (gradeSpec) gradeSpec.textContent = grade || 'N/A';
  if (yearSpec) yearSpec.textContent = year || '—';
  if (mintSpec) mintSpec.textContent = mint || '—';
  if (puritySpec) puritySpec.textContent = purity || '—';
  if (finishSpec) finishSpec.textContent = finish || 'N/A';

  // Populate grading requirement
  const gradingEl = modal.querySelector('#bid-confirm-grading');
  if (gradingEl) {
    if (data.requiresGrading) {
      const graderText = data.preferredGrader || 'Any';
      gradingEl.textContent = `Yes (${graderText})`;
    } else {
      gradingEl.textContent = 'No';
    }
  }

  // Populate quantity
  const quantityEl = modal.querySelector('#bid-confirm-quantity');
  if (quantityEl) {
    quantityEl.textContent = data.quantity;
  }

  // Handle pricing mode display
  const priceEl = modal.querySelector('#bid-confirm-price');
  const totalEl = modal.querySelector('#bid-confirm-total');
  const modeRow = modal.querySelector('#bid-confirm-mode-row');
  const modeEl = modal.querySelector('#bid-confirm-mode');
  const spotRow = modal.querySelector('#bid-confirm-spot-row');
  const spotEl = modal.querySelector('#bid-confirm-spot');
  const premiumRow = modal.querySelector('#bid-confirm-premium-row');
  const premiumEl = modal.querySelector('#bid-confirm-premium');
  const ceilingRow = modal.querySelector('#bid-confirm-ceiling-row');
  const ceilingEl = modal.querySelector('#bid-confirm-ceiling');
  const priceLabel = modal.querySelector('#bid-confirm-price-label');

  console.log('🔍 [Bid Confirm Modal] Display Logic:', {
    isVariablePricing,
    pricingMode,
    currentSpotPrice,
    effectivePrice,
    spotPremium: data.spotPremium,
    ceilingPrice: data.ceilingPrice,
    elementsFound: {
      modeRow: !!modeRow,
      spotRow: !!spotRow,
      spotEl: !!spotEl,
      premiumRow: !!premiumRow,
      premiumEl: !!premiumEl,
      ceilingRow: !!ceilingRow,
      ceilingEl: !!ceilingEl,
      priceEl: !!priceEl
    }
  });

  if (isVariablePricing) {
    console.log('✅ [Bid Confirm Modal] Showing variable pricing fields');

    // Show variable pricing fields
    if (modeRow) {
      modeRow.style.display = 'flex';
      console.log('  → modeRow display set to:', modeRow.style.display);
    }
    if (modeEl) {
      modeEl.textContent = 'Variable (Premium to Spot)';
      console.log('  → modeEl text set to:', modeEl.textContent);
    }

    // Show current spot price
    if (spotRow) {
      spotRow.style.display = 'flex';
      console.log('  → spotRow display set to:', spotRow.style.display);
    }
    if (spotEl && currentSpotPrice !== null) {
      spotEl.textContent = `$${currentSpotPrice.toFixed(2)}/oz`;
      console.log('  → spotEl text set to:', spotEl.textContent);
    } else {
      spotEl.textContent = 'Loading...';
    }

    if (premiumRow) {
      premiumRow.style.display = 'flex';
      console.log('  → premiumRow display set to:', premiumRow.style.display);
    }
    if (premiumEl && data.spotPremium !== undefined) {
      premiumEl.textContent = `$${parseFloat(data.spotPremium).toFixed(2)}`;
      console.log('  → premiumEl text set to:', premiumEl.textContent);
    }

    if (ceilingRow) {
      ceilingRow.style.display = 'flex';
      console.log('  → ceilingRow display set to:', ceilingRow.style.display);
    }
    if (ceilingEl && data.ceilingPrice !== undefined) {
      ceilingEl.textContent = `$${parseFloat(data.ceilingPrice).toFixed(2)}`;
      console.log('  → ceilingEl text set to:', ceilingEl.textContent);
    }

    // Show effective price in the main price row
    if (priceLabel) {
      priceLabel.textContent = 'Current Effective Bid Price:';
    }

    if (priceEl) {
      priceEl.textContent = `$${effectivePrice.toFixed(2)}`;
      console.log('  → priceEl (effective) text set to:', priceEl.textContent);
    }

    // Calculate total using effective price
    if (totalEl && data.quantity) {
      const total = effectivePrice * parseInt(data.quantity);
      totalEl.textContent = `$${total.toFixed(2)}`;
    }
  } else {
    console.log('ℹ️ [Bid Confirm Modal] Showing static pricing fields');

    // Hide variable pricing fields for fixed bids
    if (modeRow) modeRow.style.display = 'none';
    if (spotRow) spotRow.style.display = 'none';
    if (premiumRow) premiumRow.style.display = 'none';
    if (ceilingRow) ceilingRow.style.display = 'none';

    if (priceLabel) {
      priceLabel.textContent = 'Your bid per item:';
    }

    if (priceEl && data.price !== undefined) {
      priceEl.textContent = `$${parseFloat(data.price).toFixed(2)}`;
    }

    if (totalEl && data.price !== undefined && data.quantity) {
      const total = parseFloat(data.price) * parseInt(data.quantity);
      totalEl.textContent = `$${total.toFixed(2)}`;
    }
  }

  // Parse and populate delivery address
  console.log('[BID CONFIRM] Raw delivery_address:', data.deliveryAddress);

  let address = data.deliveryAddress || '';
  let street = '';
  let street2 = '';
  let city = '';
  let state = '';
  let zip = '';

  // Handle different address formats
  if (!address || address === 'Not provided') {
    console.log('[BID CONFIRM] No address provided');
  } else if (typeof address === 'object') {
    // Address is an object with separate fields
    street = address.line1 || address.street || '';
    street2 = address.line2 || address.street2 || '';
    city = address.city || '';
    state = address.state || '';
    zip = address.zip || address.zip_code || '';
  } else if (typeof address === 'string' && address.includes('•')) {
    // Bullet separator format: "Name • Line1 • [Line2 •] City, State ZIP"
    console.log('[BID CONFIRM] Parsing bullet-separated address');

    let cleanAddress = address;
    if (address.includes(' - ')) {
      cleanAddress = address.split(' - ').slice(1).join(' - ');
    }

    const addressParts = cleanAddress.split('•').map(p => p.trim());
    console.log('[BID CONFIRM] Address parts:', addressParts);

    // Extract components based on number of parts
    let cityStateZip = '';
    if (addressParts.length === 4) {
      // Format: Name • Line1 • Line2 • City, State ZIP
      street = addressParts[1];
      street2 = addressParts[2];
      cityStateZip = addressParts[3];
    } else if (addressParts.length === 3) {
      // Format: Line1 • Line2 • City, State ZIP  OR  Name • Line1 • City, State ZIP
      const lastPart = addressParts[2];
      if (lastPart.includes(',')) {
        // Last part has comma, so it's City,State ZIP format
        street = addressParts[0];
        street2 = addressParts[1];
        cityStateZip = lastPart;
      } else {
        street = addressParts[0];
        street2 = addressParts[1];
        cityStateZip = addressParts[2];
      }
    } else if (addressParts.length === 2) {
      // Format: Line1 • City, State ZIP
      street = addressParts[0];
      cityStateZip = addressParts[1];
    } else if (addressParts.length === 1) {
      street = addressParts[0];
    }

    // Parse "City, State ZIP" or "City, State, ZIP"
    if (cityStateZip && cityStateZip.includes(',')) {
      const cityParts = cityStateZip.split(',').map(p => p.trim());
      city = cityParts[0];

      if (cityParts.length === 2) {
        // Format: "City, State ZIP"
        const stateZipParts = cityParts[1].split(/\s+/);
        if (stateZipParts.length >= 1) {
          state = stateZipParts[0];
        }
        if (stateZipParts.length >= 2) {
          zip = stateZipParts.slice(1).join(' ');
        }
      } else if (cityParts.length >= 3) {
        // Format: "City, State, ZIP"
        state = cityParts[1];
        zip = cityParts.slice(2).join(', ');
      }
    }
  } else if (typeof address === 'string') {
    // Simple text address
    console.log('[BID CONFIRM] Simple text address');
    street = address;
  }

  console.log('[BID CONFIRM] Parsed address:', {
    street, street2, city, state, zip
  });

  // Get all address elements (scoped to this modal)
  const line1Row = modal.querySelector('#confirm-address-line1-row');
  const line1El = modal.querySelector('#confirm-address-line1');
  const line2Row = modal.querySelector('#confirm-address-line2-row');
  const line2El = modal.querySelector('#confirm-address-line2');
  const cityRow = modal.querySelector('#confirm-address-city-row');
  const cityEl = modal.querySelector('#confirm-address-city');
  const stateRow = modal.querySelector('#confirm-address-state-row');
  const stateEl = modal.querySelector('#confirm-address-state');
  const zipRow = modal.querySelector('#confirm-address-zip-row');
  const zipEl = modal.querySelector('#confirm-address-zip');

  // Populate and show each component
  if (line1El && line1Row) {
    line1El.textContent = street || '—';
    line1Row.style.display = 'flex';
    console.log('[BID CONFIRM] Line 1:', street || '—');
  }

  if (line2El && line2Row) {
    line2El.textContent = street2 || '—';
    line2Row.style.display = 'flex';
    console.log('[BID CONFIRM] Line 2:', street2 || '—');
  }

  if (cityEl && cityRow) {
    cityEl.textContent = city || '—';
    cityRow.style.display = 'flex';
    console.log('[BID CONFIRM] City:', city || '—');
  }

  if (stateEl && stateRow) {
    stateEl.textContent = state || '—';
    stateRow.style.display = 'flex';
    console.log('[BID CONFIRM] State:', state || '—');
  }

  if (zipEl && zipRow) {
    zipEl.textContent = zip || '—';
    zipRow.style.display = 'flex';
    console.log('[BID CONFIRM] ZIP:', zip || '—');
  }

  // Show modal with animation
  modal.style.display = 'flex';

  // Trigger animation on next frame
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });

  // Set up confirm button
  const confirmBtn = document.getElementById('bidConfirmBtn');
  if (confirmBtn) {
    // Remove any existing listeners
    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);

    // Add new listener
    newBtn.addEventListener('click', () => {
      // Call the submission function from bid_modal.js
      if (typeof window.submitBidForm === 'function') {
        window.submitBidForm();
      } else {
        console.error('submitBidForm function not found');
        alert('Error: Unable to submit bid. Please refresh and try again.');
      }
    });
  }
}

/**
 * Close bid confirmation modal
 */
function closeBidConfirmModal() {
  const modal = document.getElementById('bidConfirmModal');

  if (!modal) return;

  // Add hiding class for fade-out animation
  modal.classList.add('hiding');
  modal.classList.remove('active');

  // Wait for animation to complete before hiding
  setTimeout(() => {
    modal.style.display = 'none';
    modal.classList.remove('hiding');
  }, 300);
}

/**
 * Get bucket description from the bid form
 * @returns {string} Formatted bucket description
 */
function getBucketDescription() {
  // Try to extract bucket info from the bid form data attributes
  const form = document.getElementById('bid-form');
  if (!form) return 'Item from selected category';

  // Extract bucket attributes from data attributes
  const metal = form.dataset.bucketMetal || '';
  const productLine = form.dataset.bucketProductLine || '';
  const productType = form.dataset.bucketProductType || '';
  const weight = form.dataset.bucketWeight || '';
  const year = form.dataset.bucketYear || '';
  const mint = form.dataset.bucketMint || '';
  const finish = form.dataset.bucketFinish || '';
  const grade = form.dataset.bucketGrade || '';

  // Build description from available attributes
  const parts = [];

  if (year) parts.push(year);
  if (metal) parts.push(metal);
  if (productLine) parts.push(productLine);
  if (productType) parts.push(productType);
  if (weight) parts.push(weight);
  if (mint) parts.push(`(${mint})`);
  if (finish && finish !== 'N/A') parts.push(`- ${finish}`);
  if (grade && grade !== 'N/A') parts.push(`[${grade}]`);

  return parts.length > 0 ? parts.join(' ') : 'Item from selected category';
}

/**
 * Open bid success modal with bid details
 * @param {Object} data - Bid data to display
 * @param {string} data.pricingMode - Pricing mode ('static' or 'premium_to_spot')
 * @param {number} data.effectivePrice - Effective price (for variable bids)
 * @param {number} data.currentSpotPrice - Current spot price (for variable bids)
 * @param {number} data.spotPremium - Premium above spot (for variable bids)
 * @param {number} data.ceilingPrice - Floor/minimum price (for variable bids)
 */
function openBidSuccessModal(data) {
  const modal = document.getElementById('bidSuccessModal');

  if (!modal) {
    console.error('Bid success modal not found (#bidSuccessModal)');
    return;
  }

  // Debug logging
  console.log('openBidSuccessModal called with data:', data);
  console.log('- pricingMode:', data.pricingMode);
  console.log('- effectivePrice:', data.effectivePrice);
  console.log('- currentSpotPrice:', data.currentSpotPrice);
  console.log('- spotPremium:', data.spotPremium);
  console.log('- ceilingPrice:', data.ceilingPrice);

  // Determine pricing mode
  const pricingMode = data.pricingMode || 'static';
  const isVariablePricing = pricingMode === 'premium_to_spot';

  // Populate basic fields
  modal.querySelector('#success-bid-quantity').textContent = data.quantity || '—';

  // Populate grading requirement
  const gradingText = data.requiresGrading
    ? `Yes${data.preferredGrader ? ` (${data.preferredGrader})` : ''}`
    : 'No';
  modal.querySelector('#success-bid-grading').textContent = gradingText;

  // Populate item detail spec fields from bucket data
  const metalSpec = modal.querySelector('#success-spec-metal .spec-value');
  const productLineSpec = modal.querySelector('#success-spec-product-line .spec-value');
  const productTypeSpec = modal.querySelector('#success-spec-product-type .spec-value');
  const weightSpec = modal.querySelector('#success-spec-weight .spec-value');
  const gradeSpec = modal.querySelector('#success-spec-grade .spec-value');
  const yearSpec = modal.querySelector('#success-spec-year .spec-value');
  const mintSpec = modal.querySelector('#success-spec-mint .spec-value');
  const puritySpec = modal.querySelector('#success-spec-purity .spec-value');
  const finishSpec = modal.querySelector('#success-spec-finish .spec-value');

  if (metalSpec) metalSpec.textContent = data.bucketMetal || '—';
  if (productLineSpec) productLineSpec.textContent = data.bucketProductLine || '—';
  if (productTypeSpec) productTypeSpec.textContent = data.bucketProductType || '—';
  if (weightSpec) weightSpec.textContent = data.bucketWeight || '—';
  if (gradeSpec) gradeSpec.textContent = data.bucketGrade || 'N/A';
  if (yearSpec) yearSpec.textContent = data.bucketYear || '—';
  if (mintSpec) mintSpec.textContent = data.bucketMint || '—';
  if (puritySpec) puritySpec.textContent = data.bucketPurity || '—';
  if (finishSpec) finishSpec.textContent = data.bucketFinish || 'N/A';

  console.log('✅ [Bid Success Modal] Populated item specs:', {
    metal: data.bucketMetal,
    productLine: data.bucketProductLine,
    productType: data.bucketProductType,
    weight: data.bucketWeight,
    grade: data.bucketGrade,
    year: data.bucketYear,
    mint: data.bucketMint,
    purity: data.bucketPurity,
    finish: data.bucketFinish
  });

  // Handle pricing mode display
  const modeRow = modal.querySelector('#success-mode-row');
  const modeEl = modal.querySelector('#success-bid-mode');
  const spotRow = modal.querySelector('#success-spot-row');
  const spotEl = modal.querySelector('#success-spot-price');
  const premiumRow = modal.querySelector('#success-premium-row');
  const premiumEl = modal.querySelector('#success-bid-premium');
  const successCeilingRow = modal.querySelector('#success-ceiling-row');
  const successCeilingEl = modal.querySelector('#success-bid-ceiling');
  const effectiveRow = modal.querySelector('#success-effective-row');
  const effectiveEl = modal.querySelector('#success-effective-price');
  const priceRow = modal.querySelector('#success-price-row');
  const priceLabel = modal.querySelector('#success-price-label');
  const priceEl = modal.querySelector('#success-bid-price');
  const totalEl = modal.querySelector('#success-bid-total');

  console.log('🔍 [Bid Success Modal] Display Logic:', {
    isVariablePricing,
    pricingMode,
    currentSpotPrice: data.currentSpotPrice,
    effectivePrice: data.effectivePrice,
    spotPremium: data.spotPremium,
    ceilingPrice: data.ceilingPrice,
    elementsFound: {
      modeRow: !!modeRow,
      spotRow: !!spotRow,
      spotEl: !!spotEl,
      premiumRow: !!premiumRow,
      premiumEl: !!premiumEl,
      successCeilingRow: !!successCeilingRow,
      successCeilingEl: !!successCeilingEl,
      effectiveRow: !!effectiveRow,
      effectiveEl: !!effectiveEl
    }
  });

  if (isVariablePricing) {
    console.log('✅ [Bid Success Modal] Showing variable pricing fields');

    // Show variable pricing fields
    if (modeRow) {
      modeRow.style.display = 'flex';
      console.log('  → modeRow display set to:', modeRow.style.display);
    }
    if (modeEl) {
      modeEl.textContent = 'Variable (Premium to Spot)';
      console.log('  → modeEl text set to:', modeEl.textContent);
    }

    if (spotRow) {
      spotRow.style.display = 'flex';
      console.log('  → spotRow display set to:', spotRow.style.display);
    }
    if (spotEl) {
      if (data.currentSpotPrice != null && !isNaN(data.currentSpotPrice)) {
        spotEl.textContent = `$${parseFloat(data.currentSpotPrice).toFixed(2)}/oz`;
        console.log('  → spotEl text set to:', spotEl.textContent);
      } else {
        spotEl.textContent = '—';
        console.warn('Current spot price is null or invalid:', data.currentSpotPrice);
      }
    }

    if (premiumRow) {
      premiumRow.style.display = 'flex';
      console.log('  → premiumRow display set to:', premiumRow.style.display);
    }
    if (premiumEl) {
      if (data.spotPremium != null && !isNaN(data.spotPremium)) {
        premiumEl.textContent = `$${parseFloat(data.spotPremium).toFixed(2)}`;
        console.log('  → premiumEl text set to:', premiumEl.textContent);
      } else {
        premiumEl.textContent = '—';
        console.warn('Spot premium is null or invalid:', data.spotPremium);
      }
    }

    if (successCeilingRow) {
      successCeilingRow.style.display = 'flex';
      console.log('  → successCeilingRow display set to:', successCeilingRow.style.display);
    }
    if (successCeilingEl) {
      if (data.ceilingPrice != null && !isNaN(data.ceilingPrice)) {
        successCeilingEl.textContent = `$${parseFloat(data.ceilingPrice).toFixed(2)}`;
        console.log('  → successCeilingEl text set to:', successCeilingEl.textContent);
      } else {
        successCeilingEl.textContent = '—';
        console.warn('Ceiling price is null or invalid:', data.ceilingPrice);
      }
    }

    if (effectiveRow) {
      effectiveRow.style.display = 'flex';
      console.log('  → effectiveRow display set to:', effectiveRow.style.display);
    }
    if (effectiveEl) {
      if (data.effectivePrice != null && !isNaN(data.effectivePrice)) {
        effectiveEl.textContent = `$${parseFloat(data.effectivePrice).toFixed(2)}`;
        console.log('  → effectiveEl text set to:', effectiveEl.textContent);
      } else {
        effectiveEl.textContent = '—';
        console.warn('Effective price is null or invalid:', data.effectivePrice);
      }
    }

    // For variable bids, hide the static price row
    if (priceRow) priceRow.style.display = 'none';

    // Calculate total using effective price
    if (totalEl) {
      if (data.effectivePrice != null && !isNaN(data.effectivePrice) && data.quantity) {
        const total = parseFloat(data.effectivePrice) * parseInt(data.quantity);
        totalEl.textContent = `$${total.toFixed(2)}`;
      } else {
        totalEl.textContent = '—';
        console.warn('Cannot calculate total - effective price or quantity invalid:', {
          effectivePrice: data.effectivePrice,
          quantity: data.quantity
        });
      }
    }
  } else {
    console.log('ℹ️ [Bid Success Modal] Showing static pricing fields');

    // Hide variable pricing fields for fixed bids
    if (modeRow) modeRow.style.display = 'none';
    if (spotRow) spotRow.style.display = 'none';
    if (premiumRow) premiumRow.style.display = 'none';
    if (successCeilingRow) successCeilingRow.style.display = 'none';
    if (effectiveRow) effectiveRow.style.display = 'none';

    // Show static price for fixed bids
    if (priceRow) priceRow.style.display = '';
    if (priceLabel) priceLabel.textContent = 'Price per Item:';
    if (priceEl && data.price !== undefined) {
      priceEl.textContent = `$${parseFloat(data.price).toFixed(2)}`;
    }

    // Calculate total using static price
    if (totalEl && data.price !== undefined && data.quantity) {
      const total = parseFloat(data.price) * parseInt(data.quantity);
      totalEl.textContent = `$${total.toFixed(2)}`;
    }
  }

  // Parse and display delivery address
  if (data.deliveryAddress) {
    // Address format: "Street • [Street2 •] City, State ZIP"
    const addressParts = data.deliveryAddress.split('•').map(p => p.trim());

    let street = '';
    let street2 = '';
    let city = '';
    let state = '';
    let zip = '';

    // Extract street and optional street2
    if (addressParts.length >= 1) {
      street = addressParts[0];
    }

    // Check if we have 3 parts (street • street2 • city,state zip) or 2 parts (street • city,state zip)
    let cityStateZip = '';
    if (addressParts.length === 3) {
      // Middle part is Address Line 2
      street2 = addressParts[1];
      cityStateZip = addressParts[2];
    } else if (addressParts.length === 2) {
      // No Address Line 2
      cityStateZip = addressParts[1];
    }

    // Parse "City, State ZIP" from the last part
    if (cityStateZip && cityStateZip.includes(',')) {
      const cityParts = cityStateZip.split(',');
      city = cityParts[0].trim();
      if (cityParts.length > 1) {
        const stateZipParts = cityParts[1].trim().split(/\s+/);
        if (stateZipParts.length >= 1) {
          state = stateZipParts[0];
        }
        if (stateZipParts.length >= 2) {
          zip = stateZipParts[1];
        }
      }
    }

    // Display address components
    const addressLine1Row = modal.querySelector('#success-address-line1-row');
    const addressLine1El = modal.querySelector('#success-address-line1');
    if (street && addressLine1Row && addressLine1El) {
      addressLine1El.textContent = street;
      addressLine1Row.style.display = 'flex';
    }

    const addressLine2Row = modal.querySelector('#success-address-line2-row');
    const addressLine2El = modal.querySelector('#success-address-line2');
    if (street2 && addressLine2Row && addressLine2El) {
      addressLine2El.textContent = street2;
      addressLine2Row.style.display = 'flex';
    }

    const cityRow = modal.querySelector('#success-address-city-row');
    const cityEl = modal.querySelector('#success-address-city');
    if (city && cityRow && cityEl) {
      cityEl.textContent = city;
      cityRow.style.display = 'flex';
    }

    const stateRow = modal.querySelector('#success-address-state-row');
    const stateEl = modal.querySelector('#success-address-state');
    if (state && stateRow && stateEl) {
      stateEl.textContent = state;
      stateRow.style.display = 'flex';
    }

    const zipRow = modal.querySelector('#success-address-zip-row');
    const zipEl = modal.querySelector('#success-address-zip');
    if (zip && zipRow && zipEl) {
      zipEl.textContent = zip;
      zipRow.style.display = 'flex';
    }

    console.log('✅ [Bid Success Modal] Parsed delivery address:', {
      street,
      street2,
      city,
      state,
      zip
    });
  }

  // Show modal
  modal.style.display = 'flex';

  // Trigger animation on next frame
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });
}

/**
 * Close bid success modal
 */
function closeBidSuccessModal() {
  const modal = document.getElementById('bidSuccessModal');

  if (!modal) return;

  // Add hiding class for fade-out animation
  modal.classList.add('hiding');
  modal.classList.remove('active');

  // Wait for animation to complete before hiding
  setTimeout(() => {
    modal.style.display = 'none';
    modal.classList.remove('hiding');

    // Reload page to show updated bids
    location.reload();
  }, 300);
}

// Global exposure
window.openBidConfirmModal = openBidConfirmModal;
window.closeBidConfirmModal = closeBidConfirmModal;
window.openBidSuccessModal = openBidSuccessModal;
window.closeBidSuccessModal = closeBidSuccessModal;

// Close on overlay click
window.addEventListener('click', (e) => {
  const confirmModal = document.getElementById('bidConfirmModal');
  const successModal = document.getElementById('bidSuccessModal');

  if (e.target === confirmModal) {
    closeBidConfirmModal();
  }
  if (e.target === successModal) {
    closeBidSuccessModal();
  }
});

// Close on Escape
window.addEventListener('keydown', (e) => {
  const confirmModal = document.getElementById('bidConfirmModal');
  const successModal = document.getElementById('bidSuccessModal');

  if (e.key === 'Escape') {
    if (confirmModal && confirmModal.style.display !== 'none') {
      closeBidConfirmModal();
    }
    if (successModal && successModal.style.display !== 'none') {
      closeBidSuccessModal();
    }
  }
});
