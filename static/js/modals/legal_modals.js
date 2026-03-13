/**
 * Legal Modals JavaScript
 * Handles opening/closing Terms of Service and Privacy Policy modals
 */

/**
 * Opens a legal modal (Terms or Privacy)
 * @param {string} modalId - The ID of the modal to open ('termsModal' or 'privacyModal')
 */
function openLegalModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) {
    console.error(`Modal with ID "${modalId}" not found`);
    return;
  }

  // Display the modal
  modal.style.display = 'flex';

  // Prevent body scroll when modal is open
  document.body.style.overflow = 'hidden';

  // Scroll modal content to top
  const modalBody = modal.querySelector('.modal-body');
  if (modalBody) {
    modalBody.scrollTop = 0;
  }

  // Add keyboard listener for Escape key
  document.addEventListener('keydown', handleEscapeKey);

  // Add click-outside-to-close listener
  modal.addEventListener('click', handleOutsideClick);
}

/**
 * Closes a legal modal
 * @param {string} modalId - The ID of the modal to close ('termsModal' or 'privacyModal')
 */
function closeLegalModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) {
    console.error(`Modal with ID "${modalId}" not found`);
    return;
  }

  // Remove keyboard listener
  document.removeEventListener('keydown', handleEscapeKey);

  // Remove click-outside listener
  modal.removeEventListener('click', handleOutsideClick);

  // Re-enable body scroll
  document.body.style.overflow = '';

  window.animatedModalClose(modal, function() { modal.style.display = 'none'; });
}

/**
 * Handles Escape key press to close modal
 * @param {KeyboardEvent} event - The keyboard event
 */
function handleEscapeKey(event) {
  if (event.key === 'Escape') {
    const modalIds = ['termsModal', 'privacyModal', 'authenticityModal', 'marketPriceModal', 'shippingDisputesModal'];
    for (const id of modalIds) {
      const modal = document.getElementById(id);
      if (modal && modal.style.display === 'flex') {
        closeLegalModal(id);
        break;
      }
    }
  }
}

/**
 * Handles click outside modal to close it
 * @param {MouseEvent} event - The click event
 */
function handleOutsideClick(event) {
  const modalDialog = event.target.querySelector('.legal-modal-dialog');

  // If click is on the overlay (not inside the modal dialog), close it
  if (event.target === event.currentTarget) {
    const modalId = event.currentTarget.id;
    closeLegalModal(modalId);
  }
}

/**
 * Initialize legal modal triggers on page load
 */
document.addEventListener('DOMContentLoaded', function() {
  const linkModalMap = {
    '#terms': 'termsModal',
    '#privacy': 'privacyModal',
    '#authenticity': 'authenticityModal',
    '#market-price': 'marketPriceModal',
    '#shipping-disputes': 'shippingDisputesModal',
  };

  Object.entries(linkModalMap).forEach(([href, modalId]) => {
    document.querySelectorAll(`a[href="${href}"]`).forEach(link => {
      link.addEventListener('click', function(event) {
        event.preventDefault();
        openLegalModal(modalId);
      });
    });
  });
});
