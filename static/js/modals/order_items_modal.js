// order_items_modal.js

let orderItemsData = [];
let currentItemIndex = 0;

// controls whether "Remove Item" shows, and lets you hook a remover
let orderItemsOptions = {
  context: 'orders',          // 'orders' | 'cart'
  onRemove: null              // function(item, index) { ... }
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
  if (e.target && e.target.id === 'orderItemsModal') {
    closeOrderItemsPopup();
  }
}

function keyNavHandler(e) {
  if (e.key === 'ArrowLeft') prevOrderItem();
  else if (e.key === 'ArrowRight') nextOrderItem();
  else if (e.key === 'Escape') closeOrderItemsPopup(); // keep keyboard accessibility
}

function showOrderItemsError(message) {
  const body = document.getElementById('orderItemsModalContent');
  if (!body) return;
  body.innerHTML = `
    <div class="order-items-error">
      <div class="order-items-error-title">Couldn’t load items</div>
      <div class="order-items-error-msg">${message ? String(message) : 'Please try again.'}</div>
    </div>
  `;
}

function openOrderItemsPopup(orderId, options = {}) {
  orderItemsOptions = { context: 'orders', onRemove: null, ...options };

  // Open with loading state (no alerts)
  showOrderItemsModal();
  const body = document.getElementById('orderItemsModalContent');
  if (body) body.innerHTML = '<div class="order-items-loading">Loading…</div>';

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

// Use this for the Cart context (you provide the items array)
function openCartItemsPopup(items, options = {}) {
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
  if (currentItemIndex > 0) {
    currentItemIndex--;
    renderOrderItem();
  }
}

function nextOrderItem() {
  if (currentItemIndex < orderItemsData.length - 1) {
    currentItemIndex++;
    renderOrderItem();
  }
}

function renderOrderItem() {
  if (!orderItemsData.length) {
    showOrderItemsError('No items to display.');
    return;
  }

  const item = orderItemsData[currentItemIndex];

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

  // Normalize/alias fields (tolerate name drift from backend)
  const metal        = item.metal ?? item.metal_type ?? null;
  const productLine  = item.product_line ?? item.series ?? item.program ?? null;
  const productType  = item.product_type ?? item.type ?? item.form ?? null;

  // Weight: prefer explicit unit if provided
  let weightDisplay = null;
  if (item.weight != null) {
    weightDisplay = String(item.weight) + (item.weight_unit ? ` ${item.weight_unit}` : '');
  } else if (item.weight_oz != null) {
    weightDisplay = `${item.weight_oz} oz`;
  } else if (item.weight_g != null) {
    weightDisplay = `${item.weight_g} g`;
  }

  const year         = item.year ?? null;
  const mint         = item.mint ?? item.mint_name ?? null;
  const purityRaw    = item.purity ?? item.fineness ?? item.purity_pct ?? null;
  const finish       = item.finish ?? item.condition ?? null;
  const grading      = item.grading ?? item.grade ?? null;
  const gradingSvc   = item.grading_service ?? item.grader ?? null;
  const seller       = item.seller_username ?? item.seller_name ?? item.seller ?? null;

  // Purity formatting: show provided text as-is; if numeric, render as 0.999
  const purity = (() => {
    if (purityRaw == null || purityRaw === '') return null;
    const n = Number(purityRaw);
    if (Number.isNaN(n)) return purityRaw;
    return n.toFixed(3); // e.g., 0.999
  })();

  // Combined grading field: "Requires 3rd Party Grading"
  // Check item.graded flag (1 = yes, 0 = no)
  const requiresGrading = (() => {
    const gradedFlag = item.graded ?? item.is_graded ?? null;
    if (gradedFlag === 1 || gradedFlag === '1' || gradedFlag === true) {
      // Graded = Yes, show "Yes (SERVICE)" if service is available
      if (gradingSvc) {
        return `Yes (${gradingSvc})`;
      }
      return 'Yes';
    } else if (gradedFlag === 0 || gradedFlag === '0' || gradedFlag === false) {
      return 'No';
    }
    return null;
  })();

  // Numbers: do not default to 0; show "--" if missing
  const qtyRaw   = (item.total_quantity ?? item.quantity ?? null);
  const priceRaw = (item.price_each ?? item.unit_price ?? item.price_per_coin ?? null);
  const totalVal = (qtyRaw != null && priceRaw != null &&
                    !Number.isNaN(Number(qtyRaw)) && !Number.isNaN(Number(priceRaw)))
    ? Number(qtyRaw) * Number(priceRaw)
    : null;

  // Title
  const title =
    item.title
    ?? item.category_name
    ?? [
         (weightDisplay ? `${weightDisplay}` : ''),
         (metal ? `${metal}` : '')
       ].join(' ').trim() +
       (mint || year ? ` (${[mint, year].filter(Boolean).join(', ')})` : '');

  const titleEl = document.getElementById('orderItemsModalTitle');
  if (titleEl) titleEl.textContent = title || 'Item';

  // Determine image source (fallback to built-in SVG placeholder)
  const imgSrc = (() => {
    const candidates = [
      item.image_url, item.photo_url, item.photo, item.image,
      item.listing_image_url, item.image_src, item.img_src
    ];
    for (const c of candidates) {
      if (typeof c === 'string' && c.trim() !== '') return c;
    }
    const svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400'><rect width='400' height='400' fill='%23f3f4f6'/><text x='200' y='205' text-anchor='middle' font-family='Arial,Helvetica,sans-serif' font-size='28' fill='%239ca3af'>No Image</text></svg>";
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
  })();

  // Right column: show Remove only in cart context
  const removeBtnHTML = (orderItemsOptions.context === 'cart')
    ? `<button class="order-items-remove-btn" type="button">Remove Item</button>`
    : '';

  // Left column: ALWAYS render these 10 rows (label left, value right)
  const leftHTML = `
    <div><dt>Metal</dt><dd>${show(metal)}</dd></div>
    <div><dt>Product line</dt><dd>${show(productLine)}</dd></div>
    <div><dt>Product type</dt><dd>${show(productType)}</dd></div>
    <div><dt>Weight</dt><dd>${show(weightDisplay)}</dd></div>
    <div><dt>Year</dt><dd>${show(year)}</dd></div>
    <div><dt>Mint</dt><dd>${show(mint)}</dd></div>
    <div><dt>Purity</dt><dd>${show(purity)}</dd></div>
    <div><dt>Finish</dt><dd>${show(finish)}</dd></div>
    <div><dt>Requires 3rd Party Grading</dt><dd>${show(requiresGrading)}</dd></div>
    <div><dt>Seller</dt><dd>${show(seller)}</dd></div>
  `;

  const body = document.getElementById('orderItemsModalContent');
  if (!body) return;
  body.innerHTML = `
    <div class="order-items-two-col">
      <div class="order-items-col-left">
        <dl class="kv-list">${leftHTML}</dl>
      </div>

      <div class="order-items-col-right">
        <div class="order-items-image-wrap">
          <img class="order-items-image" src="${imgSrc}" alt="Product image">
        </div>

        <div class="kv"><span>Quantity</span><span class="value">${showNum(qtyRaw)}</span></div>
        <div class="kv"><span>Price / item</span><span class="value">${showMoney(priceRaw)}</span></div>
        <div class="kv total"><span>Total</span><span class="value">${showMoney(totalVal)}</span></div>
        ${removeBtnHTML}
      </div>
    </div>
  `;

  // Hook remove action if present
  if (orderItemsOptions.context === 'cart') {
    const btn = document.querySelector('.order-items-remove-btn');
    if (btn && typeof orderItemsOptions.onRemove === 'function') {
      btn.addEventListener('click', () => orderItemsOptions.onRemove(item, currentItemIndex));
    }
  }

  // Nav enable/disable
  const prevBtn = document.getElementById('oi-prev');
  const nextBtn = document.getElementById('oi-next');
  if (prevBtn && nextBtn) {
    if (orderItemsData.length <= 1) {
      prevBtn.disabled = true;
      nextBtn.disabled = true;
    } else {
      prevBtn.disabled = (currentItemIndex === 0);
      nextBtn.disabled = (currentItemIndex === orderItemsData.length - 1);
    }
  }
}

// Expose globals
window.openOrderItemsPopup   = openOrderItemsPopup;
window.openCartItemsPopup    = openCartItemsPopup;
window.prevOrderItem         = prevOrderItem;
window.nextOrderItem         = nextOrderItem;
window.closeOrderItemsPopup  = closeOrderItemsPopup;
