// cart_individual_listings_modal.js

let priceData = [];
let priceIndex = 0;
let priceBucketId = null; // track which bucket the modal is showing

function showCartItemsModal() {
  const modal = document.getElementById('priceBreakdownModal');
  if (!modal) return;

  // Center via flex (matches orders modal)
  modal.style.display = 'flex';

  // Only handle overlay click & keyboard — no capture-phase blockers
  modal.addEventListener('click', priceOutsideClick);
  document.addEventListener('keydown', cartKeyNavHandler);
}

function closePriceBreakdown() {
  const modal = document.getElementById('priceBreakdownModal');
  if (!modal) return;

  modal.style.display = 'none';
  modal.removeEventListener('click', priceOutsideClick);
  document.removeEventListener('keydown', cartKeyNavHandler);
}

function priceOutsideClick(e) {
  // Only close when the overlay itself is clicked
  if (e.target && e.target.id === 'priceBreakdownModal') {
    closePriceBreakdown();
  }
}

function cartKeyNavHandler(e) {
  if (e.key === 'ArrowLeft') prevPriceListing();
  else if (e.key === 'ArrowRight') nextPriceListing();
  else if (e.key === 'Escape') closePriceBreakdown();
}

function showCartItemsError(message) {
  const body = document.getElementById('pb-modal-content');
  if (!body) return;
  body.innerHTML = `
    <div class="cart-items-error">
      <div class="cart-items-error-title">Couldn’t load items</div>
      <div class="cart-items-error-msg">${message ? String(message) : 'Please try again.'}</div>
    </div>
  `;
}

function openPriceBreakdown(bucketId) {
  priceBucketId = bucketId; // remember which bucket we’re looking at
  showCartItemsModal();
  const body = document.getElementById('pb-modal-content');
  if (body) body.innerHTML = '<div class="cart-items-loading">Loading…</div>';

  fetch(`/cart/api/bucket/${bucketId}/price_breakdown`)
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then(data => {
      priceData = Array.isArray(data) ? data : [];
      priceIndex = 0;
      if (!priceData.length) {
        showCartItemsError('No items found for this cart bucket.');
        return;
      }
      renderPriceEntry();
    })
    .catch(err => {
      showCartItemsError(err?.message || 'Unexpected error.');
      console.error('cart price_breakdown fetch error:', err);
    });
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

// ===== UI sync helpers for the cart tab =====
function updateCartBucketUIFromModalState() {
  if (priceBucketId == null) return;

  // Recompute totals from remaining priceData
  let totalQty = 0;
  let weightedSum = 0;
  for (const row of priceData) {
    const q = Number(row.quantity) || 0;
    const p = Number(row.price_per_coin);
    totalQty += q;
    if (!Number.isNaN(p)) weightedSum += p * q;
  }
  const newAvg = totalQty > 0 ? (weightedSum / totalQty) : null;

  // Patch the cart tab tile
  const tile = document.querySelector(
    `.cart-tab .cart-item-tile[data-bucket-id="${priceBucketId}"]`
  );

  if (!tile) return;

  // Update Qty input (#quantity-<bucketId>)
  const qtyInput = document.getElementById(`quantity-${priceBucketId}`) ||
                   tile.querySelector('.quantity-input');
  if (qtyInput) {
    qtyInput.value = String(totalQty > 0 ? totalQty : 0);
  }

  // Update displayed average price (.avg-price)
  const avgEl = tile.querySelector('.avg-price');
  if (avgEl) {
    avgEl.textContent = (newAvg != null && !Number.isNaN(newAvg))
      ? `$${newAvg.toFixed(2)}`
      : '--';
  }

  // If bucket became empty, remove the tile and show empty message if nothing remains
  if (totalQty <= 0) {
    tile.remove();

    // If no more tiles remain in the cart tab, show an empty message
    const stillHasTiles = document.querySelector('.cart-tab .cart-item-tile');
    if (!stillHasTiles) {
      const col = document.querySelector('.cart-tab .cart-items-column');
      if (col && !col.querySelector('.empty-message')) {
        const p = document.createElement('p');
        p.className = 'empty-message';
        p.textContent = 'You have no items in your cart yet!';
        col.appendChild(p);
      }
    }
  }
}

// Remove current listing from cart (POST), then update UI locally
function removePriceListing() {
  const entry = priceData[priceIndex];
  if (!entry || !entry.listing_id) return;

  if (!confirm('Remove this item from cart?')) return;

  fetch(`/cart/remove_item/${entry.listing_id}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then(res => {
      if (!res.ok) throw new Error('Failed to remove item.');

      // Remove locally and re-render modal view
      priceData.splice(priceIndex, 1);

      // Sync the cart tab quantities/avg price
      updateCartBucketUIFromModalState();

      // If nothing left in this bucket, close the modal; otherwise, move index if needed
      if (priceData.length === 0) {
        closePriceBreakdown();
        return;
      }
      if (priceIndex > priceData.length - 1) priceIndex = priceData.length - 1;
      renderPriceEntry();
    })
    .catch(err => {
      showCartItemsError(err?.message || 'Remove failed. Please try again.');
      console.error('removePriceListing error:', err);
    });
}

function renderPriceEntry() {
  if (!priceData.length) {
    showCartItemsError('No items to display.');
    return;
  }

  const entry = priceData[priceIndex];

  // Helpers
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c])
  );
  const DASH = '--';
  const show = v => {
    if (v === null || v === undefined) return DASH;
    if (typeof v === 'string' && v.trim() === '') return DASH;
    return esc(v);
  };
  const showNum = v =>
    (v === null || v === undefined || v === '' || Number.isNaN(Number(v)))
      ? DASH
      : String(Number(v));
  const showMoney = v =>
    (v === null || v === undefined || v === '' || Number.isNaN(Number(v)))
      ? DASH
      : '$' + Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  /* NOTE: Metadata placeholders remain until API enrichment (deferred). */
  const metal        = entry.metal ?? entry.metal_type ?? null;
  const productLine  = entry.product_line ?? entry.series ?? entry.program ?? null;
  const productType  = entry.product_type ?? entry.type ?? entry.form ?? null;

  let weightDisplay = null;
  if (entry.weight != null) {
    weightDisplay = String(entry.weight) + (entry.weight_unit ? ` ${entry.weight_unit}` : '');
  } else if (entry.weight_oz != null) {
    weightDisplay = `${entry.weight_oz} oz`;
  } else if (entry.weight_g != null) {
    weightDisplay = `${entry.weight_g} g`;
  }

  const year         = entry.year ?? null;
  const mint         = entry.mint ?? entry.mint_name ?? null;
  const purityRaw    = entry.purity ?? entry.fineness ?? entry.purity_pct ?? null;
  const finish       = entry.finish ?? entry.condition ?? null;
  const grading      = entry.grading ?? entry.grade ?? null;
  const gradingSvc   = entry.grading_service ?? entry.grader ?? null;
  const seller       = entry.seller_username ?? entry.seller_name ?? entry.seller ?? entry.username ?? null;

  const purity = (() => {
    if (purityRaw == null || purityRaw === '') return null;
    const n = Number(purityRaw);
    if (Number.isNaN(n)) return purityRaw;
    return n.toFixed(3);
  })();

  const qtyRaw   = (entry.quantity ?? entry.total_quantity ?? null);
  const priceRaw = (entry.price_per_coin ?? entry.price_each ?? entry.unit_price ?? null);
  const totalVal = (qtyRaw != null && priceRaw != null &&
                   !Number.isNaN(Number(qtyRaw)) && !Number.isNaN(Number(priceRaw)))
    ? Number(qtyRaw) * Number(priceRaw)
    : null;

  // Title
  const title =
    entry.title
    ?? entry.category_name
    ?? [
         (weightDisplay ? `${weightDisplay}` : ''),
         (metal ? `${metal}` : '')
       ].join(' ').trim() +
       (mint || year ? ` (${[mint, year].filter(Boolean).join(', ')})` : '');

  const titleEl = document.getElementById('pb-username');
  if (titleEl) titleEl.textContent = title || 'Item';

  // Image source or placeholder
  const imgSrc = (() => {
    const candidates = [
      entry.image_url, entry.listing_image_url, entry.photo_url,
      entry.photo, entry.image, entry.image_src, entry.img_src
    ];
    for (const c of candidates) {
      if (typeof c === 'string' && c.trim() !== '') return c;
    }
    const svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400'><rect width='400' height='400' fill='%23f3f4f6'/><text x='200' y='205' text-anchor='middle' font-family='Arial,Helvetica,sans-serif' font-size='28' fill='%239ca3af'>No Image</text></svg>";
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
  })();

  // Left column (11 rows, always shown)
  const leftHTML = `
    <div><dt>Metal</dt><dd>${show(metal)}</dd></div>
    <div><dt>Product line</dt><dd>${show(productLine)}</dd></div>
    <div><dt>Product type</dt><dd>${show(productType)}</dd></div>
    <div><dt>Weight</dt><dd>${show(weightDisplay)}</dd></div>
    <div><dt>Year</dt><dd>${show(year)}</dd></div>
    <div><dt>Mint</dt><dd>${show(mint)}</dd></div>
    <div><dt>Purity</dt><dd>${show(purity)}</dd></div>
    <div><dt>Finish</dt><dd>${show(finish)}</dd></div>
    <div><dt>Grading</dt><dd>${show(grading)}</dd></div>
    <div><dt>Grading service</dt><dd>${show(gradingSvc)}</dd></div>
    <div><dt>Seller</dt><dd>${show(seller)}</dd></div>
  `;

  const body = document.getElementById('pb-modal-content');
  if (!body) return;
  body.innerHTML = `
    <div class="cart-items-two-col">
      <div class="cart-items-col-left">
        <dl class="kv-list">${leftHTML}</dl>
      </div>

      <div class="cart-items-col-right">
        <div class="cart-items-image-wrap">
          <img class="cart-items-image" src="${imgSrc}" alt="Product image">
        </div>

        <div class="kv"><span>Quantity</span><span class="value">${showNum(qtyRaw)}</span></div>
        <div class="kv"><span>Price / item</span><span class="value">${showMoney(priceRaw)}</span></div>
        <div class="kv total"><span>Total</span><span class="value">${showMoney(totalVal)}</span></div>

        <button id="pb-remove-btn" class="cart-items-remove-btn" type="button">
           <i class="fas fa-trash"></i> Remove Item
        </button>
      </div>
    </div>
  `;

  // Hook remove button
  const removeBtn = document.getElementById('pb-remove-btn');
  if (removeBtn) {
    removeBtn.onclick = removePriceListing;
  }

  // Nav enable/disable
  const prevBtn = document.getElementById('pb-prev');
  const nextBtn = document.getElementById('pb-next');
  if (prevBtn && nextBtn) {
    if (priceData.length <= 1) {
      prevBtn.disabled = true;
      nextBtn.disabled = true;
    } else {
      prevBtn.disabled = (priceIndex === 0);
      nextBtn.disabled = (priceIndex === priceData.length - 1);
    }
  }
}

// expose globals for inline onclicks
window.openPriceBreakdown   = openPriceBreakdown;
window.closePriceBreakdown  = closePriceBreakdown;
window.prevPriceListing     = prevPriceListing;
window.nextPriceListing     = nextPriceListing;
window.removePriceListing   = removePriceListing;
