// static/js/tabs/cart_tab.js
// Cart behavior for the Account → Cart Items tab.
// ALL pricing math is server-authoritative.
// JS never computes subtotal = quantity * unit_price.
// All totals come from /cart/update_bucket_quantity response.

// Track per-bucket subtotals for grand total recomputation.
// Initialized from server-rendered DOM on page load.
const cartTabBucketTotals = {};

document.addEventListener('DOMContentLoaded', () => {
  // Initialize bucket totals from server-rendered DOM (already correct at load time).
  document.querySelectorAll('[id^="summary-subtotal-"]').forEach(el => {
    const bucketId = el.id.replace('summary-subtotal-', '');
    const match = el.textContent.match(/\$([\d,]+\.?\d*)/);
    if (match) {
      cartTabBucketTotals[bucketId] = parseFloat(match[1].replace(/,/g, ''));
    }
  });

  // Attach qty dials for all cart tiles in the account cart tab
  document.querySelectorAll('#cart-tab .cart-qty').forEach(attachQtyDial);

  // For safety, also listen to changes on the raw inputs
  document.querySelectorAll('#cart-tab .quantity-input').forEach(input => {
    input.addEventListener('change', handleQuantityChange);
  });
});

/**
 * Attach +/- behavior to a quantity dial group.
 */
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

/**
 * Send quantity update to server and update all price displays from the response.
 * No client-side financial math. All totals come from the backend.
 */
function handleQuantityChange(e) {
  const input = e.target;
  const qtyGroup = input.closest('.cart-qty');
  // bucket_key may contain underscores (e.g. "42_g0"); read integer category_id from data attr
  const bucketId = qtyGroup ? qtyGroup.dataset.bucketId : input.id.replace('quantity-', '');
  const categoryId = qtyGroup ? qtyGroup.dataset.categoryId : bucketId;
  const requiresGrading = qtyGroup ? parseInt(qtyGroup.dataset.requiresGrading || '0', 10) : 0;
  let qty = parseInt(input.value, 10);
  if (isNaN(qty) || qty < 1) qty = 1;
  input.value = qty;

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
    if (!data.success) throw new Error(data.error || 'Update failed');

    // Update tile quantity (in case server clamped it)
    input.value = data.quantity;

    // Tile price block (left column)
    const tileTotalEl    = document.getElementById(`cart-total-${bucketId}`);
    const tileUnitEl     = document.getElementById(`cart-unit-price-${bucketId}`);
    if (tileTotalEl) tileTotalEl.textContent = formatPrice(data.total_price);
    if (tileUnitEl)  tileUnitEl.textContent  = `${formatPrice(data.avg_price)} each`;

    // Order summary section for this bucket
    const summaryQtyEl    = document.getElementById(`summary-qty-${bucketId}`);
    const summaryAvgEl    = document.getElementById(`summary-avg-price-${bucketId}`);
    const summaryGradFeeEl= document.getElementById(`summary-grading-fee-${bucketId}`);
    const summaryGradLblEl= document.getElementById(`summary-grading-label-${bucketId}`);
    const summarySubEl    = document.getElementById(`summary-subtotal-${bucketId}`);

    if (summaryQtyEl)    summaryQtyEl.textContent    = data.quantity;
    if (summaryAvgEl)    summaryAvgEl.textContent     = formatPrice(data.avg_price);
    if (summaryGradFeeEl) summaryGradFeeEl.textContent = formatPrice(data.grading_fee || 0);
    if (summaryGradLblEl) summaryGradLblEl.textContent = `3rd Party Grading (×${data.quantity})`;

    // Bucket subtotal = merchandise + grading (both from backend, no client math)
    const bucketSubtotal = data.total_price + (data.grading_fee || 0);
    if (summarySubEl) {
      summarySubEl.textContent = formatPrice(bucketSubtotal);
      cartTabBucketTotals[bucketId] = bucketSubtotal;
    }

    // Recompute and update grand total
    updateCartGrandTotal();

    // If quantity dropped to 0, reload to remove the tile
    if (data.quantity === 0) {
      location.reload();
    }
  })
  .catch(err => {
    console.error('Cart tab update error:', err);
    openErrorNotificationModal(`Error updating quantity: ${err.message}`, 'Cart Error');
    location.reload();
  });
}

/**
 * Sum all bucket subtotals and update the grand total display.
 * No arithmetic on unit prices — only sums server-provided subtotals.
 */
function updateCartGrandTotal() {
  let grandTotal = 0;
  for (const bucketId in cartTabBucketTotals) {
    grandTotal += cartTabBucketTotals[bucketId];
  }

  const subtotalEl  = document.getElementById('cart-subtotal');
  const totalEl     = document.getElementById('cart-total-all');
  if (subtotalEl) subtotalEl.textContent = formatPrice(grandTotal);
  if (totalEl)    totalEl.textContent    = formatPrice(grandTotal);
}
