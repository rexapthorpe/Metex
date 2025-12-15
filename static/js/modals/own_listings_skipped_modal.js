// static/js/modals/own_listings_skipped_modal.js
'use strict';

/**
 * Show "Own Listings Skipped" notification modal
 */
function showOwnListingsSkippedModal() {
    const modal = document.getElementById('ownListingsSkippedModal');
    if (!modal) {
        console.error('[OwnListingsSkippedModal] Modal element not found!');
        return;
    }

    console.log('[OwnListingsSkippedModal] Showing modal');
    modal.style.display = 'flex';

    // Add fade-in animation
    setTimeout(() => {
        modal.classList.add('show');
    }, 10);
}

/**
 * Hide "Own Listings Skipped" notification modal
 */
function hideOwnListingsSkippedModal() {
    const modal = document.getElementById('ownListingsSkippedModal');
    if (!modal) {
        return;
    }

    console.log('[OwnListingsSkippedModal] Hiding modal');
    modal.classList.remove('show');

    setTimeout(() => {
        modal.style.display = 'none';
    }, 300);
}

// Setup event listeners when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('[OwnListingsSkippedModal] Initializing...');

    const modal = document.getElementById('ownListingsSkippedModal');
    if (!modal) {
        console.warn('[OwnListingsSkippedModal] Modal element not found');
        return;
    }

    // OK button
    const okBtn = document.getElementById('ownListingsSkippedOkBtn');
    if (okBtn) {
        okBtn.addEventListener('click', function() {
            hideOwnListingsSkippedModal();
        });
    }

    // Close on background click
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            hideOwnListingsSkippedModal();
        }
    });

    // Close on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && modal.style.display === 'flex') {
            hideOwnListingsSkippedModal();
        }
    });

    // Check if we should show the modal (triggered by session flag)
    console.log('[OwnListingsSkippedModal] Checking flag. Value:', window.showOwnListingsSkippedModal, 'Type:', typeof window.showOwnListingsSkippedModal);

    if (window.showOwnListingsSkippedModal === true) {
        console.log('[OwnListingsSkippedModal] ✓ Flag is true - showing modal');
        showOwnListingsSkippedModal();
    } else {
        console.log('[OwnListingsSkippedModal] ✗ Flag is not true - modal will not show');
    }
});

// Expose functions globally with different names to avoid overwriting boolean flags
window.showOwnListingsSkippedModalFunc = showOwnListingsSkippedModal;
window.hideOwnListingsSkippedModalFunc = hideOwnListingsSkippedModal;
