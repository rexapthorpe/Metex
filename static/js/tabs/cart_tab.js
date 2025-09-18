// Only target inputs inside the .cart-tab namespace
document.addEventListener('DOMContentLoaded', () => {
  // Legacy: listen for manual edits on the value (kept for compatibility)
  document.querySelectorAll('.cart-tab .quantity-input')
    .forEach(input => input.addEventListener('change', handleQuantityChangeBucket));

  // New: attach +/- behavior for the pill dial
  document.querySelectorAll('.cart-tab .cart-qty').forEach(attachQtyDial);
});

function attachQtyDial(group) {
  const minus = group.querySelector('.cart-qty__minus');
  const plus  = group.querySelector('.cart-qty__plus');
  const input = group.querySelector('.cart-qty__value'); // also has class quantity-input

  const clamp = (v) => {
    const min = parseInt(input.getAttribute('min') || '1', 10);
    const max = parseInt(input.getAttribute('max') || '999999', 10);
    v = parseInt(String(v).replace(/\D/g, ''), 10);
    if (!Number.isFinite(v)) v = min;
    return Math.max(min, Math.min(max, v));
  };

  const updateDisabled = () => {
    const min = parseInt(input.getAttribute('min') || '1', 10);
    const max = parseInt(input.getAttribute('max') || '999999', 10);
    const q = parseInt(input.value, 10);
    minus.disabled = q <= min;
    plus.disabled  = q >= max;
  };

  // Initialize
  input.value = clamp(input.value);
  updateDisabled();

  minus.addEventListener('click', () => {
    const q = clamp(parseInt(input.value, 10) - 1);
    if (q === parseInt(input.value, 10)) return;
    input.value = q;
    updateDisabled();
    // Reuse existing handler (expects an event with target)
    handleQuantityChangeBucket({ target: input });
  });

  plus.addEventListener('click', () => {
    const q = clamp(parseInt(input.value, 10) + 1);
    if (q === parseInt(input.value, 10)) return;
    input.value = q;
    updateDisabled();
    handleQuantityChangeBucket({ target: input });
  });

  // Allow typing; commit on blur/Enter
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') input.blur();
  });
  input.addEventListener('blur', () => {
    const q = clamp(input.value);
    if (q !== parseInt(input.value, 10)) input.value = q;
    updateDisabled();
    handleQuantityChangeBucket({ target: input });
  });
}

// Called when the quantity input for a bucket changes
function handleQuantityChangeBucket(e) {
  const bucketId = e.target.id.split('-')[1];
  let q = parseInt(e.target.value, 10);
  if (isNaN(q) || q < 1) q = 1;
  e.target.value = q;

  fetch(`/cart/update_bucket_quantity/${bucketId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ quantity: q })
  })
  .then(res => {
    if (!res.ok) throw new Error('Failed to update quantity');
    location.reload();
  })
  .catch(err => alert(err.message));
}

// removeCartBucket is now internal—confirmation happens in the modal
function removeCartBucket(bucketId) {
  fetch(`/cart/remove_bucket/${bucketId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
  .then(res => {
    if (!res.ok) throw new Error('Remove failed');
    const tile = document.querySelector(
      `.cart-tab .cart-item-tile[data-bucket-id="${bucketId}"]`
    );
    if (tile) tile.remove();
  })
  .catch(() => alert('Failed to remove item.'));
}

// expose for inline onclicks
window.handleQuantityChangeBucket = handleQuantityChangeBucket;
window.openSellerPopup       = openSellerPopup;
window.openPriceBreakdown    = openPriceBreakdown;
window.openRemoveItemModal   = openRemoveItemModal;
window.removeCartBucket      = removeCartBucket;
