/**
 * Cancel Order Modal JavaScript
 * Handles buyer cancellation requests and seller responses
 */

// Track current state
let currentCancelOrderId = null;
let currentSellerResponseOrderId = null;
let currentSellerResponseType = null;

/**
 * Open the cancel order modal for a buyer
 * @param {number} orderId - The order ID to cancel
 */
function openCancelOrderModal(orderId) {
  currentCancelOrderId = orderId;
  document.getElementById('cancelOrderId').value = orderId;
  document.getElementById('cancelOrderNumber').textContent = `#ORD-2026-${String(orderId).padStart(6, '0')}`;

  // Reset form
  const radios = document.querySelectorAll('input[name="cancelReason"]');
  radios.forEach(radio => radio.checked = false);
  document.getElementById('cancelAdditionalDetails').value = '';
  document.getElementById('cancelCharCount').textContent = '0';

  // Reset button state (not ready until reason selected)
  const submitBtn = document.getElementById('submitCancelBtn');
  submitBtn.classList.remove('ready');

  // Add event listeners for reason selection
  radios.forEach(radio => {
    radio.addEventListener('change', updateCancelButtonState);
  });

  // Show modal
  document.getElementById('cancelOrderModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

/**
 * Update the cancel button state based on whether a reason is selected
 */
function updateCancelButtonState() {
  const selectedReason = document.querySelector('input[name="cancelReason"]:checked');
  const submitBtn = document.getElementById('submitCancelBtn');

  if (selectedReason) {
    submitBtn.classList.add('ready');
  } else {
    submitBtn.classList.remove('ready');
  }
}

/**
 * Close the cancel order modal
 */
function closeCancelOrderModal() {
  document.getElementById('cancelOrderModal').style.display = 'none';
  document.body.style.overflow = '';
  currentCancelOrderId = null;

  // Reset success state
  const dialog = document.getElementById('cancelOrderDialog');
  const successContent = document.getElementById('cancelSuccessContent');

  if (dialog) {
    dialog.classList.remove('success');

    // Reset inline styles on form elements
    const header = dialog.querySelector('.cancel-order-header');
    const subtitle = dialog.querySelector('.cancel-order-subtitle');
    const warning = dialog.querySelector('.cancel-order-warning');
    const body = dialog.querySelector('.cancel-order-body');
    const footer = dialog.querySelector('.cancel-order-footer');

    if (header) header.style.display = '';
    if (subtitle) subtitle.style.display = '';
    if (warning) warning.style.display = '';
    if (body) body.style.display = '';
    if (footer) footer.style.display = '';
  }

  if (successContent) {
    successContent.classList.remove('show');
    successContent.style.display = 'none';
  }
}

/**
 * Show the cancel success animation
 */
function showCancelSuccessAnimation() {
  console.log('[CANCEL] showCancelSuccessAnimation called');

  const dialog = document.getElementById('cancelOrderDialog');
  const successContent = document.getElementById('cancelSuccessContent');

  console.log('[CANCEL] dialog:', dialog);
  console.log('[CANCEL] successContent:', successContent);

  if (!dialog || !successContent) {
    console.error('[CANCEL] Elements not found!');
    // Fallback: just show notification and close
    closeCancelOrderModal();
    showCancelNotification('success', 'Cancellation request submitted. Waiting for seller approval.');
    setTimeout(() => window.location.reload(), 1500);
    return;
  }

  // Hide all form elements
  const header = dialog.querySelector('.cancel-order-header');
  const subtitle = dialog.querySelector('.cancel-order-subtitle');
  const warning = dialog.querySelector('.cancel-order-warning');
  const body = dialog.querySelector('.cancel-order-body');
  const footer = dialog.querySelector('.cancel-order-footer');

  if (header) header.style.display = 'none';
  if (subtitle) subtitle.style.display = 'none';
  if (warning) warning.style.display = 'none';
  if (body) body.style.display = 'none';
  if (footer) footer.style.display = 'none';

  // Show success content
  successContent.style.display = 'flex';

  // Also add classes for CSS animations
  dialog.classList.add('success');
  successContent.classList.add('show');

  console.log('[CANCEL] Animation should be showing now');
}

/**
 * Close modal and refresh the page
 */
function closeCancelOrderModalAndRefresh() {
  closeCancelOrderModal();
  window.location.reload();
}

/**
 * Close modal when clicking on overlay
 */
function closeCancelOrderModalOnOverlay(event) {
  if (event.target.classList.contains('cancel-order-overlay')) {
    closeCancelOrderModal();
  }
}

/**
 * Update character count for additional details textarea
 */
function updateCancelCharCount() {
  const textarea = document.getElementById('cancelAdditionalDetails');
  const count = textarea.value.length;
  document.getElementById('cancelCharCount').textContent = count;
}

/**
 * Submit the cancellation request
 */
async function submitCancelOrder() {
  if (!currentCancelOrderId) {
    alert('Error: No order selected');
    return;
  }

  // Get selected reason
  const selectedReason = document.querySelector('input[name="cancelReason"]:checked');
  if (!selectedReason) {
    alert('Please select a reason for cancellation');
    return;
  }

  const reason = selectedReason.value;
  const additionalDetails = document.getElementById('cancelAdditionalDetails').value.trim();

  // Disable button and show loading
  const submitBtn = document.getElementById('submitCancelBtn');
  const originalText = submitBtn.innerHTML;
  submitBtn.disabled = true;
  submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Submitting...';

  try {
    const response = await fetch(`/api/orders/${currentCancelOrderId}/cancel`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({
        reason: reason,
        additional_details: additionalDetails
      })
    });

    const data = await response.json();
    console.log('[CANCEL] API response:', data);

    if (data.success) {
      console.log('[CANCEL] Success! Showing animation...');
      // Show success animation
      showCancelSuccessAnimation();
    } else {
      // Re-enable button on API error
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalText;
      alert(data.error || 'Failed to submit cancellation request');
    }
  } catch (error) {
    console.error('Error submitting cancellation:', error);
    // Re-enable button on exception
    submitBtn.disabled = false;
    submitBtn.innerHTML = originalText;
    alert('An error occurred. Please try again.');
  }
}

/**
 * Check if an order can be canceled (buyer-side)
 * @param {number} orderId - The order ID to check
 * @returns {Promise<object>} - Cancellation status info
 */
async function checkCancellationStatus(orderId) {
  try {
    const response = await fetch(`/api/orders/${orderId}/cancellation/status`, {
      headers: {
        'X-Requested-With': 'XMLHttpRequest'
      }
    });
    return await response.json();
  } catch (error) {
    console.error('Error checking cancellation status:', error);
    return { success: false, error: error.message };
  }
}

// ==========================================================================
// Seller Response Functions
// ==========================================================================

/**
 * Open seller response confirmation modal
 * @param {number} orderId - The order ID
 * @param {string} responseType - 'approve' or 'deny'
 * @param {string} reason - The buyer's cancellation reason
 */
function openSellerCancelResponseModal(orderId, responseType, reason) {
  currentSellerResponseOrderId = orderId;
  currentSellerResponseType = responseType;

  document.getElementById('sellerResponseOrderId').value = orderId;
  document.getElementById('sellerResponseType').value = responseType;
  document.getElementById('sellerResponseOrderNum').textContent = `#ORD-2026-${String(orderId).padStart(6, '0')}`;
  document.getElementById('sellerResponseReason').textContent = reason || 'Not specified';

  const icon = document.getElementById('sellerResponseIcon');
  const title = document.getElementById('sellerResponseTitle');
  const message = document.getElementById('sellerResponseMessage');
  const warning = document.getElementById('sellerResponseWarning');
  const confirmBtn = document.getElementById('confirmSellerResponseBtn');

  if (responseType === 'approve') {
    icon.innerHTML = '<i class="fa-solid fa-check"></i>';
    icon.style.background = '#ecfdf5';
    icon.style.color = '#10b981';
    title.textContent = 'Approve Cancellation';
    message.textContent = 'Are you sure you want to approve this cancellation request?';
    warning.className = 'seller-response-warning warning-approve';
    warning.innerHTML = '<i class="fa-solid fa-info-circle"></i> The order will only be canceled if all other sellers also approve. Your inventory will be restored if the cancellation is completed.';
    confirmBtn.className = 'btn-confirm-response approve';
    confirmBtn.textContent = 'Approve Cancellation';
  } else {
    icon.innerHTML = '<i class="fa-solid fa-xmark"></i>';
    icon.style.background = '#fef2f2';
    icon.style.color = '#ef4444';
    title.textContent = 'Deny Cancellation';
    message.textContent = 'Are you sure you want to deny this cancellation request?';
    warning.className = 'seller-response-warning warning-deny';
    warning.innerHTML = '<i class="fa-solid fa-exclamation-triangle"></i> Denying will immediately reject the entire cancellation request. The buyer will not be able to submit another cancellation request for this order.';
    confirmBtn.className = 'btn-confirm-response deny';
    confirmBtn.textContent = 'Deny Cancellation';
  }

  document.getElementById('sellerCancelResponseModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

/**
 * Close the seller response modal
 */
function closeSellerCancelResponseModal() {
  document.getElementById('sellerCancelResponseModal').style.display = 'none';
  document.body.style.overflow = '';
  currentSellerResponseOrderId = null;
  currentSellerResponseType = null;

  // Reset success states
  const dialog = document.getElementById('sellerResponseDialog');
  const approveSuccess = document.getElementById('sellerApproveSuccessContent');
  const denySuccess = document.getElementById('sellerDenySuccessContent');

  if (dialog) {
    dialog.classList.remove('success');

    // Reset inline styles on form elements
    const formElements = dialog.querySelectorAll('.seller-response-form-content');
    formElements.forEach(el => {
      el.style.display = '';
    });
  }

  if (approveSuccess) {
    approveSuccess.classList.remove('show');
    approveSuccess.style.display = 'none';
  }

  if (denySuccess) {
    denySuccess.classList.remove('show');
    denySuccess.style.display = 'none';
  }
}

/**
 * Close modal when clicking on overlay
 */
function closeSellerCancelResponseModalOnOverlay(event) {
  if (event.target.classList.contains('cancel-order-overlay')) {
    closeSellerCancelResponseModal();
  }
}

/**
 * Submit the seller's response (approve/deny)
 */
async function confirmSellerResponse() {
  if (!currentSellerResponseOrderId || !currentSellerResponseType) {
    alert('Error: Missing response information');
    return;
  }

  const confirmBtn = document.getElementById('confirmSellerResponseBtn');
  const originalText = confirmBtn.textContent;
  confirmBtn.disabled = true;
  confirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';

  try {
    const response = await fetch(`/api/orders/${currentSellerResponseOrderId}/cancel/respond`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({
        response: currentSellerResponseType === 'approve' ? 'approved' : 'denied'
      })
    });

    const data = await response.json();

    if (data.success) {
      // Show success animation based on response type
      showSellerResponseSuccessAnimation(currentSellerResponseType);
    } else {
      confirmBtn.disabled = false;
      confirmBtn.innerHTML = originalText;
      alert(data.error || 'Failed to submit response');
    }
  } catch (error) {
    console.error('Error submitting response:', error);
    confirmBtn.disabled = false;
    confirmBtn.innerHTML = originalText;
    alert('An error occurred. Please try again.');
  }
}

/**
 * Show the seller response success animation
 * @param {string} responseType - 'approve' or 'deny'
 */
function showSellerResponseSuccessAnimation(responseType) {
  console.log('[SELLER RESPONSE] showSellerResponseSuccessAnimation called:', responseType);

  const dialog = document.getElementById('sellerResponseDialog');
  const approveSuccess = document.getElementById('sellerApproveSuccessContent');
  const denySuccess = document.getElementById('sellerDenySuccessContent');

  if (!dialog) {
    console.error('[SELLER RESPONSE] Dialog not found!');
    closeSellerCancelResponseModalAndRefresh();
    return;
  }

  // Hide all form elements using inline styles for reliability
  const formElements = dialog.querySelectorAll('.seller-response-form-content');
  formElements.forEach(el => {
    el.style.display = 'none';
  });

  // Show the appropriate success content
  if (responseType === 'approve' && approveSuccess) {
    approveSuccess.style.display = 'flex';
    approveSuccess.classList.add('show');
  } else if (responseType === 'deny' && denySuccess) {
    denySuccess.style.display = 'flex';
    denySuccess.classList.add('show');
  }

  // Add success class to dialog
  dialog.classList.add('success');

  console.log('[SELLER RESPONSE] Animation should be showing now');
}

/**
 * Close seller response modal and refresh the page
 */
function closeSellerCancelResponseModalAndRefresh() {
  closeSellerCancelResponseModal();
  window.location.reload();
}

// ==========================================================================
// Utility Functions
// ==========================================================================

/**
 * Show a notification toast
 * @param {string} type - 'success', 'error', 'warning'
 * @param {string} message - The message to display
 */
function showCancelNotification(type, message) {
  // Check if there's an existing notification container
  let container = document.getElementById('cancelNotificationContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'cancelNotificationContainer';
    container.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 10001;
      max-width: 400px;
    `;
    document.body.appendChild(container);
  }

  const notification = document.createElement('div');
  notification.style.cssText = `
    background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#f59e0b'};
    color: white;
    padding: 14px 20px;
    border-radius: 10px;
    margin-bottom: 10px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    display: flex;
    align-items: center;
    gap: 10px;
    animation: slideInRight 0.3s ease;
  `;

  const icon = type === 'success' ? 'fa-check-circle' :
               type === 'error' ? 'fa-exclamation-circle' : 'fa-exclamation-triangle';

  notification.innerHTML = `
    <i class="fa-solid ${icon}"></i>
    <span>${message}</span>
  `;

  container.appendChild(notification);

  // Add animation keyframes if not exists
  if (!document.getElementById('cancelNotificationStyles')) {
    const style = document.createElement('style');
    style.id = 'cancelNotificationStyles';
    style.textContent = `
      @keyframes slideInRight {
        from {
          opacity: 0;
          transform: translateX(100px);
        }
        to {
          opacity: 1;
          transform: translateX(0);
        }
      }
    `;
    document.head.appendChild(style);
  }

  // Auto-remove after 4 seconds
  setTimeout(() => {
    notification.style.opacity = '0';
    notification.style.transform = 'translateX(100px)';
    notification.style.transition = 'all 0.3s ease';
    setTimeout(() => notification.remove(), 300);
  }, 4000);
}

/**
 * Format order ID for display
 * @param {number} orderId - The order ID
 * @returns {string} - Formatted order number
 */
function formatOrderNumber(orderId) {
  return `#ORD-2026-${String(orderId).padStart(6, '0')}`;
}

// Close modals on Escape key
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    if (document.getElementById('cancelOrderModal').style.display === 'flex') {
      closeCancelOrderModal();
    }
    if (document.getElementById('sellerCancelResponseModal').style.display === 'flex') {
      closeSellerCancelResponseModal();
    }
  }
});
