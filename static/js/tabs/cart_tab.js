// Only target inputs inside the .cart-tab namespace
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.cart-tab .quantity-input')
    .forEach(input => input.addEventListener('change', handleQuantityChangeBucket));
});

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
