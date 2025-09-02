// static/js/view_cart.js

// Wait for the DOM to load, then attach change listeners to quantity inputs
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.quantity-input').forEach(input => {
    input.addEventListener('change', handleQuantityChange);
  });
});

// Recalculate total when quantity changes
function handleQuantityChange(e) {
  const input = e.target;
  const [, bucketId] = input.id.split('-');
  let qty = parseInt(input.value, 10);
  if (isNaN(qty) || qty < 1) qty = 1;
  input.value = qty;

  // Get this bucket's per-unit prices from the global cartData
  const prices = (cartData[bucketId] || []).slice().sort((a, b) => a - b);
  const total = prices.slice(0, qty).reduce((sum, p) => sum + p, 0);

  // Update the Order Summary panel
  const qtyEl = document.getElementById(`summary-qty-${bucketId}`);
  const totEl = document.getElementById(`summary-total-${bucketId}`);
  if (qtyEl) qtyEl.textContent = `Quantity: ${qty}`;
  if (totEl) totEl.textContent = `Total: $${total.toFixed(2)}`;
}

// --- Existing popup & removal functions ---

function openSellerPopup(bucketId) {
  fetch(`/cart/api/bucket/${bucketId}/cart_sellers`)
    .then(res => res.json())
    .then(data => {
      const container = document.getElementById('sellerDetails');
      container.innerHTML = '';
      if (data.length === 0) {
        container.innerHTML = '<p>No sellers found for this item.</p>';
      }
      data.forEach(seller => {
        const div = document.createElement('div');
        div.className = 'seller-card';
        div.innerHTML = `
          <p><strong>${seller.username}</strong></p>
          <p>Quantity: ${seller.quantity}</p>
          <p>Price: $${seller.price_per_coin}</p>
          <p>Rating: ${seller.rating ? seller.rating.toFixed(2) : 'N/A'} (${seller.num_reviews} reviews)</p>
          <form method="POST" action="/cart/remove_seller/${bucketId}/${seller.seller_id}" onsubmit="return confirm('Remove this seller?');">
            <button type="submit" class="btn btn-danger btn-sm">Remove Seller</button>
          </form>
        `;
        container.appendChild(div);
      });
      document.getElementById('sellerModal').style.display = 'block';
    });
}

function closeSellerPopup() {
  document.getElementById('sellerModal').style.display = 'none';
}

function getFilterValue(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name) === '1' ? '1' : '';
}

function openPriceBreakdown(bucketId) {
  fetch(`/cart/api/bucket/${bucketId}/price_breakdown`)
    .then(res => res.json())
    .then(data => {
      const container = document.getElementById('priceBreakdownDetails');
      container.innerHTML = '';
      data.forEach(entry => {
        const div = document.createElement('div');
        div.className = 'seller-card';
        div.innerHTML = `
          <p><strong>${entry.username}</strong></p>
          <p>Quantity: ${entry.quantity}</p>
          <p>Price: $${entry.price_per_coin}</p>
          <form method="POST" action="/cart/remove_item/${entry.listing_id}" onsubmit="return confirm('Remove this item?');">
            <button type="submit" class="btn btn-danger btn-sm">Remove Item</button>
          </form>
          <hr>
        `;
        container.appendChild(div);
      });
      document.getElementById('priceBreakdownModal').style.display = 'block';
    });
}

function closePriceBreakdown() {
  document.getElementById('priceBreakdownModal').style.display = 'none';
}

function removeCartItem(listingId, buttonElement) {
  if (!confirm('Remove this item from cart?')) return;
  fetch(`/cart/remove_item/${listingId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then(response => {
      if (response.ok) {
        const tile = buttonElement.closest('.cart-item-tile');
        if (tile) tile.remove();
      } else {
        alert('Failed to remove item from cart.');
      }
    })
    .catch(err => {
      console.error('Error removing item:', err);
      alert('Something went wrong.');
    });
}
