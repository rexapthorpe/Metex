// static/js/view_cart.js

document.addEventListener('DOMContentLoaded', () => {
  // Initialize bucket totals from current summary
  document.querySelectorAll('.summary-total').forEach(el => {
    const bucketId = el.id.replace('summary-total-', '');
    const match = el.textContent.match(/\$([0-9.]+)/);
    if (match) {
      bucketTotals[bucketId] = parseFloat(match[1]);
    }
  });

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

// Store bucket totals for grand total calculation
const bucketTotals = {};

// Update quantity both client-side and backend
function handleQuantityChange(e) {
  const input = e.target;
  const [, bucketId] = input.id.split('-');
  let qty = parseInt(input.value, 10);
  if (isNaN(qty) || qty < 1) qty = 1;
  input.value = qty;

  // Persist to backend and reload page
  fetch(`/cart/update_bucket_quantity/${bucketId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'
    },
    body: JSON.stringify({ quantity: qty })
  })
  .then(res => {
    if (!res.ok) throw new Error('Failed to update quantity');
    return res.json();
  })
  .then(() => {
    // Reload page to show updated totals
    location.reload();
  })
  .catch(err => {
    alert(`Error updating quantity: ${err.message}`);
  });
}

// Calculate and update the grand total across all buckets
function updateGrandTotal() {
  let grandTotal = 0;

  // Sum all bucket totals
  for (const bucketId in bucketTotals) {
    grandTotal += bucketTotals[bucketId];
  }

  // Update the "Total for All Items" line
  const allItemsTotalEl = document.querySelector('.cart-summary-fixed > p:last-of-type');
  if (allItemsTotalEl) {
    allItemsTotalEl.innerHTML = `<strong>Total for All Items:</strong> $${grandTotal.toFixed(2)}`;
  }
}

/* ---------------------- Helpers for modal content ---------------------- */
function firstExisting(root, selectors) {
  for (const sel of selectors) {
    const el = root ? root.querySelector(sel) : document.querySelector(sel);
    if (el) return el;
  }
  return null;
}

/* --------- Items modal (works with partial ids or legacy ids) ---------- */
function openPriceBreakdown(bucketId) {
  // try partial id(s), then legacy
  const modal =
    document.getElementById('cartIndividualListingsModal') ||
    document.getElementById('cartPriceBreakdownModal') ||
    document.getElementById('priceBreakdownModal');

  if (!modal) return;

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
        const sellerName = entry.seller_username || entry.username || 'Unknown seller';

        const div = document.createElement('div');
        div.className = 'seller-card';
        div.innerHTML = `
          <p><strong>${sellerName}</strong></p>
          <p>Quantity: ${entry.quantity}</p>
          <p>Price: $${entry.price_per_coin}</p>
          <button type="button" class="btn btn-danger btn-sm" onclick="openRemoveListingConfirmation(${entry.listing_id})">
            Remove Item
          </button>
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
  // This just opens the bucket-level "are you sure?" modal
  openRemoveItemModal(bucketId);
}

// expose for inline onclick
window.removeCartBucket   = removeCartBucket;
window.openPriceBreakdown = openPriceBreakdown;
window.closePriceBreakdown = closePriceBreakdown;
