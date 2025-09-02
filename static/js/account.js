// Show the selected tab
function showTab(tabName) {
  document.querySelectorAll('.tab-content').forEach(tab => tab.style.display = 'none');
  const active = document.getElementById(`${tabName}-tab`);
  if (active) {
    active.style.display = 'block';
  }

  // Highlight active sidebar tab
  document.querySelectorAll('.account-sidebar li').forEach(item => {
    item.classList.remove('active');
    if (item.getAttribute('onclick')?.includes(tabName)) {
      item.classList.add('active');
    }
  });

  // Fade in average rating if entering ratings tab
  if (tabName === 'ratings' && typeof fadeInAverageRating === 'function') {
    fadeInAverageRating();
  }
}

// Automatically open tab based on URL hash (e.g. #bids), or default to cart
document.addEventListener('DOMContentLoaded', () => {
  const tabFromHash = window.location.hash.slice(1); // "orders" from "#orders"
  const validTabs = ['cart','bids','listings','orders','ratings','messages','details'];
  const tab = validTabs.includes(tabFromHash) ? tabFromHash : 'cart';
  showTab(tab);
});

// Remove a single listing from cart (AJAX)
function removeCartItem(listingId, buttonElement) {
  fetch(`/cart/remove_item/${listingId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
  .then(response => {
    if (response.ok) {
      const tile = buttonElement.closest('.cart-item-tile');
      if (tile) tile.remove();
      // if no more .cart-item-tile left, show "empty" message
      if (!document.querySelector('.cart-tab .cart-item-tile')) {
        document.querySelector('.cart-tab .empty-message').style.display = 'block';
      }
    } else {
      alert("Failed to remove item from cart.");
    }
  })
  .catch(err => {
    console.error("Error:", err);
    alert("Something went wrong.");
  });
}
window.removeCartItem = removeCartItem;
