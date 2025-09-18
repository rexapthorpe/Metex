// static/js/view_cart.js

document.addEventListener('DOMContentLoaded', () => {
  // manual edits on the qty value (kept for compatibility)
  document.querySelectorAll('.quantity-input').forEach(input => {
    input.addEventListener('change', handleQuantityChange);
  });

  // attach +/- behavior for the pill dial
  document.querySelectorAll('.cart-qty').forEach(attachQtyDial);

  // wire modal behavior for all known modal ids (partials & legacy)
  [
    'cartSellersModal',
    'cartIndividualListingsModal',
    'sellerModal',
    'priceBreakdownModal'
  ].forEach(id => wireModalBehavior(id));
});

function wireModalBehavior(id) {
  const modal = document.getElementById(id);
  if (!modal) return;

  // backdrop click closes
  modal.addEventListener('click', (e) => {
    if (e.target === modal) hideModal(modal);
  });

  // ESC closes
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isShown(modal)) hideModal(modal);
  });
}

function isShown(modal) {
  return modal.classList.contains('show') || modal.style.display === 'flex';
}

function showModal(modal) {
  // override any inline display:none from base.html
  modal.style.display = 'flex';
  modal.classList.add('show');
  modal.setAttribute('aria-hidden', 'false');
}

function hideModal(modal) {
  modal.classList.remove('show');
  modal.setAttribute('aria-hidden', 'true');
  modal.style.display = 'none';
}

function attachQtyDial(group) {
  const minus = group.querySelector('.cart-qty__minus');
  const plus  = group.querySelector('.cart-qty__plus');
  const input = group.querySelector('.cart-qty__value');

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

  // initialize
  input.value = clamp(input.value);
  updateDisabled();

  minus.addEventListener('click', () => {
    const q = clamp(parseInt(input.value, 10) - 1);
    if (q === parseInt(input.value, 10)) return;
    input.value = q;
    updateDisabled();
    handleQuantityChange({ target: input });
  });

  plus.addEventListener('click', () => {
    const q = clamp(parseInt(input.value, 10) + 1);
    if (q === parseInt(input.value, 10)) return;
    input.value = q;
    updateDisabled();
    handleQuantityChange({ target: input });
  });

  // typing support: commit on blur/Enter
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') input.blur();
  });
  input.addEventListener('blur', () => {
    const q = clamp(input.value);
    if (q !== parseInt(input.value, 10)) input.value = q;
    updateDisabled();
    handleQuantityChange({ target: input });
  });
}

// Client-side summary update
function handleQuantityChange(e) {
  const input = e.target;
  const [, bucketId] = input.id.split('-');
  let qty = parseInt(input.value, 10);
  if (isNaN(qty) || qty < 1) qty = 1;
  input.value = qty;

  const prices = (cartData[bucketId] || []).slice().sort((a, b) => a - b);
  const total = prices.slice(0, qty).reduce((sum, p) => sum + p, 0);

  const qtyEl = document.getElementById(`summary-qty-${bucketId}`);
  const totEl = document.getElementById(`summary-total-${bucketId}`);
  if (qtyEl) qtyEl.textContent = `Quantity: ${qty}`;
  if (totEl) totEl.textContent = `Total: $${total.toFixed(2)}`;
}

/* ---------------------- Helpers for modal content ---------------------- */
function firstExisting(root, selectors) {
  for (const sel of selectors) {
    const el = root ? root.querySelector(sel) : document.querySelector(sel);
    if (el) return el;
  }
  return null;
}

/* --------- Sellers modal (works with partial ids or legacy ids) --------- */
function openSellerPopup(bucketId) {
  // try partial id first, fall back to legacy
  const modal =
    document.getElementById('cartSellersModal') ||
    document.getElementById('sellerModal');

  if (!modal) return;

  // common content containers in the shared partials / legacy:
  // - [data-role="sellers-list"]
  // - .seller-scroll-container
  // - #sellerDetails (legacy)
  // - .modal-scroll
  const container = firstExisting(modal, [
    '[data-role="sellers-list"]',
    '.seller-scroll-container',
    '#sellerDetails',
    '.modal-scroll'
  ]) || modal;

  container.innerHTML = '<p>Loading sellers…</p>';
  showModal(modal);

  fetch(`/cart/api/bucket/${bucketId}/cart_sellers`)
    .then(res => {
      if (!res.ok) throw new Error('Failed to load sellers');
      return res.json();
    })
    .then(data => {
      container.innerHTML = '';
      if (!data || data.length === 0) {
        container.innerHTML = '<p>No sellers found for this item.</p>';
        return;
      }
      data.forEach(seller => {
        const div = document.createElement('div');
        div.className = 'seller-card';
        div.innerHTML = `
          <p><strong>${seller.username}</strong></p>
          <p>Quantity: ${seller.quantity}</p>
          <p>Price: $${seller.price_per_coin}</p>
          <p>Rating: ${seller.rating ? Number(seller.rating).toFixed(2) : 'N/A'} (${seller.num_reviews} reviews)</p>
          <form method="POST" action="/cart/remove_seller/${bucketId}/${seller.seller_id}" onsubmit="return confirm('Remove this seller?');">
            <button type="submit" class="btn btn-danger btn-sm">Remove Seller</button>
          </form>
          <hr>
        `;
        container.appendChild(div);
      });

      // wire any close button in the partial (e.g., .modal-close)
      const closeBtn = firstExisting(modal, ['.modal-close', '[data-close]']);
      if (closeBtn) {
        closeBtn.onclick = () => hideModal(modal);
      }
    })
    .catch(err => {
      container.innerHTML = `<p style="color:#b91c1c;">${err.message}</p>`;
    });
}
function closeSellerPopup() {
  const modal =
    document.getElementById('cartSellersModal') ||
    document.getElementById('sellerModal');
  if (modal) hideModal(modal);
}

/* --------- Items modal (works with partial ids or legacy ids) ---------- */
function openPriceBreakdown(bucketId) {
  // try partial id(s), then legacy
  const modal =
    document.getElementById('cartIndividualListingsModal') ||
    document.getElementById('cartPriceBreakdownModal') ||
    document.getElementById('priceBreakdownModal');

  if (!modal) return;

  // common content containers:
  // - [data-role="items-list"]
  // - .seller-scroll-container
  // - #priceBreakdownDetails (legacy)
  // - .modal-scroll
  const container = firstExisting(modal, [
    '[data-role="items-list"]',
    '.seller-scroll-container',
    '#priceBreakdownDetails',
    '.modal-scroll'
  ]) || modal;

  container.innerHTML = '<p>Loading items…</p>';
  showModal(modal);

  fetch(`/cart/api/bucket/${bucketId}/price_breakdown`)
    .then(res => {
      if (!res.ok) throw new Error('Failed to load items');
      return res.json();
    })
    .then(data => {
      container.innerHTML = '';
      if (!data || data.length === 0) {
        container.innerHTML = '<p>No items found for this bucket.</p>';
        return;
      }
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

      const closeBtn = firstExisting(modal, ['.modal-close', '[data-close]']);
      if (closeBtn) {
        closeBtn.onclick = () => hideModal(modal);
      }
    })
    .catch(err => {
      container.innerHTML = `<p style="color:#b91c1c;">${err.message}</p>`;
    });
}
function closePriceBreakdown() {
  const modal =
    document.getElementById('cartIndividualListingsModal') ||
    document.getElementById('cartPriceBreakdownModal') ||
    document.getElementById('priceBreakdownModal');
  if (modal) hideModal(modal);
}

/* ------------------------- Remove bucket ------------------------- */
function removeCartBucket(bucketId) {
  if (!confirm('Remove all items in this group from cart?')) return;
  fetch(`/cart/remove_bucket/${bucketId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then(res => {
      if (!res.ok) throw new Error('Remove failed');
      const tile = document.querySelector(`.cart-item-tile[data-bucket-id="${bucketId}"]`);
      if (tile) tile.remove();
    })
    .catch(() => alert('Failed to remove.'));
}

// expose for inline onclick
window.removeCartBucket = removeCartBucket;
window.openSellerPopup = openSellerPopup;
window.closeSellerPopup = closeSellerPopup;
window.openPriceBreakdown = openPriceBreakdown;
window.closePriceBreakdown = closePriceBreakdown;
