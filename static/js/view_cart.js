// static/js/view_cart.js

document.addEventListener('DOMContentLoaded', () => {
  // Initialize bucket totals from per-bucket subtotal elements (includes grading fee)
  document.querySelectorAll('[id^="summary-total-"]').forEach(el => {
    const bucketId = el.id.replace('summary-total-', '');
    const match = el.textContent.match(/\$([\d,]+\.?\d*)/);
    if (match) {
      bucketTotals[bucketId] = parseFloat(match[1].replace(/,/g, ''));
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
  // bucket_key may contain underscores (e.g. "42_g0"), so don't just split on '-'
  const bucketId = input.id.replace('quantity-', '');
  const qtyGroup = input.closest('.cart-qty');
  const categoryId = qtyGroup ? qtyGroup.dataset.categoryId : bucketId;
  const requiresGrading = qtyGroup ? parseInt(qtyGroup.dataset.requiresGrading || '0', 10) : 0;
  let qty = parseInt(input.value, 10);
  if (isNaN(qty) || qty < 1) qty = 1;
  input.value = qty;

  // Persist to backend and update UI dynamically
  fetch(`/cart/update_bucket_quantity/${categoryId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'
    },
    body: JSON.stringify({ quantity: qty, requires_grading: requiresGrading })
  })
  .then(res => {
    if (!res.ok) throw new Error('Failed to update quantity');
    return res.json();
  })
  .then(data => {
    if (data.success) {
      // Update tile quantity display (in case backend adjusted it)
      input.value = data.quantity;

      // Update order summary for this bucket
      const summaryQtyEl = document.getElementById(`summary-qty-${bucketId}`);
      const summaryTotalEl = document.getElementById(`summary-total-${bucketId}`);
      const gradingFeeEl   = document.getElementById(`summary-grading-fee-${bucketId}`);
      const gradingLabelEl = document.getElementById(`summary-grading-label-${bucketId}`);

      if (summaryQtyEl) {
        summaryQtyEl.textContent = data.quantity;
      }

      // Update grading fee row
      if (gradingFeeEl) {
        gradingFeeEl.textContent = formatPrice(data.grading_fee || 0);
      }
      if (gradingLabelEl) {
        gradingLabelEl.textContent = `3rd Party Grading (×${data.quantity})`;
      }

      // Subtotal = merchandise + grading fee
      const bucketSubtotal = data.total_price + (data.grading_fee || 0);
      if (summaryTotalEl) {
        summaryTotalEl.textContent = formatPrice(bucketSubtotal);
        bucketTotals[bucketId] = bucketSubtotal;
      }

      // Update tile price display (average price)
      const tilePrice = document.querySelector(`[data-bucket-id="${bucketId}"] .price`);
      if (tilePrice) {
        tilePrice.textContent = formatPrice(data.avg_price);
      }

      // Recalculate and update grand total
      updateGrandTotal();

      // If quantity is now 0, reload to remove the tile
      if (data.quantity === 0) {
        location.reload();
      }
    } else {
      throw new Error(data.error || 'Update failed');
    }
  })
  .catch(err => {
    console.error('Update error:', err);
    alert(`Error updating quantity: ${err.message}`);
    // Reload to show accurate state
    location.reload();
  });
}

// Calculate and update the grand total across all buckets
function updateGrandTotal() {
  let grandTotal = 0;

  // Sum all bucket totals (each already includes grading fee)
  for (const bucketId in bucketTotals) {
    grandTotal += bucketTotals[bucketId];
  }

  // Update Subtotal and Total rows (both show the same grand total)
  const subtotalEl  = document.getElementById('cart-subtotal');
  const grandTotalEl = document.querySelector('.summary-total .summary-value');
  if (subtotalEl)   subtotalEl.textContent   = formatPrice(grandTotal);
  if (grandTotalEl) grandTotalEl.textContent = formatPrice(grandTotal);
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
