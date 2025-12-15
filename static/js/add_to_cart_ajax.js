// static/js/add_to_cart_ajax.js
'use strict';

/**
 * Handle Add to Cart via AJAX to show "own listings skipped" modal before redirect
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('[BucketPurchaseAJAX] Initializing...');

    // Find all Add to Cart forms and Buy Item forms on the page
    const addToCartForms = document.querySelectorAll('form[action*="purchase_from_bucket"]');

    // Find Buy Item forms (forms with action containing "checkout" that have bucket_id input)
    const allCheckoutForms = document.querySelectorAll('form[action*="checkout"]');
    const buyItemForms = Array.from(allCheckoutForms).filter(form =>
        form.querySelector('input[name="bucket_id"]')
    );

    console.log('[BucketPurchaseAJAX] Found', addToCartForms.length, 'Add to Cart forms');
    console.log('[BucketPurchaseAJAX] Found', buyItemForms.length, 'Buy Item forms');

    addToCartForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            console.log('[AddToCartAJAX] Add to Cart form submitted - intercepting');

            // Sync quantity before submitting
            const quantityInput = form.querySelector('#cartQuantityInput');
            if (quantityInput && typeof syncQuantity === 'function') {
                syncQuantity('cartQuantityInput');
            }

            // Gather form data
            const formData = new FormData(form);
            const actionUrl = form.action;

            console.log('[AddToCartAJAX] Sending AJAX POST to:', actionUrl);

            // Send AJAX request
            fetch(actionUrl, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: formData,
                credentials: 'same-origin'  // Include cookies/session
            })
            .then(response => {
                console.log('[AddToCartAJAX] Response status:', response.status);

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                return response.json();
            })
            .then(data => {
                console.log('[AddToCartAJAX] Response data:', data);

                if (!data.success) {
                    console.error('[AddToCartAJAX] Server returned success=false:', data.message);
                    alert(data.message || 'Failed to add items to cart');
                    return;
                }

                // Check if user listings were skipped
                if (data.user_listings_skipped === true) {
                    console.log('[AddToCartAJAX] User listings were skipped - showing modal');

                    // Show the modal
                    if (typeof window.showOwnListingsSkippedModalFunc === 'function') {
                        window.showOwnListingsSkippedModalFunc();

                        // Wait for user to click OK, then redirect
                        // We'll listen for the modal to close
                        const modal = document.getElementById('ownListingsSkippedModal');
                        if (modal) {
                            const okBtn = document.getElementById('ownListingsSkippedOkBtn');
                            if (okBtn) {
                                // Remove any existing listeners to avoid duplicates
                                const newOkBtn = okBtn.cloneNode(true);
                                okBtn.parentNode.replaceChild(newOkBtn, okBtn);

                                // Add new listener that redirects after closing
                                newOkBtn.addEventListener('click', function() {
                                    console.log('[AddToCartAJAX] Modal OK clicked - redirecting to cart');
                                    if (typeof window.hideOwnListingsSkippedModalFunc === 'function') {
                                        window.hideOwnListingsSkippedModalFunc();
                                    }
                                    // Small delay to allow modal to close gracefully
                                    setTimeout(() => {
                                        window.location.href = '/view_cart';
                                    }, 300);
                                });
                            }

                            // Also handle background click
                            const handleBackgroundClick = function(event) {
                                if (event.target === modal) {
                                    console.log('[AddToCartAJAX] Modal background clicked - redirecting to cart');
                                    if (typeof window.hideOwnListingsSkippedModalFunc === 'function') {
                                        window.hideOwnListingsSkippedModalFunc();
                                    }
                                    setTimeout(() => {
                                        window.location.href = '/view_cart';
                                    }, 300);
                                    modal.removeEventListener('click', handleBackgroundClick);
                                }
                            };
                            modal.addEventListener('click', handleBackgroundClick);
                        }
                    } else {
                        console.error('[AddToCartAJAX] showOwnListingsSkippedModalFunc function not found!');
                        // Fallback: redirect immediately
                        window.location.href = '/view_cart';
                    }
                } else {
                    // No user listings were skipped - redirect immediately
                    console.log('[AddToCartAJAX] No user listings skipped - redirecting immediately');
                    window.location.href = '/view_cart';
                }
            })
            .catch(error => {
                console.error('[AddToCartAJAX] Error:', error);
                alert('An error occurred while adding items to cart. Please try again.');
            });
        });
    });

    // Buy Item forms are handled by buy_item_modal.js
    // (No interception needed here - modal system handles the flow)

    console.log('[AddToCartAJAX] Initialization complete');
});
