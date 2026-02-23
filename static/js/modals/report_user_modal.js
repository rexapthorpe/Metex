// static/js/modals/report_user_modal.js

// State variables
let reportTargetUserId = null;
let reportTargetUsername = null;
let reportOrderId = null;
let reportAttachments = [];

/**
 * Open the Report User modal
 * @param {number} userId - The ID of the user being reported
 * @param {string} username - The username of the user being reported
 * @param {number} orderId - The order ID related to this report
 */
function openReportUserModal(userId, username, orderId) {
  reportTargetUserId = userId;
  reportTargetUsername = username;
  reportOrderId = orderId;
  reportAttachments = [];

  // Update modal content
  const usernameEl = document.getElementById('reportUserUsername');
  const orderBadgeEl = document.getElementById('reportOrderBadge');

  if (usernameEl) {
    usernameEl.textContent = `@${username}`;
  }

  if (orderBadgeEl) {
    const year = new Date().getFullYear();
    orderBadgeEl.textContent = `Order #ORD-${year}-${String(orderId).padStart(6, '0')}`;
  }

  // Clear previous state
  clearReportForm();

  // Show modal
  const modal = document.getElementById('reportUserModal');
  if (modal) {
    modal.style.display = 'flex';
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');

    // Add outside click listener
    modal.addEventListener('click', reportOutsideClickListener);
  }
}

/**
 * Close the Report User modal
 */
function closeReportUserModal() {
  const modal = document.getElementById('reportUserModal');
  const dialog = document.getElementById('reportUserDialog');
  const successContent = document.getElementById('reportSuccessContent');

  if (modal) {
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
    modal.style.display = 'none';
    modal.removeEventListener('click', reportOutsideClickListener);
  }

  // Reset success state
  if (dialog) {
    dialog.classList.remove('success');
  }
  if (successContent) {
    successContent.classList.remove('show');
    successContent.style.display = 'none';
  }

  // Reset form content visibility
  const formElements = document.querySelectorAll('#reportUserDialog .report-form-content');
  formElements.forEach(el => {
    el.style.display = '';
  });

  // Clear state
  reportTargetUserId = null;
  reportTargetUsername = null;
  reportOrderId = null;
  reportAttachments = [];
}

/**
 * Close the Report User modal and refresh the page
 */
function closeReportUserModalAndRefresh() {
  closeReportUserModal();
  window.location.reload();
}

/**
 * Show the report success animation
 */
function showReportSuccessAnimation() {
  const dialog = document.getElementById('reportUserDialog');
  const successContent = document.getElementById('reportSuccessContent');

  if (!dialog || !successContent) {
    // Fallback: just close and show toast
    closeReportUserModal();
    showReportToast('Report submitted successfully.', 'success');
    return;
  }

  // Hide all form elements
  const formElements = dialog.querySelectorAll('.report-form-content');
  formElements.forEach(el => {
    el.style.display = 'none';
  });

  // Show success content
  successContent.style.display = 'flex';
  successContent.classList.add('show');

  // Add success class to dialog
  dialog.classList.add('success');
}

/**
 * Handle clicks outside the modal content
 */
function reportOutsideClickListener(e) {
  if (e.target && e.target.id === 'reportUserModal') {
    closeReportUserModal();
  }
}

/**
 * Clear the report form
 */
function clearReportForm() {
  // Clear reason selection
  const reasonInputs = document.querySelectorAll('input[name="report_reason"]');
  reasonInputs.forEach(input => {
    input.checked = false;
  });

  // Clear comment
  const commentEl = document.getElementById('reportComment');
  if (commentEl) {
    commentEl.value = '';
  }

  // Update char count
  updateReportCharCount();

  // Clear attachments
  reportAttachments = [];
  const previewEl = document.getElementById('reportAttachmentsPreview');
  if (previewEl) {
    previewEl.innerHTML = '';
  }

  // Clear file input
  const fileInput = document.getElementById('reportPhotoInput');
  if (fileInput) {
    fileInput.value = '';
  }
}

/**
 * Update the character count for the comment textarea
 */
function updateReportCharCount() {
  const commentEl = document.getElementById('reportComment');
  const countEl = document.getElementById('reportCharCount');

  if (commentEl && countEl) {
    countEl.textContent = commentEl.value.length;
  }
}

/**
 * Handle photo file selection
 */
function handleReportPhotoSelect(event) {
  const files = event.target.files;
  if (!files || files.length === 0) return;

  for (let i = 0; i < files.length; i++) {
    const file = files[i];

    // Validate file type
    if (!file.type.match(/^image\/(png|jpeg|jpg|webp)$/)) {
      continue;
    }

    // Validate file size (10MB max)
    if (file.size > 10 * 1024 * 1024) {
      alert(`File "${file.name}" is too large. Maximum size is 10MB.`);
      continue;
    }

    // Add to attachments
    reportAttachments.push(file);

    // Create preview
    addPhotoPreview(file);
  }

  // Clear the input so the same file can be selected again
  event.target.value = '';
}

/**
 * Add a photo preview to the attachments section
 */
function addPhotoPreview(file) {
  const previewEl = document.getElementById('reportAttachmentsPreview');
  if (!previewEl) return;

  const reader = new FileReader();
  reader.onload = function (e) {
    const index = reportAttachments.indexOf(file);
    const itemEl = document.createElement('div');
    itemEl.className = 'report-attachment-item';
    itemEl.dataset.index = index;

    itemEl.innerHTML = `
      <img src="${e.target.result}" alt="Attachment">
      <button type="button" class="report-attachment-remove" onclick="removeReportAttachment(${index})">
        <i class="fa-solid fa-xmark"></i>
      </button>
    `;

    previewEl.appendChild(itemEl);
  };

  reader.readAsDataURL(file);
}

/**
 * Remove an attachment by index
 */
function removeReportAttachment(index) {
  // Remove from array
  reportAttachments.splice(index, 1);

  // Re-render previews
  renderAttachmentPreviews();
}

/**
 * Re-render all attachment previews
 */
function renderAttachmentPreviews() {
  const previewEl = document.getElementById('reportAttachmentsPreview');
  if (!previewEl) return;

  previewEl.innerHTML = '';

  reportAttachments.forEach((file, index) => {
    const reader = new FileReader();
    reader.onload = function (e) {
      const itemEl = document.createElement('div');
      itemEl.className = 'report-attachment-item';
      itemEl.dataset.index = index;

      itemEl.innerHTML = `
        <img src="${e.target.result}" alt="Attachment">
        <button type="button" class="report-attachment-remove" onclick="removeReportAttachment(${index})">
          <i class="fa-solid fa-xmark"></i>
        </button>
      `;

      previewEl.appendChild(itemEl);
    };

    reader.readAsDataURL(file);
  });
}

/**
 * Submit the report
 */
function submitReport() {
  // Validate reason is selected
  const selectedReason = document.querySelector('input[name="report_reason"]:checked');
  if (!selectedReason) {
    alert('Please select a reason for your report.');
    return;
  }

  const reason = selectedReason.value;
  const comment = document.getElementById('reportComment')?.value?.trim() || '';

  // Build form data
  const formData = new FormData();
  formData.append('reported_user_id', reportTargetUserId);
  formData.append('order_id', reportOrderId);
  formData.append('reason', reason);
  formData.append('comment', comment);

  // Add attachments
  reportAttachments.forEach((file, index) => {
    formData.append(`attachment_${index}`, file);
  });

  // Disable submit button
  const submitBtn = document.querySelector('.report-user-btn-submit');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Submitting...';
  }

  // Submit to API
  fetch('/api/reports/create', {
    method: 'POST',
    body: formData
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        // Also close the sellers modal if open
        if (typeof closeOrderSellerPopup === 'function') {
          closeOrderSellerPopup();
        }
        if (typeof closeSoldBuyerPopup === 'function') {
          closeSoldBuyerPopup();
        }

        // Show success animation
        showReportSuccessAnimation();
      } else {
        alert(data.error || 'Failed to submit report. Please try again.');
      }
    })
    .catch(err => {
      console.error('[Report User Modal] Error:', err);
      alert('Failed to submit report. Please try again.');
    })
    .finally(() => {
      // Re-enable submit button
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa-solid fa-flag"></i> Submit Report';
      }
    });
}

/**
 * Show a toast notification
 */
function showReportToast(message, type = 'info') {
  // Check if there's already a toast container
  let toastContainer = document.getElementById('reportToastContainer');
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'reportToastContainer';
    toastContainer.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 100000;
      display: flex;
      flex-direction: column;
      gap: 10px;
    `;
    document.body.appendChild(toastContainer);
  }

  const toast = document.createElement('div');
  toast.style.cssText = `
    padding: 14px 20px;
    background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
    color: #ffffff;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    font-size: 14px;
    font-weight: 500;
    max-width: 320px;
    animation: slideIn 0.3s ease;
  `;
  toast.textContent = message;

  // Add animation keyframes if not already added
  if (!document.getElementById('reportToastStyles')) {
    const style = document.createElement('style');
    style.id = 'reportToastStyles';
    style.textContent = `
      @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
      }
      @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
      }
    `;
    document.head.appendChild(style);
  }

  toastContainer.appendChild(toast);

  // Remove toast after delay
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease forwards';
    setTimeout(() => {
      toast.remove();
    }, 300);
  }, 4000);
}

// Export functions globally
window.openReportUserModal = openReportUserModal;
window.closeReportUserModal = closeReportUserModal;
window.closeReportUserModalAndRefresh = closeReportUserModalAndRefresh;
window.showReportSuccessAnimation = showReportSuccessAnimation;
window.updateReportCharCount = updateReportCharCount;
window.handleReportPhotoSelect = handleReportPhotoSelect;
window.removeReportAttachment = removeReportAttachment;
window.submitReport = submitReport;
