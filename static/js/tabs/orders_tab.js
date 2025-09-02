// orders_tab.js
// placeholder for any Orders-specific JS
document.addEventListener('DOMContentLoaded', () => {
  // future enhancements (e.g. tracking modal) go here
});

// orders_tab.js
function openOrderSellerPopup(orderId) {
  fetch(`/orders/api/${orderId}/order_sellers`)
    .then(res => {
      if (!res.ok) throw new Error("Could not load sellers");
      return res.json();
    })
    .then(data => {
      // reuse the cart_sellers_modal rendering logic
      sellerData   = data;
      currentIndex = 0;
      renderSeller();
      const modal = document.getElementById('orderSellersModal');
      modal.style.display = 'block';
      modal.addEventListener('click', outsideClickListener);
    })
    .catch(err => {
      console.error(err);
      alert(err.message);
    });
}

// expose globally
window.openOrderSellerPopup = openOrderSellerPopup;
