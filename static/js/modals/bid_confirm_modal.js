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

  // Populate basic fields
  const itemDescEl = document.getElementById('bid-confirm-item-desc');
  const gradingEl = document.getElementById('bid-confirm-grading');
  const priceEl = document.getElementById('bid-confirm-price');
  const quantityEl = document.getElementById('bid-confirm-quantity');
  const totalEl = document.getElementById('bid-confirm-total');

  if (itemDescEl) {
    itemDescEl.textContent = bucketDesc || data.itemDesc || '—';
  }

  if (gradingEl) {
    if (data.requiresGrading) {
      const graderText = data.preferredGrader || 'Any';
      gradingEl.textContent = `Yes (${graderText})`;
    } else {
      gradingEl.textContent = 'No';
    }
  }

  if (quantityEl) {
    quantityEl.textContent = data.quantity;
  }

  // Handle pricing mode display
  const modeRow = document.getElementById('bid-confirm-mode-row');
  const modeEl = document.getElementById('bid-confirm-mode');
  const spotRow = document.getElementById('bid-confirm-spot-row');
  const spotEl = document.getElementById('bid-confirm-spot');
  const premiumRow = document.getElementById('bid-confirm-premium-row');
  const premiumEl = document.getElementById('bid-confirm-premium');
  const ceilingRow = document.getElementById('bid-confirm-ceiling-row');
  const ceilingEl = document.getElementById('bid-confirm-ceiling');
  const priceLabel = document.getElementById('bid-confirm-price-label');

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
  document.getElementById('success-bid-quantity').textContent = data.quantity || '—';
  document.getElementById('success-bid-item-desc').textContent = data.itemDesc || '—';

  const gradingText = data.requiresGrading
    ? `Yes${data.preferredGrader ? ` (${data.preferredGrader})` : ''}`
    : 'No';
  document.getElementById('success-bid-grading').textContent = gradingText;

  // Handle pricing mode display
  const modeRow = document.getElementById('success-mode-row');
  const modeEl = document.getElementById('success-bid-mode');
  const spotRow = document.getElementById('success-spot-row');
  const spotEl = document.getElementById('success-spot-price');
  const premiumRow = document.getElementById('success-premium-row');
  const premiumEl = document.getElementById('success-bid-premium');
  const successCeilingRow = document.getElementById('success-ceiling-row');
  const successCeilingEl = document.getElementById('success-bid-ceiling');
  const effectiveRow = document.getElementById('success-effective-row');
  const effectiveEl = document.getElementById('success-effective-price');
  const priceRow = document.getElementById('success-price-row');
  const priceLabel = document.getElementById('success-price-label');
  const priceEl = document.getElementById('success-bid-price');
  const totalEl = document.getElementById('success-bid-total');

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
    const addressLine1Row = document.getElementById('success-address-line1-row');
    const addressLine1El = document.getElementById('success-address-line1');
    if (street && addressLine1Row && addressLine1El) {
      addressLine1El.textContent = street;
      addressLine1Row.style.display = 'flex';
    }

    const addressLine2Row = document.getElementById('success-address-line2-row');
    const addressLine2El = document.getElementById('success-address-line2');
    if (street2 && addressLine2Row && addressLine2El) {
      addressLine2El.textContent = street2;
      addressLine2Row.style.display = 'flex';
    }

    const cityRow = document.getElementById('success-address-city-row');
    const cityEl = document.getElementById('success-address-city');
    if (city && cityRow && cityEl) {
      cityEl.textContent = city;
      cityRow.style.display = 'flex';
    }

    const stateRow = document.getElementById('success-address-state-row');
    const stateEl = document.getElementById('success-address-state');
    if (state && stateRow && stateEl) {
      stateEl.textContent = state;
      stateRow.style.display = 'flex';
    }

    const zipRow = document.getElementById('success-address-zip-row');
    const zipEl = document.getElementById('success-address-zip');
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
