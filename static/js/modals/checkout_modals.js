// static/js/modals/checkout_modals.js
'use strict';

/* ==========================================================================
   Checkout Modals - Three-step flow
   1. Fetch cart data and show order summary modal
   2. Show payment selection modal
   3. Submit order via AJAX and show success modal
   ========================================================================== */

let checkoutCartData = null;

/**
 * Open checkout modal - fetches cart data and displays order summary
 */
async function openCheckoutModal() {
  try {
    // Fetch cart data from backend
    const response = await fetch('/api/cart-data', {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      }
    });

    if (!response.ok) {
      throw new Error('Failed to fetch cart data');
    }

    const data = await response.json();

    if (!data.success) {
      alert(data.message || 'Unable to load cart data');
      return;
    }

    // Store cart data
    checkoutCartData = data;

    // Populate order summary
    populateOrderSummary(data.buckets, data.cart_total);

    // Show modal with animation
    const modal = document.getElementById('checkoutOrderSummaryModal');
    if (modal) {
      modal.style.display = 'flex';
      requestAnimationFrame(() => {
        modal.classList.add('active');
      });
    }
  } catch (err) {
    console.error('Error opening checkout modal:', err);
    alert('An error occurred while loading your cart. Please try again.');
  }
}

/**
 * Populate order summary with cart items
 * @param {Object} buckets - Cart buckets data
 * @param {Number} cartTotal - Total cart value
 */
function populateOrderSummary(buckets, cartTotal) {
  const container = document.getElementById('checkoutOrderItems');
  const totalElement = document.getElementById('checkoutTotalValue');

  if (!container || !totalElement) return;

  // Clear existing items
  container.innerHTML = '';

  // Create item cards for each bucket
  Object.entries(buckets).forEach(([bucketId, bucket]) => {
    const itemCard = document.createElement('div');
    itemCard.className = 'order-item-card';

    const category = bucket.category;

    // Build grading service row conditionally
    const gradingServiceRow = (category.graded === 1 || category.graded === '1') && category.grading_service
      ? `<div class="spec-row">
          <span class="spec-label">Grading Service:</span>
          <span class="spec-value">${category.grading_service}</span>
        </div>`
      : '';

    itemCard.innerHTML = `
      <div class="item-card-header">
        <h3 class="item-card-title">${category.metal} ${category.product_type}</h3>
      </div>

      <div class="item-specs-grid">
        <div class="spec-row">
          <span class="spec-label">Weight:</span>
          <span class="spec-value">${category.weight}</span>
        </div>
        <div class="spec-row">
          <span class="spec-label">Purity:</span>
          <span class="spec-value">${category.purity || '—'}</span>
        </div>
        <div class="spec-row">
          <span class="spec-label">Mint:</span>
          <span class="spec-value">${category.mint}</span>
        </div>
        <div class="spec-row">
          <span class="spec-label">Year:</span>
          <span class="spec-value">${category.year}</span>
        </div>
        <div class="spec-row">
          <span class="spec-label">Finish:</span>
          <span class="spec-value">${category.finish}</span>
        </div>
        <div class="spec-row">
          <span class="spec-label">Grade:</span>
          <span class="spec-value">${category.grade}</span>
        </div>
        <div class="spec-row">
          <span class="spec-label">Product Line:</span>
          <span class="spec-value">${category.product_line || '—'}</span>
        </div>
        <div class="spec-row">
          <span class="spec-label">Requires 3rd Party Grading:</span>
          <span class="spec-value">${(category.graded === 1 || category.graded === '1') ? 'Yes' : 'No'}</span>
        </div>
        ${gradingServiceRow}
      </div>

      <div class="item-pricing-section">
        <div class="pricing-row">
          <span class="pricing-label">Quantity:</span>
          <span class="pricing-value">${bucket.total_qty}</span>
        </div>
        <div class="pricing-row">
          <span class="pricing-label">Average Price:</span>
          <span class="pricing-value">$${bucket.avg_price.toFixed(2)}</span>
        </div>
        <div class="pricing-row item-total-row">
          <span class="pricing-label">Item Total:</span>
          <span class="pricing-value">$${bucket.total_price.toFixed(2)}</span>
        </div>
      </div>
    `;

    container.appendChild(itemCard);
  });

  // Update total
  totalElement.textContent = `$${cartTotal.toFixed(2)}`;
}

/**
 * Close checkout order summary modal
 */
function closeCheckoutModal() {
  const modal = document.getElementById('checkoutOrderSummaryModal');
  if (!modal) return;

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
    checkoutCartData = null;
  }, 300);
}

/**
 * Show payment selection modal
 */
function showPaymentSelection() {
  // Close order summary modal first
  const summaryModal = document.getElementById('checkoutOrderSummaryModal');
  if (summaryModal) {
    summaryModal.classList.remove('active');
    setTimeout(() => {
      summaryModal.style.display = 'none';
    }, 300);
  }

  // Show payment modal
  setTimeout(() => {
    const paymentModal = document.getElementById('checkoutPaymentModal');
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
function closePaymentModal() {
  const modal = document.getElementById('checkoutPaymentModal');
  if (!modal) return;

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
  }, 300);
}

/**
 * Confirm payment method - returns to order summary
 */
function confirmPaymentMethod() {
  // Close payment modal
  const paymentModal = document.getElementById('checkoutPaymentModal');
  if (paymentModal) {
    paymentModal.classList.remove('active');
    setTimeout(() => {
      paymentModal.style.display = 'none';
    }, 300);
  }

  // Re-open order summary modal
  setTimeout(() => {
    const summaryModal = document.getElementById('checkoutOrderSummaryModal');
    if (summaryModal) {
      summaryModal.style.display = 'flex';
      requestAnimationFrame(() => {
        summaryModal.classList.add('active');
      });
    }
  }, 350);
}

/**
 * Handle confirm checkout - submit order via AJAX
 */
async function handleConfirmCheckout() {
  const confirmBtn = document.getElementById('confirmCheckoutBtn');
  if (!confirmBtn) return;

  // Disable button and show loading state
  confirmBtn.disabled = true;
  confirmBtn.textContent = 'Processing Order...';

  try {
    // Submit order via AJAX
    const response = await fetch('/checkout', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({
        shipping_address: 'Default Address' // TODO: Get from user input/saved address
      })
    });

    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      throw new Error('Server returned non-JSON response');
    }

    const data = await response.json();

    if (data.success) {
      // Close order summary modal
      closeCheckoutModal();

      // Show success modal with order details
      setTimeout(() => {
        openSuccessModal(data);
      }, 350);
    } else {
      alert(data.message || 'Failed to process order. Please try again.');
    }
  } catch (err) {
    console.error('Checkout error:', err);
    alert('An error occurred while processing your order. Please try again.');
  } finally {
    // Reset button
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.textContent = 'Confirm';
    }
  }
}

/**
 * Open success modal with order details
 * @param {Object} data - Response data from backend
 */
function openSuccessModal(data) {
  const modal = document.getElementById('checkoutSuccessModal');
  if (!modal) return;

  // Populate success modal
  document.getElementById('success-order-id').textContent = data.order_id || '—';
  document.getElementById('success-total-items').textContent = data.total_items || '—';
  document.getElementById('success-order-total').textContent = data.order_total
    ? `$${parseFloat(data.order_total).toFixed(2)}`
    : '—';

  // Show modal with animation
  modal.style.display = 'flex';
  requestAnimationFrame(() => {
    modal.classList.add('active');
  });
}

/**
 * Close success modal and refresh page to update cart
 */
function closeSuccessModal() {
  const modal = document.getElementById('checkoutSuccessModal');
  if (!modal) return;

  modal.classList.remove('active');
  setTimeout(() => {
    modal.style.display = 'none';
    // Reload page to refresh cart
    window.location.reload();
  }, 300);
}

/**
 * Initialize checkout modal system
 */
document.addEventListener('DOMContentLoaded', () => {
  // Wire up confirm checkout button
  const confirmBtn = document.getElementById('confirmCheckoutBtn');
  if (confirmBtn) {
    confirmBtn.addEventListener('click', handleConfirmCheckout);
  }

  // Close modals on overlay click
  document.getElementById('checkoutOrderSummaryModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'checkoutOrderSummaryModal') {
      closeCheckoutModal();
    }
  });

  document.getElementById('checkoutPaymentModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'checkoutPaymentModal') {
      closePaymentModal();
    }
  });

  document.getElementById('checkoutSuccessModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'checkoutSuccessModal') {
      closeSuccessModal();
    }
  });

  // Close modals on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeCheckoutModal();
      closePaymentModal();
      closeSuccessModal();
    }
  });
});

// Expose functions globally
window.openCheckoutModal = openCheckoutModal;
window.closeCheckoutModal = closeCheckoutModal;
window.showPaymentSelection = showPaymentSelection;
window.closePaymentModal = closePaymentModal;
window.confirmPaymentMethod = confirmPaymentMethod;
window.closeSuccessModal = closeSuccessModal;
