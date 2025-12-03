// Show the selected tab
function showTab(tabName) {
  // Hide all tab panels
  document.querySelectorAll('.tab-content').forEach(tab => {
    tab.style.display = 'none';
  });

  // Show the active tab
  const active = document.getElementById(`${tabName}-tab`);
  if (active) {
    active.style.display = 'block';
  }

  // Highlight active sidebar tab
  document.querySelectorAll('.account-sidebar li').forEach(item => {
    item.classList.remove('active');
    const clickAttr = item.getAttribute('onclick') || '';
    if (clickAttr.includes(`'${tabName}'`)) {
      item.classList.add('active');
    }
  });

  // Tell the layout whether Account Details is open
  const layout = document.querySelector('.account-layout');
  if (layout) {
    if (tabName === 'details') {
      layout.classList.add('details-nav-open');
      // Show the overview section by default when opening Account Details
      if (typeof showDetailsSection === 'function') {
        setTimeout(() => showDetailsSection('overview'), 50);
      }
    } else {
      layout.classList.remove('details-nav-open');
    }
  }

  // Fade in average rating if entering ratings tab
  if (tabName === 'ratings' && typeof fadeInAverageRating === 'function') {
    fadeInAverageRating();
  }

  // Initialize portfolio if entering portfolio tab
  if (tabName === 'portfolio' && typeof initPortfolioTab === 'function') {
    initPortfolioTab();
  }
}

// Automatically open tab based on URL hash (e.g. #bids), or default to cart
document.addEventListener('DOMContentLoaded', () => {
  const tabFromHash = window.location.hash.slice(1); // "orders" from "#orders"
  const validTabs = ['cart','bids','listings','sold','orders','portfolio','ratings','messages','details'];
  const tab = validTabs.includes(tabFromHash) ? tabFromHash : 'cart';
  showTab(tab);
});

// Handle hash changes (e.g., when clicking notification "View Order" button)
window.addEventListener('hashchange', () => {
  const tabFromHash = window.location.hash.slice(1);
  const validTabs = ['cart','bids','listings','sold','orders','portfolio','ratings','messages','details'];
  if (validTabs.includes(tabFromHash)) {
    showTab(tabFromHash);
  }
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

      const emptyMsg = document.querySelector('.cart-tab .empty-message');
      if (!document.querySelector('.cart-tab .cart-item-tile') && emptyMsg) {
        emptyMsg.style.display = 'block';
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
