// cart_individual_listings_modal.js

let priceData = [];
let priceIndex = 0;
let priceBucketId = null; // track which bucket the modal is showing

// Set item sub-navigation state (for when a cart listing is a set type)
let _pbSetSubItems = [];
let _pbSetSubIndex = 0;

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
    _pbSetSubItems = []; _pbSetSubIndex = 0;
    renderPriceEntry();
  }
}

function nextPriceListing() {
  if (priceIndex < priceData.length - 1) {
    priceIndex++;
    _pbSetSubItems = []; _pbSetSubIndex = 0;
    renderPriceEntry();
  }
}

// ---- Set item sub-navigation (for set listings in cart) ----

function _pbPrevSetSubItem() {
  if (_pbSetSubIndex > 0) { _pbSetSubIndex--; _pbRenderSetSubItem(); }
}

function _pbNextSetSubItem() {
  if (_pbSetSubIndex < _pbSetSubItems.length - 1) { _pbSetSubIndex++; _pbRenderSetSubItem(); }
}

function _pbLoadSetSubItems(listingId) {
  const grid = document.getElementById('pb-set-specs-grid');
  if (grid) grid.innerHTML = '<span style="color:#9ca3af;font-size:0.85rem">Loading set items\u2026</span>';

  fetch(`/api/listings/${listingId}/details`)
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => {
      _pbSetSubItems = data.set_items || [];
      _pbSetSubIndex = 0;
      _pbRenderSetSubItem();
    })
    .catch(() => {
      const g = document.getElementById('pb-set-specs-grid');
      if (g) g.innerHTML = '<span style="color:#9ca3af;font-size:0.85rem">Could not load set items.</span>';
    });
}

function _pbRenderSetSubItem() {
  const item = _pbSetSubItems[_pbSetSubIndex];
  if (!item) return;

  const subnav = document.getElementById('pb-set-subnav');
  if (subnav) {
    subnav.style.display = _pbSetSubItems.length > 1 ? 'flex' : 'none';
    subnav.innerHTML = _pbSetSubItems.length > 1 ? `
      <button class="oim-nav-arrow" ${_pbSetSubIndex === 0 ? 'disabled' : ''} onclick="_pbPrevSetSubItem()">&#8592;</button>
      <span class="oim-nav-counter">Set Item ${_pbSetSubIndex + 1} of ${_pbSetSubItems.length}</span>
      <button class="oim-nav-arrow" ${_pbSetSubIndex === _pbSetSubItems.length - 1 ? 'disabled' : ''} onclick="_pbNextSetSubItem()">&#8594;</button>
    ` : '';
  }

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
  const specRow = (icon, label, value) => {
    if (value === null || value === undefined || String(value).trim() === '') return '';
    return `<div class="oim-spec-item">
      <span class="oim-spec-icon">${icon}</span>
      <span class="oim-spec-label">${label}:</span>
      <span class="oim-spec-value">${esc(value)}</span>
    </div>`;
  };
  const purityRaw = item.purity;
  const purityFmt = (() => {
    if (purityRaw == null || purityRaw === '') return null;
    const n = Number(purityRaw);
    return Number.isNaN(n) ? String(purityRaw) : '.' + String(n).replace(/^0\./, '').replace('.', '');
  })();

  const specsHtml = [
    specRow('<i class="fa-solid fa-gem"></i>',                'Metal',        item.metal),
    specRow('<i class="fa-regular fa-calendar"></i>',         'Year',         item.year),
    specRow('<i class="fa-solid fa-coins"></i>',              'Product Line', item.product_line),
    specRow('<i class="fa-solid fa-building-columns"></i>',   'Mint',         item.mint),
    specRow('<i class="fa-solid fa-tag"></i>',                'Type',         item.product_type),
    specRow('<i class="fa-solid fa-layer-group"></i>',        'Purity',       purityFmt),
    specRow('<i class="fa-solid fa-scale-balanced"></i>',     'Weight',       item.weight),
    specRow('<i class="fa-solid fa-wand-magic-sparkles"></i>','Finish',       item.finish),
    specRow('<i class="fa-solid fa-box"></i>',                'Packaging',    item.packaging_type),
    ...(item.graded ? [specRow('<i class="fa-solid fa-certificate"></i>', 'Grading', item.grading_service)] : []),
    ...(item.condition_notes ? [specRow('<i class="fa-solid fa-info-circle"></i>', 'Condition', item.condition_notes)] : []),
  ].filter(Boolean).join('');

  const grid = document.getElementById('pb-set-specs-grid');
  if (grid) grid.innerHTML = specsHtml || '<span style="color:#9ca3af;font-size:0.85rem">No specifications available</span>';
}

// ===== UI sync helpers =====
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

  // Try to find tile on cart tab first, then main cart page
  const tile = document.querySelector(
    `.cart-tab .cart-item-tile[data-bucket-id="${priceBucketId}"]`
  ) || document.querySelector(
    `.cart-item-tile[data-bucket-id="${priceBucketId}"]`
  );

  if (!tile) {
    // Tile not found in DOM, reload page to sync
    setTimeout(() => location.reload(), 300);
    return;
  }

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
      ? formatPrice(newAvg)
      : '--';
  }

  // If bucket became empty, reload page to show updated state
  if (totalQty <= 0) {
    closePriceBreakdown();
    setTimeout(() => location.reload(), 300);
  }
}

// Remove current listing from cart (POST), then update UI locally
function removePriceListing() {
  const entry = priceData[priceIndex];
  if (!entry || !entry.listing_id) return;

  // Fetch the actual refill status from backend
  fetch(`/cart/api/bucket/${priceBucketId}/can_refill_listing/${entry.listing_id}`)
    .then(res => res.json())
    .then(data => {
      const canRefill = data.canRefill;
      console.log('[Individual Listings] canRefill:', canRefill, 'availableCount:', data.availableCount);

      // Open custom confirmation modal with callback to handle UI updates
      openRemoveListingConfirmation(entry.listing_id, () => {
        // Remove locally from priceData
        priceData.splice(priceIndex, 1);

        // If nothing left in this bucket, close modal and reload
        if (priceData.length === 0) {
          closePriceBreakdown();
          setTimeout(() => location.reload(), 300);
          return;
        }

        // Adjust index if needed and re-render
        if (priceIndex > priceData.length - 1) {
          priceIndex = priceData.length - 1;
        }
        renderPriceEntry();

        // Update cart quantities and prices in the background
        updateCartBucketUIFromModalState();
      }, canRefill);
    })
    .catch(err => {
      console.error('[Individual Listings] Error checking refill:', err);
      // Default to safe behavior - assume no refill possible
      openRemoveListingConfirmation(entry.listing_id, () => {
        priceData.splice(priceIndex, 1);
        if (priceData.length === 0) {
          closePriceBreakdown();
          setTimeout(() => location.reload(), 300);
          return;
        }
        if (priceIndex > priceData.length - 1) {
          priceIndex = priceData.length - 1;
        }
        renderPriceEntry();
        updateCartBucketUIFromModalState();
      }, false);
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
  const DASH = '\u2014';
  const show = v => {
    if (v === null || v === undefined) return DASH;
    if (typeof v === 'string' && v.trim() === '') return DASH;
    return esc(v);
  };
  const showMoney = v =>
    (v === null || v === undefined || v === '' || Number.isNaN(Number(v)))
      ? DASH
      : '$' + Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const metal       = entry.metal ?? entry.metal_type ?? null;
  const productType = entry.product_type ?? entry.type ?? entry.form ?? null;
  const mint        = entry.mint ?? entry.mint_name ?? null;
  const entryYear   = entry.year ?? null;
  const finish      = entry.finish ?? entry.condition ?? null;
  const grade       = entry.grading ?? entry.grade ?? null;
  const purityRaw   = entry.purity ?? entry.fineness ?? entry.purity_pct ?? null;

  let weightDisplay = null;
  if (entry.weight != null) {
    weightDisplay = String(entry.weight) + (entry.weight_unit ? ` ${entry.weight_unit}` : '');
  } else if (entry.weight_oz != null) {
    weightDisplay = `${entry.weight_oz} oz`;
  } else if (entry.weight_g != null) {
    weightDisplay = `${entry.weight_g} g`;
  }

  const purity = (() => {
    if (purityRaw == null || purityRaw === '') return null;
    const n = Number(purityRaw);
    if (Number.isNaN(n)) return purityRaw;
    return n < 1 ? n.toFixed(4).replace(/\.?0+$/, '') : n.toFixed(3);
  })();

  // Certification: only show if actually graded
  const gradedFlag = entry.graded;
  const certDisplay = (gradedFlag === 1 || gradedFlag === '1' || gradedFlag === true)
    ? (entry.grading_service ?? entry.grader ?? null)
    : null;

  const qtyRaw   = entry.quantity ?? entry.total_quantity ?? null;
  const priceRaw = entry.price_per_coin ?? entry.price_each ?? entry.unit_price ?? null;
  const itemTotal = (qtyRaw != null && priceRaw != null)
    ? Number(qtyRaw) * Number(priceRaw)
    : null;

  // Overall subtotal and total qty across all listings in this bucket
  const overallSubtotal = priceData.reduce((sum, e) => {
    const q = Number(e.quantity ?? e.total_quantity ?? 0);
    const p = Number(e.price_per_coin ?? e.price_each ?? e.unit_price ?? 0);
    return sum + (q * p);
  }, 0);
  const totalQty = priceData.reduce((sum, e) =>
    sum + Number(e.quantity ?? e.total_quantity ?? 0), 0);

  // Update subtitle
  const subtitleEl = document.getElementById('pb-subtitle');
  if (subtitleEl) {
    subtitleEl.textContent = `${totalQty} listing${totalQty === 1 ? '' : 's'} in cart`;
  }

  // Item title
  const title = entry.title
    ?? entry.category_name
    ?? ([entryYear, metal, entry.product_line, productType].filter(Boolean).join(' ') || 'Item');

  // Image
  const imgSrc = (() => {
    const candidates = [
      entry.image_url, entry.photo_url, entry.photo, entry.image,
      entry.listing_image_url, entry.image_src, entry.img_src
    ];
    for (const c of candidates) {
      if (typeof c === 'string' && c.trim() !== '') return c;
    }
    if (entry.photo_filename) {
      return `/static/uploads/listings/${encodeURIComponent(entry.photo_filename)}`;
    }
    return null;
  })();
  const imgHtml = imgSrc
    ? `<img class="oim-item-image" src="${imgSrc}" alt="Product image" onerror="this.style.display='none'">`
    : `<div class="oim-item-image oim-item-image-placeholder"></div>`;

  // Nav show/hide
  const navRow = document.getElementById('pb-nav-row');
  if (navRow) navRow.style.display = priceData.length <= 1 ? 'none' : 'flex';
  const counterEl = document.getElementById('pb-counter');
  if (counterEl) counterEl.textContent = `${priceIndex + 1} of ${priceData.length}`;

  // Spec helper
  const specItem = (iconHtml, label, value) => {
    const displayed = show(value);
    if (displayed === DASH) return '';
    return `
      <div class="oim-spec-item">
        <span class="oim-spec-icon">${iconHtml}</span>
        <span class="oim-spec-label">${label}:</span>
        <span class="oim-spec-value">${displayed}</span>
      </div>
    `;
  };

  const productLine  = entry.product_line ?? entry.series ?? entry.coin_series ?? null;
  const seriesVariant = entry.series_variant ?? null;
  const seller       = entry.seller_username ?? entry.seller_name ?? null;

  const specsGrid = [
    specItem('<i class="fa-solid fa-tag"></i>',              'Category',      productType),
    specItem('<i class="fa-solid fa-gem"></i>',              'Metal Type',    metal),
    specItem('<i class="fa-solid fa-coins"></i>',            'Product Line',  productLine),
    specItem('<i class="fa-solid fa-scale-balanced"></i>',   'Weight',        weightDisplay),
    specItem('<i class="fa-solid fa-layer-group"></i>',      'Purity',        purity),
    specItem('<i class="fa-solid fa-building-columns"></i>', 'Mint',          mint),
    specItem('<i class="fa-regular fa-calendar"></i>',       'Year',          entryYear),
    specItem('<i class="fa-solid fa-certificate"></i>',      'Finish',        finish),
    specItem('<i class="fa-solid fa-medal"></i>',            'Grade',         grade),
    specItem('<i class="fa-solid fa-shield-halved"></i>',    'Certification', certDisplay),
    specItem('<i class="fa-solid fa-star"></i>',             'Series',        seriesVariant),
    specItem('<i class="fa-regular fa-user"></i>',           'Seller',        seller),
  ].filter(Boolean).join('');

  // Detect set listing for sub-navigation
  const isSetListing = entry.isolated_type === 'set';
  const setListingId = entry.listing_id ?? null;

  const specsSection = isSetListing ? `
    <div class="oim-specs-section">
      <div class="oim-set-title-row">
        <span class="oim-specs-title">Set Items</span>
        <div class="oim-set-subnav" id="pb-set-subnav" style="display:none;"></div>
      </div>
      <div class="oim-specs-grid" id="pb-set-specs-grid">
        <span style="color:#9ca3af;font-size:0.85rem">Loading\u2026</span>
      </div>
    </div>
  ` : `
    <div class="oim-specs-section">
      <div class="oim-specs-title">Specifications</div>
      <div class="oim-specs-grid">
        ${specsGrid || `<span style="color:#9ca3af;font-size:0.85rem">No specifications available</span>`}
      </div>
    </div>
  `;

  const body = document.getElementById('pb-modal-content');
  if (!body) return;

  body.innerHTML = `
    <div class="oim-item-row">
      ${imgHtml}
      <div class="oim-item-details">
        <div class="oim-item-title-row">
          <div class="oim-item-title">${esc(title)}</div>
          <div class="oim-item-price">${showMoney(itemTotal)}</div>
        </div>
        <div class="oim-item-qty-row">
          <span class="oim-qty-badge">Qty: ${qtyRaw ?? '\u2014'}</span>
          <span>@ ${showMoney(priceRaw)} each</span>
        </div>
      </div>
    </div>

    ${specsSection}

    <hr class="oim-summary-divider">

    <div class="oim-summary">
      <div class="oim-summary-row">
        <span>Subtotal (${totalQty} listing${totalQty === 1 ? '' : 's'})</span>
        <span>${showMoney(overallSubtotal)}</span>
      </div>
      <div class="oim-summary-row">
        <span>Shipping</span>
        <span class="oim-shipping-free">Free</span>
      </div>
      <div class="oim-summary-row total">
        <span>Total</span>
        <span class="oim-summary-value">${showMoney(overallSubtotal)}</span>
      </div>
    </div>

    <button id="pb-remove-btn" class="cart-items-remove-btn" type="button">
      <i class="fa-solid fa-trash"></i> Remove Item
    </button>
  `;

  // Hook remove button
  const removeBtn = document.getElementById('pb-remove-btn');
  if (removeBtn) removeBtn.onclick = removePriceListing;

  // Nav enable/disable
  const prevBtn = document.getElementById('pb-prev');
  const nextBtn = document.getElementById('pb-next');
  if (prevBtn && nextBtn) {
    prevBtn.disabled = (priceIndex === 0);
    nextBtn.disabled = (priceIndex === priceData.length - 1);
  }

  // Async load set items for set listings
  if (isSetListing && setListingId) {
    _pbLoadSetSubItems(setListingId);
  }
}

// expose globals for inline onclicks
window.openPriceBreakdown   = openPriceBreakdown;
window.closePriceBreakdown  = closePriceBreakdown;
window.prevPriceListing     = prevPriceListing;
window.nextPriceListing     = nextPriceListing;
window.removePriceListing   = removePriceListing;
window._pbPrevSetSubItem    = _pbPrevSetSubItem;
window._pbNextSetSubItem    = _pbNextSetSubItem;
