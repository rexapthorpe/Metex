// static/js/modals/buy_item_modal.js
'use strict';

/* ==========================================================================
   Buy Item Confirmation Modal
   Shows purchase summary before proceeding to checkout
   ========================================================================== */

let pendingBuyData = null;
let priceLockTimer = null;  // Interval ID for countdown timer
let priceLockData = null;   // Price lock information from backend

/**
 * Open confirmation modal with purchase summary
 * @param {Object} itemData - Item information
 */
function openBuyItemConfirmModal(itemData) {
  pendingBuyData = itemData;

  const modal = document.getElementById('buyItemConfirmModal');
  if (!modal) return;

  // Get bucket specs from window or use defaults
  const specs = window.bucketSpecs || {};

  // Populate item specifications (specs keys use capitalized format with spaces)
  document.getElementById('buy-spec-metal').textContent = specs['Metal'] || '—';
  document.getElementById('buy-spec-product-type').textContent = specs['Product type'] || '—';
  document.getElementById('buy-spec-weight').textContent = specs['Weight'] || '—';
  document.getElementById('buy-spec-purity').textContent = specs['Purity'] || '—';
  document.getElementById('buy-spec-mint').textContent = specs['Mint'] || '—';
  document.getElementById('buy-spec-year').textContent = specs['Year'] || '—';
  document.getElementById('buy-spec-finish').textContent = specs['Finish'] || '—';
  document.getElementById('buy-spec-grade').textContent = specs['Grading'] || '—';
  document.getElementById('buy-spec-product-line').textContent = specs['Product line'] || '—';

  // Populate "Requires 3rd Party Grading" field based on buyer's toggle choice
  // Check the TPG toggle state from the page
  const tpgToggle = document.getElementById('tpgToggle');
  const thirdPartyGradingRequested = tpgToggle && tpgToggle.checked;
  const requiresGrading = thirdPartyGradingRequested ? 'Yes' : 'No';
  document.getElementById('buy-spec-requires-grading').textContent = requiresGrading;

  // Conditionally show/hide grading service field (only show if listing is already graded)
  const gradingServiceRow = document.getElementById('buy-spec-grading-service-row');
  if ((specs.graded === 1 || specs.graded === '1') && specs.grading_service) {
    document.getElementById('buy-spec-grading-service').textContent = specs.grading_service;
    gradingServiceRow.style.display = '';
  } else {
    gradingServiceRow.style.display = 'none';
  }

  // Set loading state for purchase summary
  document.getElementById('buy-confirm-price').textContent = 'Calculating...';
  document.getElementById('buy-confirm-quantity').textContent = itemData.quantity;
  document.getElementById('buy-confirm-total').textContent = 'Calculating...';

  // Show modal with animation
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });

  // Fetch and populate delivery addresses
  fetchAndPopulateAddresses();

  // Fetch actual price breakdown from backend
  const formData = new FormData();
  formData.append('quantity', itemData.quantity);

  // Include Random Year mode if enabled
  const randomYearToggle = document.getElementById('randomYearToggle');
  if (randomYearToggle && randomYearToggle.checked) {
    formData.append('random_year', '1');
  }

  // Include Third-Party Grading toggle if enabled (tpgToggle already declared above)
  if (tpgToggle && tpgToggle.checked) {
    formData.append('third_party_grading', '1');
  } else {
    formData.append('third_party_grading', '0');
  }

  // Include packaging filters (multi-select)
  const packagingTypeCheckboxes = document.querySelectorAll('.packaging-type-checkbox:checked');
  packagingTypeCheckboxes.forEach(checkbox => {
    formData.append('packaging_styles', checkbox.value);
  });

  fetch(`/preview_buy/${itemData.bucket_id}`, {
    method: 'POST',
    body: formData,
    headers: {
      'X-Requested-With': 'XMLHttpRequest'
    }
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        // Update modal with actual prices
        const avgPrice = data.average_price || 0;
        const totalCost = data.total_cost || 0;
        const totalQty = data.total_quantity || 0;
        const thirdPartyGrading = data.third_party_grading || false;
        const gradingFeePerUnit = data.grading_fee_per_unit || 0;
        const gradingFeeTotal = data.grading_fee_total || 0;
        const grandTotal = data.grand_total || totalCost;

        document.getElementById('buy-confirm-price').textContent = `$${avgPrice.toFixed(2)} USD (avg)`;
        document.getElementById('buy-confirm-quantity').textContent = totalQty;
        document.getElementById('buy-confirm-total').textContent = `$${totalCost.toFixed(2)} USD`;

        // Update grading fee display
        const gradingFeeRow = document.getElementById('buy-confirm-grading-fee-row');
        const gradingFeeEl = document.getElementById('buy-confirm-grading-fee');
        const grandTotalRow = document.getElementById('buy-confirm-grand-total-row');
        const grandTotalEl = document.getElementById('buy-confirm-grand-total');

        if (thirdPartyGrading && gradingFeeTotal > 0) {
          // Show grading fee row
          if (gradingFeeEl) {
            gradingFeeEl.textContent = `$${gradingFeeTotal.toFixed(2)} USD`;
          }
          if (gradingFeeRow) {
            gradingFeeRow.style.display = '';
          }
          // Show grand total row
          if (grandTotalEl) {
            grandTotalEl.textContent = `$${grandTotal.toFixed(2)} USD`;
          }
          if (grandTotalRow) {
            grandTotalRow.style.display = '';
          }
        } else {
          // Hide grading fee and grand total rows
          if (gradingFeeRow) {
            gradingFeeRow.style.display = 'none';
          }
          if (grandTotalRow) {
            grandTotalRow.style.display = 'none';
          }
        }

        // Store preview data for later use
        pendingBuyData.previewData = data;

        // Handle price lock for premium-to-spot listings
        if (data.has_price_lock && data.lock_expires_at) {
          // Store price lock data
          priceLockData = {
            has_price_lock: data.has_price_lock,
            price_locks: data.price_locks,
            lock_expires_at: data.lock_expires_at
          };

          // Start countdown timer
          startPriceLockCountdown(data.lock_expires_at);
        } else {
          // No price lock - hide timer section
          priceLockData = null;
          stopPriceLockCountdown();
        }
      } else {
        // Show error in modal
        document.getElementById('buy-confirm-price').textContent = 'Error';
        document.getElementById('buy-confirm-total').textContent = data.message || 'Unable to calculate';
      }
    })
    .catch(err => {
      console.error('Preview error:', err);
      document.getElementById('buy-confirm-price').textContent = 'Error';
      document.getElementById('buy-confirm-total').textContent = 'Unable to calculate';
    });
}

/**
 * Close confirmation modal
 */
function closeBuyItemConfirmModal() {
  const modal = document.getElementById('buyItemConfirmModal');
  if (!modal) return;

  // Stop price lock timer
  stopPriceLockCountdown();

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
    pendingBuyData = null;
    priceLockData = null;
  }, 300);
}

/**
 * Open success modal with order details
 * @param {Object} orderData - Order information from backend
 */
function openBuyItemSuccessModal(orderData) {
  const modal = document.getElementById('buyItemSuccessModal');
  if (!modal) return;

  // Calculate totals from orders array
  const totalQuantity = orderData.total_quantity || 0;
  const orders = orderData.orders || [];
  const totalAmount = orders.reduce((sum, order) => sum + order.total_price, 0);
  const avgPrice = totalQuantity > 0 ? totalAmount / totalQuantity : 0;

  // Get grading info
  const thirdPartyGrading = orderData.third_party_grading || false;
  const gradingFeeTotal = orderData.grading_fee_total || 0;
  const itemsTotal = totalAmount - gradingFeeTotal;

  // Populate summary (with comma formatting)
  modal.querySelector('#success-total-quantity').textContent = typeof formatQuantity === 'function' ? formatQuantity(totalQuantity) : totalQuantity;
  modal.querySelector('#success-avg-price').textContent = typeof formatPrice === 'function' ? `$${formatPrice(avgPrice, false)} USD` : `$${avgPrice.toFixed(2)} USD`;
  modal.querySelector('#success-total-amount').textContent = typeof formatPrice === 'function' ? `$${formatPrice(totalAmount, false)} USD` : `$${totalAmount.toFixed(2)} USD`;

  // Show/hide grading fee breakdown
  const successGradingFeeRow = modal.querySelector('#success-grading-fee-row');
  const successItemsTotalRow = modal.querySelector('#success-items-total-row');
  const successGradingCallout = modal.querySelector('#success-grading-callout');

  if (thirdPartyGrading && gradingFeeTotal > 0) {
    // Show items total row
    if (successItemsTotalRow) {
      const itemsTotalEl = successItemsTotalRow.querySelector('#success-items-total');
      if (itemsTotalEl) {
        itemsTotalEl.textContent = typeof formatPrice === 'function' ? `$${formatPrice(itemsTotal, false)} USD` : `$${itemsTotal.toFixed(2)} USD`;
      }
      successItemsTotalRow.style.display = '';
    }
    // Show grading fee row
    if (successGradingFeeRow) {
      const gradingFeeEl = successGradingFeeRow.querySelector('#success-grading-fee');
      if (gradingFeeEl) {
        gradingFeeEl.textContent = typeof formatPrice === 'function' ? `$${formatPrice(gradingFeeTotal, false)} USD` : `$${gradingFeeTotal.toFixed(2)} USD`;
      }
      successGradingFeeRow.style.display = '';
    }
    // Show grading callout
    if (successGradingCallout) {
      successGradingCallout.style.display = '';
    }
  } else {
    // Hide grading-related rows and callout
    if (successItemsTotalRow) successItemsTotalRow.style.display = 'none';
    if (successGradingFeeRow) successGradingFeeRow.style.display = 'none';
    if (successGradingCallout) successGradingCallout.style.display = 'none';
  }

  // Populate delivery address fields from structured data
  const deliveryAddress = orderData.delivery_address;
  if (deliveryAddress) {
    // Use modal.querySelector to ensure we target the correct modal's elements
    const line1El = modal.querySelector('#success-address-line1');
    const line2El = modal.querySelector('#success-address-line2');
    const cityEl = modal.querySelector('#success-address-city');
    const stateEl = modal.querySelector('#success-address-state');
    const zipEl = modal.querySelector('#success-address-zip');

    if (line1El) line1El.textContent = deliveryAddress.line1 || '—';
    if (line2El) {
      const line2 = deliveryAddress.line2 || '';
      line2El.textContent = line2.trim() ? line2 : '—';
    }
    if (cityEl) cityEl.textContent = deliveryAddress.city || '—';
    if (stateEl) stateEl.textContent = deliveryAddress.state || '—';
    if (zipEl) zipEl.textContent = deliveryAddress.zip || '—';
  } else {
    // No address provided - show all as dashes
    modal.querySelector('#success-address-line1').textContent = '—';
    modal.querySelector('#success-address-line2').textContent = '—';
    modal.querySelector('#success-address-city').textContent = '—';
    modal.querySelector('#success-address-state').textContent = '—';
    modal.querySelector('#success-address-zip').textContent = '—';
  }

  // Populate item specs (from bucket)
  const bucket = orderData.bucket || {};
  const specs = window.bucketSpecs || {};

  const specMap = {
    'success-buy-spec-metal': bucket.metal || specs.metal || '—',
    'success-buy-spec-product-line': bucket.product_line || specs.product_line || '—',
    'success-buy-spec-product-type': bucket.product_type || specs.product_type || '—',
    'success-buy-spec-weight': bucket.weight || specs.weight || '—',
    'success-buy-spec-grade': bucket.grade || specs.grade || '—',
    'success-buy-spec-year': bucket.year || specs.year || '—',
    'success-buy-spec-mint': bucket.mint || specs.mint || '—',
    'success-buy-spec-purity': bucket.purity || specs.purity || '—',
    'success-buy-spec-finish': bucket.finish || specs.finish || '—'
  };

  Object.entries(specMap).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) {
      const valueEl = el.querySelector('.spec-value');
      if (valueEl) valueEl.textContent = value;
    }
  });

  // Populate "3rd party graded" status based on buyer's TPG choice
  // This reflects whether the buyer requested third-party grading service for this order
  const gradingEl = document.getElementById('success-buy-spec-grading');
  if (gradingEl) {
    const gradingValueEl = gradingEl.querySelector('.spec-value');
    if (gradingValueEl) {
      // Use orderData.third_party_grading to determine if TPG service was requested
      const thirdPartyGradingRequested = orderData.third_party_grading || false;
      if (thirdPartyGradingRequested) {
        // Buyer requested TPG service
        gradingValueEl.textContent = 'Yes';
      } else {
        // Buyer did not request TPG service
        gradingValueEl.textContent = 'No';
      }
    }
  }

  // Show modal with animation
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });
}

/**
 * Close success modal
 */
function closeBuyItemSuccessModal() {
  const modal = document.getElementById('buyItemSuccessModal');
  if (!modal) return;

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
    // Reload page to show updated orders and inventory
    location.reload();
  }, 300);
}

/**
 * Handle confirmation button click - create order via AJAX
 */
function handleConfirmBuy() {
  if (!pendingBuyData) {
    console.error('No pending buy data found');
    return;
  }

  const confirmBtn = document.getElementById('confirmBuyBtn');
  if (!confirmBtn) return;

  // Disable button and show loading state
  confirmBtn.disabled = true;
  confirmBtn.textContent = 'Processing...';

  // Get selected delivery address
  const deliveryAddressSelect = document.getElementById('deliveryAddressSelect');
  const selectedAddressId = deliveryAddressSelect ? deliveryAddressSelect.value : '';

  // Validate address selection
  if (!selectedAddressId || selectedAddressId === 'add-new') {
    alert('Please select a delivery address before completing your purchase.');
    confirmBtn.disabled = false;
    confirmBtn.textContent = 'Yes, Complete Purchase';
    return;
  }

  // Prepare form data
  const formData = new FormData();
  formData.append('quantity', pendingBuyData.quantity);
  formData.append('address_id', selectedAddressId);

  // Include Random Year mode if enabled
  const randomYearToggle = document.getElementById('randomYearToggle');
  if (randomYearToggle && randomYearToggle.checked) {
    formData.append('random_year', '1');
  }

  // Include Third-Party Grading toggle if enabled
  const tpgToggle = document.getElementById('tpgToggle');
  if (tpgToggle && tpgToggle.checked) {
    formData.append('third_party_grading', '1');
  } else {
    formData.append('third_party_grading', '0');
  }

  // Include packaging filters (multi-select)
  const packagingTypeCheckboxes = document.querySelectorAll('.packaging-type-checkbox:checked');
  packagingTypeCheckboxes.forEach(checkbox => {
    formData.append('packaging_styles', checkbox.value);
  });

  // ✅ Include recipient name (source of truth for Buyer Name on Sold tiles)
  const recipientFirstInput = document.getElementById('buy-recipient-first');
  const recipientLastInput = document.getElementById('buy-recipient-last');
  if (recipientFirstInput) {
    formData.append('recipient_first', recipientFirstInput.value.trim());
  }
  if (recipientLastInput) {
    formData.append('recipient_last', recipientLastInput.value.trim());
  }

  // Include price lock IDs if we have them
  if (priceLockData && priceLockData.price_locks) {
    const lockIds = priceLockData.price_locks.map(lock => lock.lock_id).join(',');
    formData.append('price_lock_ids', lockIds);
  }

  // Submit via AJAX to direct_buy route
  fetch(`/direct_buy/${pendingBuyData.bucket_id}`, {
    method: 'POST',
    body: formData,
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
        // Check if user listings were skipped
        if (data.user_listings_skipped === true) {
          console.log('[BuyItemModal] User listings were skipped - showing notification modal');

          // Show notification modal (it will overlay the confirmation modal)
          if (typeof window.showOwnListingsSkippedModalFunc === 'function') {
            window.showOwnListingsSkippedModalFunc();

            // Set up one-time listener to proceed after notification modal closes
            const notificationModal = document.getElementById('ownListingsSkippedModal');
            const okBtn = document.getElementById('ownListingsSkippedOkBtn');

            const proceedAfterNotification = function() {
              console.log('[BuyItemModal] Notification acknowledged - proceeding with success modal');

              // Remove this listener
              if (okBtn) {
                okBtn.removeEventListener('click', proceedAfterNotification);
              }

              // Hide notification modal
              if (typeof window.hideOwnListingsSkippedModalFunc === 'function') {
                window.hideOwnListingsSkippedModalFunc();
              }

              // Now proceed with normal flow: close confirmation, show success
              setTimeout(() => {
                closeBuyItemConfirmModal();
                setTimeout(() => {
                  openBuyItemSuccessModal(data);
                }, 350);
              }, 300);
            };

            // Attach listener to OK button
            if (okBtn) {
              okBtn.addEventListener('click', proceedAfterNotification);
            }

            // Also handle background click to close notification
            if (notificationModal) {
              const handleBgClick = function(e) {
                if (e.target === notificationModal) {
                  notificationModal.removeEventListener('click', handleBgClick);
                  proceedAfterNotification();
                }
              };
              notificationModal.addEventListener('click', handleBgClick);
            }

            return; // Don't proceed with normal flow yet
          }
        }

        // Normal flow (no skipped listings): close confirmation modal, show success
        closeBuyItemConfirmModal();

        // Show success modal with order details
        setTimeout(() => {
          openBuyItemSuccessModal(data);
        }, 350);
      } else {
        // Check if this is a missing address error
        if (data.message && data.message.includes('shipping address')) {
          // Close confirmation modal and show address error modal
          closeBuyItemConfirmModal();
          setTimeout(() => {
            openBuyAddressErrorModal(data.message);
          }, 350);
        } else {
          // Show generic error alert for other errors
          alert(data.message || 'Failed to create order. Please try again.');
          closeBuyItemConfirmModal();
        }
      }
    })
    .catch(err => {
      console.error('Buy item error:', err);
      alert('An error occurred while creating your order. Please try again.');
      closeBuyItemConfirmModal();
    })
    .finally(() => {
      // Reset button
      if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Yes, Complete Purchase';
      }
    });
}

/**
 * Intercept buy form submission to show confirmation modal
 */
function interceptBuyForm() {
  // Find all buy item forms (could be multiple on page)
  const buyForms = document.querySelectorAll('form[action*="checkout"]');

  buyForms.forEach(form => {
    // Skip if already intercepted
    if (form.dataset.intercepted) return;
    form.dataset.intercepted = 'true';

    form.addEventListener('submit', (e) => {
      // Only intercept if this is a direct buy (not checkout page submit)
      const buyBtn = form.querySelector('.buy-btn');
      if (!buyBtn) return;

      e.preventDefault();

      // Sync quantity first (in case onClick didn't fire)
      const quantityInput = document.getElementById('quantityInput');
      const quantityHidden = form.querySelector('input[name="quantity"]');
      if (quantityInput && quantityHidden) {
        quantityHidden.value = quantityInput.value;
      }

      // Get form data
      const bucketId = form.querySelector('input[name="bucket_id"]')?.value;
      const quantity = form.querySelector('input[name="quantity"]')?.value || '1';

      // Get price from page (from cheapest listing or current price display)
      let price = window.lowestPrice || 0;

      // Alternative: Try to get from price display on page
      if (!price) {
        const priceEl = document.querySelector('.price-value');
        if (priceEl) {
          const priceText = priceEl.textContent.replace(/[^0-9.]/g, '');
          price = parseFloat(priceText) || 0;
        }
      }

      // Prepare item data
      const itemData = {
        form: form,
        bucket_id: bucketId,
        quantity: quantity,
        price: price
      };

      // Show confirmation modal
      openBuyItemConfirmModal(itemData);
    });
  });
}

/**
 * Initialize modal system
 */
document.addEventListener('DOMContentLoaded', () => {
  // Wire up confirmation button
  const confirmBtn = document.getElementById('confirmBuyBtn');
  if (confirmBtn) {
    confirmBtn.addEventListener('click', handleConfirmBuy);
  }

  // Intercept buy forms
  interceptBuyForm();

  // Close confirm modal on overlay click
  document.getElementById('buyItemConfirmModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'buyItemConfirmModal') {
      // Don't close if address modal or confirmation modal is open (higher z-index)
      const addressModal = document.getElementById('addressModal');
      const confirmModal = document.getElementById('saveAddressConfirmModal');

      const addressModalOpen = addressModal && addressModal.style.display === 'flex';
      const confirmModalOpen = confirmModal && confirmModal.style.display === 'flex';

      if (!addressModalOpen && !confirmModalOpen) {
        closeBuyItemConfirmModal();
      }
    }
  });

  // Close success modal on overlay click
  document.getElementById('buyItemSuccessModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'buyItemSuccessModal') {
      closeBuyItemSuccessModal();
    }
  });

  // Close payment modal on overlay click
  document.getElementById('buyItemPaymentModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'buyItemPaymentModal') {
      closeBuyPaymentModal();
    }
  });

  // Close modals on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      // Check if higher z-index modals are open first
      const addressModal = document.getElementById('addressModal');
      const confirmModal = document.getElementById('saveAddressConfirmModal');

      const addressModalOpen = addressModal && addressModal.style.display === 'flex';
      const confirmModalOpen = confirmModal && confirmModal.style.display === 'flex';

      // Only close Buy Item modals if no higher z-index modals are open
      if (!addressModalOpen && !confirmModalOpen) {
        closeBuyItemConfirmModal();
        closeBuyItemSuccessModal();
        closeBuyPaymentModal();
        closeBuyAddressErrorModal();
      }
      // If higher modals are open, let their own Escape handlers deal with them
    }
  });

  // Close address error modal on overlay click
  document.getElementById('buyItemAddressErrorModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'buyItemAddressErrorModal') {
      closeBuyAddressErrorModal();
    }
  });

  // Wire up delivery address dropdown change handler
  const deliveryAddressSelect = document.getElementById('deliveryAddressSelect');
  if (deliveryAddressSelect) {
    deliveryAddressSelect.addEventListener('change', handleAddressSelection);
  }
});

/**
 * Show payment selection modal
 */
function showBuyPaymentSelection() {
  // Close confirmation modal first
  const confirmModal = document.getElementById('buyItemConfirmModal');
  if (confirmModal) {
    confirmModal.classList.remove('active');
    setTimeout(() => {
      confirmModal.style.display = 'none';
    }, 300);
  }

  // Show payment modal
  setTimeout(() => {
    const paymentModal = document.getElementById('buyItemPaymentModal');
    if (paymentModal) {
      paymentModal.style.display = 'flex';
      requestAnimationFrame(() => {
        paymentModal.classList.add('active');
      });
    }
  }, 350);
}

/**
 * Close payment selection modal
 */
function closeBuyPaymentModal() {
  const modal = document.getElementById('buyItemPaymentModal');
  if (!modal) return;

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
  }, 300);
}

/**
 * Confirm payment method - returns to confirmation modal
 */
function confirmBuyPaymentMethod() {
  // Close payment modal
  const paymentModal = document.getElementById('buyItemPaymentModal');
  if (paymentModal) {
    paymentModal.classList.remove('active');
    setTimeout(() => {
      paymentModal.style.display = 'none';
    }, 300);
  }

  // Re-open confirmation modal
  setTimeout(() => {
    const confirmModal = document.getElementById('buyItemConfirmModal');
    if (confirmModal) {
      confirmModal.style.display = 'flex';
      requestAnimationFrame(() => {
        confirmModal.classList.add('active');
      });
    }
  }, 350);
}

/**
 * Open address error modal
 * @param {string} message - Error message to display
 */
function openBuyAddressErrorModal(message) {
  const modal = document.getElementById('buyItemAddressErrorModal');
  if (!modal) return;

  // Set custom message if provided
  const messageEl = document.getElementById('buyAddressErrorMessage');
  if (messageEl && message) {
    messageEl.textContent = message;
  }

  // Show modal with animation
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });
}

/**
 * Close address error modal
 */
function closeBuyAddressErrorModal() {
  const modal = document.getElementById('buyItemAddressErrorModal');
  if (!modal) return;

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
  }, 300);
}

/**
 * Open address modal from error modal
 * Redirects to account page with parameter to open address modal
 */
function openAddAddressFromBuyError() {
  // Redirect to account page with parameter to open address modal
  window.location.href = '/account?open_address_modal=true';
}

/**
 * Start countdown timer for price lock
 * @param {string} expiresAt - ISO timestamp when lock expires
 */
function startPriceLockCountdown(expiresAt) {
  // Clear any existing timer
  if (priceLockTimer) {
    clearInterval(priceLockTimer);
    priceLockTimer = null;
  }

  const timerEl = document.getElementById('priceLockTimer');
  const priceLockSection = document.getElementById('priceLockSection');
  const priceUpdateNotice = document.getElementById('priceUpdateNotice');

  if (!timerEl || !priceLockSection) return;

  // Show the price lock section
  priceLockSection.style.display = 'block';
  priceUpdateNotice.style.display = 'none';

  // Calculate time remaining
  const updateTimer = () => {
    const now = new Date();
    const expires = new Date(expiresAt);
    const remainingMs = expires - now;
    const remainingSec = Math.max(0, Math.ceil(remainingMs / 1000));

    timerEl.textContent = `${remainingSec}s`;

    if (remainingSec <= 0) {
      // Timer expired - refresh price lock
      clearInterval(priceLockTimer);
      priceLockTimer = null;
      refreshPriceLock();
    }
  };

  // Update immediately and then every second
  updateTimer();
  priceLockTimer = setInterval(updateTimer, 1000);
}

/**
 * Stop countdown timer
 */
function stopPriceLockCountdown() {
  if (priceLockTimer) {
    clearInterval(priceLockTimer);
    priceLockTimer = null;
  }

  const priceLockSection = document.getElementById('priceLockSection');
  if (priceLockSection) {
    priceLockSection.style.display = 'none';
  }
}

/**
 * Refresh price lock when timer expires
 * Triggers a full refresh: closes modal, fetches new prices, reopens modal
 */
function refreshPriceLock() {
  if (!pendingBuyData) return;

  console.log('[Price Lock] Timer expired - triggering full refresh');

  // Close the modal first
  const modal = document.getElementById('buyItemConfirmModal');
  if (modal) {
    modal.classList.remove('active');
  }

  // Prepare form data (same as original preview request)
  const formData = new FormData();
  formData.append('quantity', pendingBuyData.quantity);

  // Show loading state
  setTimeout(() => {
    if (modal) {
      modal.style.display = 'none';
    }

    // Fetch new prices and locks from backend
    fetch(`/refresh_price_lock/${pendingBuyData.bucket_id}`, {
      method: 'POST',
      body: formData,
      headers: {
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          console.log('[Price Lock] Refresh successful - reopening modal with new prices');

          // Store new price lock data
          if (data.has_price_lock && data.lock_expires_at) {
            priceLockData = {
              has_price_lock: data.has_price_lock,
              price_locks: data.price_locks,
              lock_expires_at: data.lock_expires_at
            };
          }

          // Store updated preview data
          pendingBuyData.previewData = data;

          // Reopen the modal with updated data
          // This will trigger a full re-render
          openBuyItemConfirmModalWithData(pendingBuyData, data);

          // Show the update notice
          setTimeout(() => {
            const priceUpdateNotice = document.getElementById('priceUpdateNotice');
            if (priceUpdateNotice) {
              priceUpdateNotice.style.display = 'block';
              // Hide notice after 5 seconds
              setTimeout(() => {
                priceUpdateNotice.style.display = 'none';
              }, 5000);
            }
          }, 500);
        } else {
          console.error('Price refresh failed:', data.message);
          alert('Price lock expired and refresh failed. Please click Buy again to get current prices.');
          pendingBuyData = null;
          priceLockData = null;
        }
      })
      .catch(err => {
        console.error('Price refresh error:', err);
        alert('Price lock expired and refresh failed. Please click Buy again to get current prices.');
        pendingBuyData = null;
        priceLockData = null;
      });
  }, 300); // Wait for modal close animation
}

/**
 * Open confirmation modal with pre-fetched data (used for refresh)
 * @param {Object} itemData - Item information
 * @param {Object} previewData - Pre-fetched preview data
 */
function openBuyItemConfirmModalWithData(itemData, previewData) {
  pendingBuyData = itemData;

  const modal = document.getElementById('buyItemConfirmModal');
  if (!modal) return;

  // Get bucket specs from window or use defaults
  const specs = window.bucketSpecs || {};

  // Populate item specifications
  document.getElementById('buy-spec-metal').textContent = specs['Metal'] || '—';
  document.getElementById('buy-spec-product-type').textContent = specs['Product type'] || '—';
  document.getElementById('buy-spec-weight').textContent = specs['Weight'] || '—';
  document.getElementById('buy-spec-purity').textContent = specs['Purity'] || '—';
  document.getElementById('buy-spec-mint').textContent = specs['Mint'] || '—';
  document.getElementById('buy-spec-year').textContent = specs['Year'] || '—';
  document.getElementById('buy-spec-finish').textContent = specs['Finish'] || '—';
  document.getElementById('buy-spec-grade').textContent = specs['Grading'] || '—';
  document.getElementById('buy-spec-product-line').textContent = specs['Product line'] || '—';

  // Populate "Requires 3rd Party Grading" field based on buyer's toggle choice
  // Check the TPG toggle state from the page
  const tpgToggle = document.getElementById('tpgToggle');
  const thirdPartyGradingRequested = tpgToggle && tpgToggle.checked;
  const requiresGrading = thirdPartyGradingRequested ? 'Yes' : 'No';
  document.getElementById('buy-spec-requires-grading').textContent = requiresGrading;

  // Conditionally show/hide grading service field (only show if listing is already graded)
  const gradingServiceRow = document.getElementById('buy-spec-grading-service-row');
  if ((specs.graded === 1 || specs.graded === '1') && specs.grading_service) {
    document.getElementById('buy-spec-grading-service').textContent = specs.grading_service;
    gradingServiceRow.style.display = '';
  } else {
    gradingServiceRow.style.display = 'none';
  }

  // Update modal with actual prices from previewData
  const avgPrice = previewData.average_price || 0;
  const totalCost = previewData.total_cost || 0;
  const totalQty = previewData.total_quantity || 0;

  document.getElementById('buy-confirm-price').textContent = `$${avgPrice.toFixed(2)} USD (avg)`;
  document.getElementById('buy-confirm-quantity').textContent = totalQty;
  document.getElementById('buy-confirm-total').textContent = `$${totalCost.toFixed(2)} USD`;

  // Show modal with animation
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });

  // Handle price lock for premium-to-spot listings
  if (previewData.has_price_lock && previewData.lock_expires_at) {
    // Start countdown timer
    startPriceLockCountdown(previewData.lock_expires_at);
  } else {
    // No price lock - hide timer section
    priceLockData = null;
    stopPriceLockCountdown();
  }
}

/**
 * Fetch and populate delivery addresses dropdown
 */
function fetchAndPopulateAddresses(selectAddressId = null) {
  const select = document.getElementById('deliveryAddressSelect');
  const noAddressMessage = document.getElementById('noAddressesMessage');

  if (!select) return;

  // Set loading state
  select.innerHTML = '<option value="">Loading addresses...</option>';
  select.disabled = true;

  // Fetch addresses from backend
  fetch('/account/get_addresses')
    .then(res => res.json())
    .then(data => {
      if (data.success && data.addresses && data.addresses.length > 0) {
        // Clear and populate dropdown
        select.innerHTML = '';

        // Add each address as an option
        data.addresses.forEach(addr => {
          const option = document.createElement('option');
          option.value = addr.id;

          // Format address label: "Name – Street, Apt, City, ST ZIP"
          let label = addr.name || 'Address';
          label += ' – ' + addr.street;

          if (addr.street_line2 && addr.street_line2.trim()) {
            label += ', ' + addr.street_line2;
          }

          label += ', ' + addr.city + ', ' + addr.state + ' ' + addr.zip_code;

          option.textContent = label;
          select.appendChild(option);
        });

        // Add "+ Add delivery address" option at bottom
        const addNewOption = document.createElement('option');
        addNewOption.value = 'add-new';
        addNewOption.textContent = '+ Add delivery address';
        select.appendChild(addNewOption);

        // If selectAddressId is provided, select it; otherwise select the first address
        if (selectAddressId) {
          select.value = selectAddressId;
        } else {
          select.selectedIndex = 0;
        }

        // Enable dropdown
        select.disabled = false;
        noAddressMessage.style.display = 'none';
      } else {
        // No addresses - show message but keep dropdown interactive
        select.innerHTML = '<option value="">No addresses available</option>';
        select.disabled = false; // ✅ Keep enabled so user can see it's not broken
        select.style.cursor = 'default'; // ✅ Normal cursor (not "not-allowed")
        noAddressMessage.style.display = 'block';
      }

      // Auto-populate recipient name fields from user profile (if fields exist)
      if (data.user_info) {
        const firstNameInput = document.getElementById('buy-recipient-first');
        const lastNameInput = document.getElementById('buy-recipient-last');
        if (firstNameInput && data.user_info.first_name) {
          firstNameInput.value = data.user_info.first_name;
        }
        if (lastNameInput && data.user_info.last_name) {
          lastNameInput.value = data.user_info.last_name;
        }
      }
    })
    .catch(err => {
      console.error('Error fetching addresses:', err);
      select.innerHTML = '<option value="">Error loading addresses</option>';
      select.disabled = true;
    });
}

/**
 * Handle address dropdown selection change
 */
function handleAddressSelection(event) {
  const select = event.target;

  if (select.value === 'add-new') {
    // User selected "+ Add delivery address" - open address modal
    // Reset selection to empty while modal is open
    select.value = '';

    // Open the address modal for adding new address
    if (typeof openAddAddressModal === 'function') {
      openAddAddressModal();
    } else {
      console.error('openAddAddressModal function not found');
      alert('Unable to open address form. Please ensure all required scripts are loaded.');
    }
  }
}

/**
 * Open the address modal from the Buy Confirm modal's "Add New Address" button
 */
function openAddAddressFromBuyConfirmModal() {
  console.log('[BuyItemModal] Opening address modal from Buy Confirm modal');

  // Set the callback context so the address modal knows to call our callback
  window.addressModalContext = 'buyModal';

  // Open the address modal
  openAddAddressModal();
}

/**
 * Callback after new address is saved (called from address modal)
 */
window.onAddressSavedFromBuyModal = function(newAddressId) {
  console.log('[BuyItemModal] Address saved, refreshing dropdown and selecting new address:', newAddressId);

  // Refresh the dropdown and select the newly created address
  fetchAndPopulateAddresses(newAddressId);
};

// Expose functions globally
window.openBuyItemConfirmModal = openBuyItemConfirmModal;
window.closeBuyItemConfirmModal = closeBuyItemConfirmModal;
window.openBuyItemSuccessModal = openBuyItemSuccessModal;
window.closeBuyItemSuccessModal = closeBuyItemSuccessModal;
window.showBuyPaymentSelection = showBuyPaymentSelection;
window.closeBuyPaymentModal = closeBuyPaymentModal;
window.confirmBuyPaymentMethod = confirmBuyPaymentMethod;
window.openBuyAddressErrorModal = openBuyAddressErrorModal;
window.closeBuyAddressErrorModal = closeBuyAddressErrorModal;
window.openAddAddressFromBuyError = openAddAddressFromBuyError;
window.openAddAddressFromBuyConfirmModal = openAddAddressFromBuyConfirmModal;
