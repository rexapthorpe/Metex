// order_items_modal.js

let orderItemsData = [];
let currentItemIndex = 0;
let currentOrderId = null;

// Set item sub-navigation state (for when an order item is a set listing)
let _oimSetSubItems = [];
let _oimSetSubIndex = 0;

let orderItemsOptions = {
  context: 'orders',   // 'orders' | 'cart'
  onRemove: null
};

function showOrderItemsModal() {
  const modal = document.getElementById('orderItemsModal');
  if (!modal) return;
  modal.style.display = 'flex';
  modal.addEventListener('click', outsideClickItems);
  document.addEventListener('keydown', keyNavHandler);
}

function closeOrderItemsPopup() {
  const modal = document.getElementById('orderItemsModal');
  if (!modal) return;
  modal.style.display = 'none';
  modal.removeEventListener('click', outsideClickItems);
  document.removeEventListener('keydown', keyNavHandler);
}

function outsideClickItems(e) {
  if (e.target && e.target.id === 'orderItemsModal') closeOrderItemsPopup();
}

function keyNavHandler(e) {
  if (e.key === 'ArrowLeft') prevOrderItem();
  else if (e.key === 'ArrowRight') nextOrderItem();
  else if (e.key === 'Escape') closeOrderItemsPopup();
}

function showOrderItemsError(message) {
  const body = document.getElementById('orderItemsModalContent');
  if (!body) return;
  body.innerHTML = `
    <div class="order-items-error">
      <div class="order-items-error-title">Couldn't load items</div>
      <div class="order-items-error-msg">${message ? String(message) : 'Please try again.'}</div>
    </div>
  `;
}

function openOrderItemsPopup(orderId, options = {}) {
  currentOrderId = orderId;
  orderItemsOptions = { context: 'orders', onRemove: null, ...options };

  showOrderItemsModal();
  const body = document.getElementById('orderItemsModalContent');
  if (body) body.innerHTML = '<div class="order-items-loading">Loading&hellip;</div>';

  const subtitleEl = document.getElementById('orderItemsModalSubtitle');
  if (subtitleEl) subtitleEl.textContent = 'Loading\u2026';

  fetch(`/orders/api/${orderId}/order_items`)
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then(data => {
      orderItemsData = Array.isArray(data) ? data : [];
      currentItemIndex = 0;
      if (!orderItemsData.length) {
        showOrderItemsError('No items found for this order.');
        return;
      }
      renderOrderItem();
    })
    .catch(err => {
      showOrderItemsError(err?.message || 'Unexpected error.');
      console.error('order_items fetch error:', err);
    });
}

function openCartItemsPopup(items, options = {}) {
  currentOrderId = null;
  orderItemsOptions = { context: 'cart', onRemove: null, ...options };
  orderItemsData = Array.isArray(items) ? items : [];
  currentItemIndex = 0;
  showOrderItemsModal();

  if (!orderItemsData.length) {
    showOrderItemsError('No items in this cart view.');
    return;
  }
  renderOrderItem();
}

function prevOrderItem() {
  if (currentItemIndex > 0) { currentItemIndex--; _oimSetSubItems = []; _oimSetSubIndex = 0; renderOrderItem(); }
}

function nextOrderItem() {
  if (currentItemIndex < orderItemsData.length - 1) { currentItemIndex++; _oimSetSubItems = []; _oimSetSubIndex = 0; renderOrderItem(); }
}

// ---- Set item sub-navigation (for set listings within an order) ----

function _oimPrevSetSubItem() {
  if (_oimSetSubIndex > 0) { _oimSetSubIndex--; _oimRenderSetSubItem(); }
}

function _oimNextSetSubItem() {
  if (_oimSetSubIndex < _oimSetSubItems.length - 1) { _oimSetSubIndex++; _oimRenderSetSubItem(); }
}

function _oimLoadSetSubItems(listingId) {
  const grid = document.getElementById('oim-set-specs-grid');
  if (grid) grid.innerHTML = '<span style="color:#9ca3af;font-size:0.85rem">Loading set items\u2026</span>';

  fetch(`/api/listings/${listingId}/details`)
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => {
      _oimSetSubItems = data.set_items || [];
      _oimSetSubIndex = 0;
      _oimRenderSetSubItem();
    })
    .catch(() => {
      const g = document.getElementById('oim-set-specs-grid');
      if (g) g.innerHTML = '<span style="color:#9ca3af;font-size:0.85rem">Could not load set items.</span>';
    });
}

function _oimRenderSetSubItem() {
  const item = _oimSetSubItems[_oimSetSubIndex];
  if (!item) return;

  // Update sub-nav arrows
  const subnav = document.getElementById('oim-set-subnav');
  if (subnav) {
    subnav.style.display = _oimSetSubItems.length > 1 ? 'flex' : 'none';
    subnav.innerHTML = _oimSetSubItems.length > 1 ? `
      <button class="oim-nav-arrow" ${_oimSetSubIndex === 0 ? 'disabled' : ''} onclick="_oimPrevSetSubItem()">&#8592;</button>
      <span class="oim-nav-counter">Set Item ${_oimSetSubIndex + 1} of ${_oimSetSubItems.length}</span>
      <button class="oim-nav-arrow" ${_oimSetSubIndex === _oimSetSubItems.length - 1 ? 'disabled' : ''} onclick="_oimNextSetSubItem()">&#8594;</button>
    ` : '';
  }

  // Build specs grid from set item data
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

  const grid = document.getElementById('oim-set-specs-grid');
  if (grid) grid.innerHTML = specsHtml || '<span style="color:#9ca3af;font-size:0.85rem">No specifications available</span>';
}

function renderOrderItem() {
  if (!orderItemsData.length) {
    showOrderItemsError('No items to display.');
    return;
  }

  const item = orderItemsData[currentItemIndex];
  const total = orderItemsData.length;

  // Helpers
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
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

  // Normalize fields
  const metal       = item.metal ?? item.metal_type ?? null;
  const productType = item.product_type ?? item.type ?? item.form ?? null;
  const mint        = item.mint ?? item.mint_name ?? null;
  const year        = item.year ?? null;
  const finish      = item.finish ?? null;
  const grade       = item.grade ?? null;
  const purityRaw   = item.purity ?? item.fineness ?? null;
  const certSvc     = item.grading_service ?? null;
  const seriesVariant  = item.series_variant ?? null;
  const isIsolated     = item.is_isolated === 1 || item.is_isolated === '1' || item.is_isolated === true;
  const isolatedType   = item.isolated_type ?? null;
  const packagingType  = item.packaging_type ?? null;
  const packagingNotes = item.packaging_notes ?? null;
  const editionNumber  = item.edition_number ?? null;
  const editionTotal   = item.edition_total ?? null;
  const conditionNotes = item.condition_notes ?? null;

  // Weight
  let weightDisplay = null;
  if (item.weight != null) {
    weightDisplay = String(item.weight) + (item.weight_unit ? ` ${item.weight_unit}` : '');
  } else if (item.weight_oz != null) {
    weightDisplay = `${item.weight_oz} oz`;
  }

  // Purity formatting
  const purity = (() => {
    if (purityRaw == null || purityRaw === '') return null;
    const n = Number(purityRaw);
    if (Number.isNaN(n)) return purityRaw;
    return n < 1 ? n.toFixed(4).replace(/\.?0+$/, '') : n.toFixed(3);
  })();

  // Certification: skip generic "No 3rd Party..." string
  const certDisplay = (certSvc && !certSvc.startsWith('No 3rd')) ? certSvc : null;

  // Qty and price
  const qtyRaw   = item.total_quantity ?? item.quantity ?? null;
  const priceRaw = item.price_each ?? item.unit_price ?? null;
  const itemTotal = (qtyRaw != null && priceRaw != null)
    ? Number(qtyRaw) * Number(priceRaw)
    : null;

  // Overall subtotal across all groups
  const overallSubtotal = orderItemsData.reduce((sum, g) => {
    const qty   = g.total_quantity ?? g.quantity ?? 0;
    const price = g.price_each ?? g.unit_price ?? 0;
    return sum + (Number(qty) * Number(price));
  }, 0);

  // Total quantity across all groups (for subtitle and summary label)
  const totalQty = orderItemsData.reduce((sum, g) =>
    sum + Number(g.total_quantity ?? g.quantity ?? 0), 0);

  // Update subtitle in static header
  const subtitleEl = document.getElementById('orderItemsModalSubtitle');
  if (subtitleEl) {
    const currentYear = new Date().getFullYear();
    const orderLabel = currentOrderId
      ? `Order #ORD-${currentYear}-${String(currentOrderId).padStart(6, '0')} \u2022 `
      : '';
    subtitleEl.textContent = `${orderLabel}${totalQty} item${totalQty === 1 ? '' : 's'}`;
  }

  // Item title
  const title = item.title
    ?? ([year, metal, item.product_line, productType].filter(Boolean).join(' ') || 'Item');

  // Image
  const imgSrc = (() => {
    const candidates = [
      item.image_url, item.photo_url, item.photo,
      item.image, item.listing_image_url
    ];
    for (const c of candidates) {
      if (typeof c === 'string' && c.trim() !== '') return c;
    }
    return null;
  })();
  const imgHtml = imgSrc
    ? `<img class="oim-item-image" src="${imgSrc}" alt="Product image" onerror="this.style.display='none'">`
    : `<div class="oim-item-image oim-item-image-placeholder"></div>`;

  // Nav arrows (only if multiple item groups)
  const navHtml = total > 1 ? `
    <div class="oim-nav">
      <button class="oim-nav-arrow" ${currentItemIndex === 0 ? 'disabled' : ''} onclick="prevOrderItem()">&#8592;</button>
      <span class="oim-nav-counter">${currentItemIndex + 1} of ${total}</span>
      <button class="oim-nav-arrow" ${currentItemIndex === total - 1 ? 'disabled' : ''} onclick="nextOrderItem()">&#8594;</button>
    </div>
  ` : '';

  // Spec helper: returns empty string if value is null/DASH
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

  const productLine = item.product_line ?? item.series ?? null;
  const seller      = item.seller_username ?? item.seller_name ?? null;

  const specsGrid = [
    specItem('<i class="fa-solid fa-tag"></i>',               'Category',       productType),
    specItem('<i class="fa-solid fa-gem"></i>',               'Metal Type',     metal),
    specItem('<i class="fa-solid fa-coins"></i>',             'Product Line',   productLine),
    specItem('<i class="fa-solid fa-scale-balanced"></i>',    'Weight',         weightDisplay),
    specItem('<i class="fa-solid fa-layer-group"></i>',       'Purity',         purity),
    specItem('<i class="fa-solid fa-building-columns"></i>',  'Mint',           mint),
    specItem('<i class="fa-regular fa-calendar"></i>',        'Year',           year),
    specItem('<i class="fa-solid fa-certificate"></i>',       'Finish',         finish),
    specItem('<i class="fa-solid fa-medal"></i>',             'Grade',          grade),
    specItem('<i class="fa-solid fa-shield-halved"></i>',     'Certification',  certDisplay),
    specItem('<i class="fa-solid fa-star"></i>',              'Series',         seriesVariant),
    ...(isIsolated && isolatedType !== 'set' ? [
      specItem('<i class="fa-solid fa-box"></i>',             'Packaging',      packagingType ? packagingType.replace(/_/g, ' ') : null),
      specItem('<i class="fa-solid fa-clipboard"></i>',       'Pkg. Notes',     packagingNotes),
      specItem('<i class="fa-solid fa-hashtag"></i>',         'Edition',        (editionNumber && editionTotal) ? `#${editionNumber} of ${editionTotal}` : null),
      specItem('<i class="fa-solid fa-info-circle"></i>',     'Condition',      conditionNotes),
    ] : []),
    specItem('<i class="fa-regular fa-user"></i>',            'Seller',         seller),
  ].filter(Boolean).join('');

  // Remove button (cart context only)
  const removeBtnHTML = (orderItemsOptions.context === 'cart')
    ? `<button class="order-items-remove-btn" type="button">Remove Item</button>`
    : '';

  // Detect set listing for sub-navigation
  const isSetListing = item.isolated_type === 'set';
  const setListingId = item.listing_id ?? (item.items && item.items[0] ? item.items[0].listing_id : null);

  const specsSection = isSetListing ? `
    <div class="oim-specs-section">
      <div class="oim-set-title-row">
        <span class="oim-specs-title">Set Items</span>
        <div class="oim-set-subnav" id="oim-set-subnav" style="display:none;"></div>
      </div>
      <div class="oim-specs-grid" id="oim-set-specs-grid">
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

  const body = document.getElementById('orderItemsModalContent');
  if (!body) return;

  body.innerHTML = `
    ${navHtml}

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
        <span>Subtotal (${totalQty} item${totalQty === 1 ? '' : 's'})</span>
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

    ${removeBtnHTML}
  `;

  // Hook remove action if in cart context
  if (orderItemsOptions.context === 'cart') {
    const btn = document.querySelector('.order-items-remove-btn');
    if (btn && typeof orderItemsOptions.onRemove === 'function') {
      btn.addEventListener('click', () => orderItemsOptions.onRemove(item, currentItemIndex));
    }
  }

  // Async load set items for set listings
  if (isSetListing && setListingId) {
    _oimLoadSetSubItems(setListingId);
  }
}

// Expose globals
window.openOrderItemsPopup  = openOrderItemsPopup;
window.openCartItemsPopup   = openCartItemsPopup;
window.prevOrderItem        = prevOrderItem;
window.nextOrderItem        = nextOrderItem;
window.closeOrderItemsPopup = closeOrderItemsPopup;
window._oimPrevSetSubItem   = _oimPrevSetSubItem;
window._oimNextSetSubItem   = _oimNextSetSubItem;
