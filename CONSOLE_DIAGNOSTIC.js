// ============================================================================
// MODAL DIAGNOSTIC - Paste this into browser console
// ============================================================================

console.log('%c=== MODAL DIAGNOSTIC START ===', 'color: cyan; font-weight: bold; font-size: 14px');

// 1. Check form detection
console.log('%c\n1. FORM DETECTION:', 'color: yellow; font-weight: bold');
const addToCartForms = document.querySelectorAll('form[action*="purchase_from_bucket"]');
const allCheckoutForms = document.querySelectorAll('form[action*="checkout"]');
const buyItemForms = Array.from(allCheckoutForms).filter(form =>
    form.querySelector('input[name="bucket_id"]')
);

console.log('Add to Cart forms found:', addToCartForms.length);
addToCartForms.forEach((form, i) => {
    console.log(`  Form ${i + 1}:`, form.action);
});

console.log('Buy Item forms found:', buyItemForms.length);
buyItemForms.forEach((form, i) => {
    console.log(`  Form ${i + 1}:`, form.action);
    console.log('  Has bucket_id input:', !!form.querySelector('input[name="bucket_id"]'));
    const bucketIdInput = form.querySelector('input[name="bucket_id"]');
    if (bucketIdInput) {
        console.log('  bucket_id value:', bucketIdInput.value);
    }
});

// 2. Check modal functions
console.log('%c\n2. MODAL FUNCTIONS:', 'color: yellow; font-weight: bold');
console.log('showOwnListingsSkippedModalFunc exists:', typeof window.showOwnListingsSkippedModalFunc);
console.log('hideOwnListingsSkippedModalFunc exists:', typeof window.hideOwnListingsSkippedModalFunc);
console.log('Modal element exists:', !!document.getElementById('ownListingsSkippedModal'));

// 3. Test Add to Cart with detailed logging
console.log('%c\n3. TESTING ADD TO CART:', 'color: yellow; font-weight: bold');
if (addToCartForms.length > 0) {
    const form = addToCartForms[0];
    const formData = new FormData(form);

    console.log('Form action:', form.action);
    console.log('Form data:');
    for (let [key, value] of formData.entries()) {
        console.log(`  ${key}: ${value}`);
    }

    console.log('\nSending test AJAX request...');
    fetch(form.action, {
        method: 'POST',
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: formData
    })
    .then(response => {
        console.log('%cResponse status:', 'color: lime', response.status);
        return response.json();
    })
    .then(data => {
        console.log('%cResponse data:', 'color: lime');
        console.log('  success:', data.success);
        console.log('  user_listings_skipped:', data.user_listings_skipped);
        console.log('  total_filled:', data.total_filled);
        console.log('  message:', data.message);
        console.log('  Full response:', data);

        console.log('%c\n✓ Add to Cart test complete', 'color: lime; font-weight: bold');

        if (data.user_listings_skipped === true) {
            console.log('%c  → Modal SHOULD appear', 'color: lime');
        } else {
            console.log('%c  → Modal should NOT appear (no user listings skipped)', 'color: orange');
        }
    })
    .catch(error => {
        console.error('%cAdd to Cart error:', 'color: red', error);
    });
} else {
    console.log('%cNo Add to Cart forms found!', 'color: red');
}

// 4. Test Buy Item with detailed logging
console.log('%c\n4. TESTING BUY ITEM:', 'color: yellow; font-weight: bold');
if (buyItemForms.length > 0) {
    const form = buyItemForms[0];

    // Sync quantity first
    const quantityInput = document.getElementById('quantityInput');
    const buyQuantityInput = form.querySelector('#buyQuantityInput');
    if (quantityInput && buyQuantityInput) {
        buyQuantityInput.value = quantityInput.value;
        console.log('Synced quantity:', quantityInput.value);
    }

    const formData = new FormData(form);

    console.log('Form action:', form.action);
    console.log('Form data:');
    for (let [key, value] of formData.entries()) {
        console.log(`  ${key}: ${value}`);
    }

    console.log('\nSending test AJAX request...');
    fetch(form.action, {
        method: 'POST',
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: formData
    })
    .then(response => {
        console.log('%cResponse status:', 'color: lime', response.status);

        if (response.status === 500) {
            console.error('%c500 ERROR - Check Flask console for Python traceback!', 'color: red; font-weight: bold');
            return response.text().then(text => {
                console.error('Error response:', text);
                throw new Error('Server returned 500 error');
            });
        }

        return response.json();
    })
    .then(data => {
        console.log('%cResponse data:', 'color: lime');
        console.log('  success:', data.success);
        console.log('  user_listings_skipped:', data.user_listings_skipped);
        console.log('  items_selected:', data.items_selected);
        console.log('  message:', data.message);
        console.log('  Full response:', data);

        console.log('%c\n✓ Buy Item test complete', 'color: lime; font-weight: bold');

        if (data.user_listings_skipped === true) {
            console.log('%c  → Modal SHOULD appear', 'color: lime');
        } else {
            console.log('%c  → Modal should NOT appear (no user listings skipped)', 'color: orange');
        }
    })
    .catch(error => {
        console.error('%cBuy Item error:', 'color: red', error);
    });
} else {
    console.log('%cNo Buy Item forms found!', 'color: red');
}

console.log('%c\n=== DIAGNOSTIC COMPLETE ===', 'color: cyan; font-weight: bold; font-size: 14px');
console.log('%cNote: Tests run asynchronously - results will appear above', 'color: gray; font-style: italic');
