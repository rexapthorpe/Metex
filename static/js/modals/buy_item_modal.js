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

  // Populate "Requires 3rd Party Grading" field (graded uses lowercase key)
  const requiresGrading = (specs.graded === 1 || specs.graded === '1') ? 'Yes' : 'No';
  document.getElementById('buy-spec-requires-grading').textContent = requiresGrading;

  // Conditionally show/hide grading service field (grading_service uses lowercase key)
  const gradingServiceRow = document.getElementById('buy-spec-grading-service-row');
  if ((specs.graded === 1 || specs.graded === '1') && specs.grading_service) {
    document.getElementById('buy-spec-grading-service').textContent = specs.grading_service;
    gradingServiceRow.style.display = '';
  } else {
    gradingServiceRow.style.display = 'none';
  }

  // Determine grading preference text
  let gradingText = 'Any (Graded or Ungraded)';
  if (itemData.graded_only === '1' || itemData.graded_only === 1) {
    if (itemData.pcgs === '1' || itemData.pcgs === 1) {
      gradingText = 'PCGS Graded Only';
    } else if (itemData.ngc === '1' || itemData.ngc === 1) {
      gradingText = 'NGC Graded Only';
    } else if (itemData.any_grader === '1' || itemData.any_grader === 1) {
      gradingText = 'Any Professional Grading';
    } else {
      gradingText = 'Graded Only';
    }
  }

  // Set loading state for purchase summary
  document.getElementById('buy-confirm-price').textContent = 'Calculating...';
  document.getElementById('buy-confirm-quantity').textContent = itemData.quantity;
  document.getElementById('buy-confirm-total').textContent = 'Calculating...';
  document.getElementById('buy-confirm-grading').textContent = gradingText;

  // Show modal with animation
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });

  // Fetch actual price breakdown from backend
  const formData = new FormData();
  formData.append('quantity', itemData.quantity);
  formData.append('graded_only', itemData.graded_only || '0');
  formData.append('any_grader', itemData.any_grader || '0');
  formData.append('pcgs', itemData.pcgs || '0');
  formData.append('ngc', itemData.ngc || '0');

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

        document.getElementById('buy-confirm-price').textContent = `$${avgPrice.toFixed(2)} USD (avg)`;
        document.getElementById('buy-confirm-quantity').textContent = totalQty;
        document.getElementById('buy-confirm-total').textContent = `$${totalCost.toFixed(2)} USD`;

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

  // Populate summary
  document.getElementById('success-total-quantity').textContent = totalQuantity;
  document.getElementById('success-avg-price').textContent = `$${avgPrice.toFixed(2)} USD`;
  document.getElementById('success-total-amount').textContent = `$${totalAmount.toFixed(2)} USD`;
  document.getElementById('success-shipping-address').textContent = orderData.shipping_address || '—';

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

  // Prepare form data
  const formData = new FormData();
  formData.append('quantity', pendingBuyData.quantity);
  formData.append('graded_only', pendingBuyData.graded_only || '0');
  formData.append('any_grader', pendingBuyData.any_grader || '0');
  formData.append('pcgs', pendingBuyData.pcgs || '0');
  formData.append('ngc', pendingBuyData.ngc || '0');

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
        // Close confirmation modal
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
      const gradedOnly = form.querySelector('input[name="graded_only"]')?.value;
      const anyGrader = form.querySelector('input[name="any_grader"]')?.value;
      const pcgs = form.querySelector('input[name="pcgs"]')?.value;
      const ngc = form.querySelector('input[name="ngc"]')?.value;

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
        price: price,
        graded_only: gradedOnly,
        any_grader: anyGrader,
        pcgs: pcgs,
        ngc: ngc
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
      closeBuyItemConfirmModal();
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
      closeBuyItemConfirmModal();
      closeBuyItemSuccessModal();
      closeBuyPaymentModal();
      closeBuyAddressErrorModal();
    }
  });

  // Close address error modal on overlay click
  document.getElementById('buyItemAddressErrorModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'buyItemAddressErrorModal') {
      closeBuyAddressErrorModal();
    }
  });
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
  formData.append('graded_only', pendingBuyData.graded_only || '0');
  formData.append('any_grader', pendingBuyData.any_grader || '0');
  formData.append('pcgs', pendingBuyData.pcgs || '0');
  formData.append('ngc', pendingBuyData.ngc || '0');

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

  const requiresGrading = (specs.graded === 1 || specs.graded === '1') ? 'Yes' : 'No';
  document.getElementById('buy-spec-requires-grading').textContent = requiresGrading;

  const gradingServiceRow = document.getElementById('buy-spec-grading-service-row');
  if ((specs.graded === 1 || specs.graded === '1') && specs.grading_service) {
    document.getElementById('buy-spec-grading-service').textContent = specs.grading_service;
    gradingServiceRow.style.display = '';
  } else {
    gradingServiceRow.style.display = 'none';
  }

  // Determine grading preference text
  let gradingText = 'Any (Graded or Ungraded)';
  if (itemData.graded_only === '1' || itemData.graded_only === 1) {
    if (itemData.pcgs === '1' || itemData.pcgs === 1) {
      gradingText = 'PCGS Graded Only';
    } else if (itemData.ngc === '1' || itemData.ngc === 1) {
      gradingText = 'NGC Graded Only';
    } else if (itemData.any_grader === '1' || itemData.any_grader === 1) {
      gradingText = 'Any Professional Grading';
    } else {
      gradingText = 'Graded Only';
    }
  }

  // Update modal with actual prices from previewData
  const avgPrice = previewData.average_price || 0;
  const totalCost = previewData.total_cost || 0;
  const totalQty = previewData.total_quantity || 0;

  document.getElementById('buy-confirm-price').textContent = `$${avgPrice.toFixed(2)} USD (avg)`;
  document.getElementById('buy-confirm-quantity').textContent = totalQty;
  document.getElementById('buy-confirm-total').textContent = `$${totalCost.toFixed(2)} USD`;
  document.getElementById('buy-confirm-grading').textContent = gradingText;

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
