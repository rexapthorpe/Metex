// static/js/add_to_cart_ajax.js
'use strict';

/**
 * Handle Add to Cart via AJAX.
 * - Intercepts the Add to Cart form submit.
 * - Reads the grading preference from the radio group on the page.
 * - Handles backend responses: OK, MAX_REACHED, errors.
 * - MAX_REACHED: shows an inline modal with View Cart / Replace / Cancel actions.
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('[BucketPurchaseAJAX] Initializing...');

    const addToCartForms = document.querySelectorAll('form[action*="purchase_from_bucket"]');
    console.log('[BucketPurchaseAJAX] Found', addToCartForms.length, 'Add to Cart forms');

    addToCartForms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            console.log('[AddToCartAJAX] Add to Cart form submitted - intercepting');

            // Read grading preference from toggle (source of truth)
            const tpgToggle = document.querySelector('#tpgToggle');
            const isTPG = tpgToggle && tpgToggle.checked;
            const gradingPref = isTPG ? 'ANY' : 'NONE';

            // Build form data, overriding grading fields from UI state
            const formData = new FormData(form);
            formData.set('grading_preference', gradingPref);
            formData.set('third_party_grading', isTPG ? '1' : '0');

            // Extract bucket_id from form action URL (/purchase_from_bucket/<id>)
            const actionUrl = form.action;
            const bucketId = actionUrl.split('/').pop();

            console.log('[AddToCartAJAX] Sending AJAX POST to:', actionUrl, 'grading:', gradingPref);

            fetch(actionUrl, {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                body: formData,
                credentials: 'same-origin'
            })
            .then(function(response) {
                console.log('[AddToCartAJAX] Response status:', response.status);
                if (!response.ok) throw new Error('HTTP error! status: ' + response.status);
                return response.json();
            })
            .then(function(data) {
                console.log('[AddToCartAJAX] Response data:', data);

                // Handle max-reached before generic success check
                if (data.status === 'MAX_REACHED') {
                    showMaxReachedModal(data, bucketId);
                    return;
                }

                if (!data.success) {
                    console.error('[AddToCartAJAX] Server returned success=false:', data.message);
                    alert(data.message || 'Failed to add items to cart');
                    return;
                }

                // Check if user's own listings were skipped
                if (data.user_listings_skipped === true) {
                    console.log('[AddToCartAJAX] User listings were skipped - showing modal');

                    if (typeof window.showOwnListingsSkippedModalFunc === 'function') {
                        window.showOwnListingsSkippedModalFunc();

                        const modal = document.getElementById('ownListingsSkippedModal');
                        if (modal) {
                            const okBtn = document.getElementById('ownListingsSkippedOkBtn');
                            if (okBtn) {
                                const newOkBtn = okBtn.cloneNode(true);
                                okBtn.parentNode.replaceChild(newOkBtn, okBtn);
                                newOkBtn.addEventListener('click', function() {
                                    if (typeof window.hideOwnListingsSkippedModalFunc === 'function') {
                                        window.hideOwnListingsSkippedModalFunc();
                                    }
                                    setTimeout(function() { window.location.href = '/view_cart'; }, 300);
                                });
                            }

                            const handleBackgroundClick = function(event) {
                                if (event.target === modal) {
                                    if (typeof window.hideOwnListingsSkippedModalFunc === 'function') {
                                        window.hideOwnListingsSkippedModalFunc();
                                    }
                                    setTimeout(function() { window.location.href = '/view_cart'; }, 300);
                                    modal.removeEventListener('click', handleBackgroundClick);
                                }
                            };
                            modal.addEventListener('click', handleBackgroundClick);
                        }
                    } else {
                        console.error('[AddToCartAJAX] showOwnListingsSkippedModalFunc not found!');
                        window.location.href = '/view_cart';
                    }
                } else {
                    console.log('[AddToCartAJAX] Success - redirecting to cart');
                    window.location.href = '/view_cart';
                }
            })
            .catch(function(error) {
                console.error('[AddToCartAJAX] Error:', error);
                alert('An error occurred while adding items to cart. Please try again.');
            });
        });
    });

    console.log('[AddToCartAJAX] Initialization complete');
});

// ===== Max Reached Modal =====

/**
 * Show the MAX_REACHED modal with current/new grading info.
 * @param {object} data  - Backend response: {in_cart_grading, new_grading, ...}
 * @param {string} bucketId - The bucket ID string extracted from the form action URL
 */
function showMaxReachedModal(data, bucketId) {
    const modal = document.getElementById('maxReachedModal');
    if (!modal) {
        console.error('[MaxReachedModal] Modal element not found in DOM');
        alert(data.message || 'Cart limit reached.');
        return;
    }

    // Populate grading display — in_cart_tpg / new_tpg are canonical 0/1 booleans
    const currentEl = document.getElementById('mrCurrentGrading');
    const newEl = document.getElementById('mrNewGrading');
    if (currentEl) currentEl.textContent = _formatGrading(data.in_cart_tpg);
    if (newEl) newEl.textContent = _formatGrading(data.new_tpg);

    modal.style.display = 'flex';

    // Wire Replace button (clone to clear any old listeners)
    const replaceBtn = document.getElementById('mrReplaceBtn');
    if (replaceBtn) {
        const newReplace = replaceBtn.cloneNode(true);
        replaceBtn.parentNode.replaceChild(newReplace, replaceBtn);
        newReplace.addEventListener('click', function() {
            replaceCartGrading(bucketId, data.new_tpg);
        });
    }

    // Wire Cancel button
    const cancelBtn = document.getElementById('mrCancelBtn');
    if (cancelBtn) {
        const newCancel = cancelBtn.cloneNode(true);
        cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);
        newCancel.addEventListener('click', function() {
            modal.style.display = 'none';
        });
    }

    // Click outside to close
    function closeOnOutside(e) {
        if (e.target === modal) {
            modal.style.display = 'none';
            modal.removeEventListener('click', closeOnOutside);
        }
    }
    modal.addEventListener('click', closeOnOutside);
}

/**
 * POST to /replace_cart_grading/<bucketId> and redirect to cart on success.
 * @param {number} newTpg  - Canonical boolean: 1 = grading requested, 0 = not requested.
 */
function replaceCartGrading(bucketId, newTpg) {
    const replaceBtn = document.getElementById('mrReplaceBtn');
    if (replaceBtn) replaceBtn.disabled = true;

    fetch('/replace_cart_grading/' + bucketId, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({ third_party_grading_requested: newTpg ? 1 : 0 }),
        credentials: 'same-origin'
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        const modal = document.getElementById('maxReachedModal');
        if (modal) modal.style.display = 'none';

        if (data.success) {
            window.location.href = '/view_cart';
        } else {
            alert(data.message || 'Failed to update cart.');
            if (replaceBtn) replaceBtn.disabled = false;
        }
    })
    .catch(function(err) {
        console.error('[replaceCartGrading] Error:', err);
        alert('An error occurred while updating the cart. Please try again.');
        if (replaceBtn) replaceBtn.disabled = false;
    });
}

/** Human-readable label for the canonical grading boolean (0/1 or falsy/truthy). */
function _formatGrading(val) {
    return val ? 'Required' : 'Not required';
}
