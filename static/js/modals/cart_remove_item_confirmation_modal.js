// static/js/modals/cart_remove_item_confirmation_modal.js

function openRemoveItemModal(bucketId) {
  const id = `cartRemoveItemModal-${bucketId}`;
  // If not yet in DOM, fetch and inject
  let wrapper = document.getElementById(id);
  if (!wrapper) {
    fetch(`/cart/remove_item_confirmation_modal/${bucketId}`)
      .then(res => {
        if (!res.ok) throw new Error('Could not load confirmation dialog.');
        return res.text();
      })
      .then(html => {
        document.body.insertAdjacentHTML('beforeend', html);
        wrapper = document.getElementById(id);
        wrapper.style.display = 'flex';
      })
      .catch(err => alert(err.message));
  } else {
   // Already exists: just show
    wrapper.style.display = 'flex';
  }
}

function closeRemoveItemModal(bucketId) {
  const id = `cartRemoveItemModal-${bucketId}`;
  const wrapper = document.getElementById(id);
  if (wrapper) wrapper.remove();
}

function confirmRemoveCartBucket(bucketId) {
  fetch(`/cart/remove_bucket/${bucketId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then(res => {
      if (!res.ok) throw new Error('Could not remove item');
      // Remove tile
      const tile = document.querySelector(
        `.cart-tab .cart-item-tile[data-bucket-id="${bucketId}"]`
      );
      if (tile) tile.remove();
      // Close modal
      closeRemoveItemModal(bucketId);
      // If no items left, show empty message
      const remaining = document.querySelectorAll(
        '.cart-tab .cart-item-tile'
      ).length;
      if (remaining === 0) {
        const col = document.querySelector('.cart-tab .cart-items-column');
        const p = document.createElement('p');
        p.className = 'empty-message';
        p.textContent = 'You have no items in your cart yet!';
        col.appendChild(p);
      }
    })
    .catch(err => {
      console.error(err);
      alert(err.message);
    });
}

// Expose for inline onclicks
window.openRemoveItemModal      = openRemoveItemModal;
window.closeRemoveItemModal     = closeRemoveItemModal;
window.confirmRemoveCartBucket  = confirmRemoveCartBucket;