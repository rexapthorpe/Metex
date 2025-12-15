// static/js/checkout.js
'use strict';

/* ==========================================================================
   CHECKOUT MODAL - Sliding Two-View System
   ========================================================================== */

/**
 * Show the payment view (slide to payment selection)
 */
function showPaymentView() {
  const sliderContainer = document.querySelector('.checkout-slider-container');
  if (sliderContainer) {
    sliderContainer.classList.add('show-payment');
  }
}

/**
 * Show the order summary view (slide back from payment)
 */
function showOrderSummary() {
  const sliderContainer = document.querySelector('.checkout-slider-container');
  if (sliderContainer) {
    sliderContainer.classList.remove('show-payment');
  }
}

/**
 * Close the checkout modal (navigate back to cart)
 */
function closeCheckout() {
  if (confirm('Are you sure you want to close checkout? Your items will remain in the cart.')) {
    window.location.href = '/view_cart';  // Fixed: correct route
  }
}

/**
 * Initialize checkout modal
 */
document.addEventListener('DOMContentLoaded', () => {
  // Start on order summary view
  showOrderSummary();

  // Close modal on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const sliderContainer = document.querySelector('.checkout-slider-container');
      if (sliderContainer && sliderContainer.classList.contains('show-payment')) {
        // If on payment view, go back to summary
        showOrderSummary();
      } else {
        // If on summary view, close modal
        closeCheckout();
      }
    }
  });

  // Close modal on overlay click
  const modalOverlay = document.querySelector('.checkout-modal-overlay');
  if (modalOverlay) {
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) {
        closeCheckout();
      }
    });
  }
});

// Expose functions globally
window.showPaymentView = showPaymentView;
window.showOrderSummary = showOrderSummary;
window.closeCheckout = closeCheckout;
