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

  // Hide the modal
  modal.style.display = 'none';

  // Re-enable body scroll
  document.body.style.overflow = '';

  // Remove keyboard listener
  document.removeEventListener('keydown', handleEscapeKey);

  // Remove click-outside listener
  modal.removeEventListener('click', handleOutsideClick);
}

/**
 * Handles Escape key press to close modal
 * @param {KeyboardEvent} event - The keyboard event
 */
function handleEscapeKey(event) {
  if (event.key === 'Escape') {
    // Find which modal is open and close it
    const termsModal = document.getElementById('termsModal');
    const privacyModal = document.getElementById('privacyModal');

    if (termsModal && termsModal.style.display === 'flex') {
      closeLegalModal('termsModal');
    } else if (privacyModal && privacyModal.style.display === 'flex') {
      closeLegalModal('privacyModal');
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
  // Find all links with href="#terms" or href="#privacy"
  const termsLinks = document.querySelectorAll('a[href="#terms"]');
  const privacyLinks = document.querySelectorAll('a[href="#privacy"]');

  // Attach click handlers to Terms of Service links
  termsLinks.forEach(link => {
    link.addEventListener('click', function(event) {
      event.preventDefault();
      openLegalModal('termsModal');
    });
  });

  // Attach click handlers to Privacy Policy links
  privacyLinks.forEach(link => {
    link.addEventListener('click', function(event) {
      event.preventDefault();
      openLegalModal('privacyModal');
    });
  });
});
