// static/js/tabs/cart_tab.js
// Cart behavior for the Account → Cart Items tab.
// This file ONLY handles quantity controls and talking to /cart/update_bucket_quantity.
// It does NOT define or call openSellerPopup / openPriceBreakdown – those come from the modal JS files.

document.addEventListener('DOMContentLoaded', () => {
  // Attach qty dials for all cart tiles in the account cart tab
  document.querySelectorAll('#cart-tab .cart-qty').forEach(attachQtyDial);

  // For safety, also listen to changes on the raw inputs
  document.querySelectorAll('#cart-tab .quantity-input').forEach(input => {
    input.addEventListener('change', handleQuantityChange);
  });
});

/**
 * Attach +/- behavior to a quantity dial group.
 * This is copied from view_cart.js, but scoped to the account cart tab.
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
 * Update quantity for a bucket by calling /cart/update_bucket_quantity/<bucket_id>
 * and then reloading the page so both the tile and summary reflect the new data.
 */
function handleQuantityChange(e) {
  const input = e.target;
  const [, bucketId] = input.id.split('-'); // id is "quantity-<bucket_id>"
  let qty = parseInt(input.value, 10);
  if (isNaN(qty) || qty < 1) qty = 1;
  input.value = qty;

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
      // Reload to show updated totals and sellers/items
      location.reload();
    })
    .catch(err => {
      alert(`Error updating quantity: ${err.message}`);
    });
}
