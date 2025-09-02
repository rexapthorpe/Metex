let priceData = [];
let priceIndex = 0;

function openPriceBreakdown(bucketId) {
  fetch(`/cart/api/bucket/${bucketId}/price_breakdown`)
    .then(res => res.json())
    .then(data => {
      priceData = data;
      priceIndex = 0;
      renderPriceEntry();
      const modal = document.getElementById('priceBreakdownModal');
      modal.style.display = 'block';
      modal.addEventListener('click', priceOutsideClick);
    })
    .catch(console.error);
}

function closePriceBreakdown() {
  const modal = document.getElementById('priceBreakdownModal');
  modal.style.display = 'none';
  modal.removeEventListener('click', priceOutsideClick);
}

function priceOutsideClick(e) {
  if (e.target.id === 'priceBreakdownModal') closePriceBreakdown();
}

function prevPriceListing() {
  if (priceIndex > 0) {
    priceIndex--;
    renderPriceEntry();
  }
}

function nextPriceListing() {
  if (priceIndex < priceData.length - 1) {
    priceIndex++;
    renderPriceEntry();
  }
}

function removePriceListing() {
  const listing = priceData[priceIndex];
  if (!confirm('Remove this item from cart?')) return;
  fetch(`/cart/remove_item/${listing.listing_id}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then(res => {
      if (res.ok) {
        closePriceBreakdown();
        location.reload();
      } else {
        alert('Failed to remove item.');
      }
    })
    .catch(() => alert('Something went wrong.'));
}

function renderPriceEntry() {
  const entry = priceData[priceIndex];
  // header
  document.getElementById('pb-username').innerText = entry.username;
  document.getElementById('pb-prev').disabled = priceIndex === 0;
  document.getElementById('pb-next').disabled = priceIndex === priceData.length - 1;
  // body
  document.getElementById('pb-quantity').innerText = `Items: ${entry.quantity}`;
  document.getElementById('pb-price').innerText =
    `$${entry.price_per_coin.toFixed(2)} each`;
}

// expose globals for inline onclicks
window.openPriceBreakdown   = openPriceBreakdown;
window.closePriceBreakdown  = closePriceBreakdown;
window.prevPriceListing     = prevPriceListing;
window.nextPriceListing     = nextPriceListing;
window.removePriceListing   = removePriceListing;
