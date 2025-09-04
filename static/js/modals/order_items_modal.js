// order_items_modal.js

let orderItemsData = [];
let currentItemIndex = 0;

// controls whether "Remove Item" shows, and lets you hook a remover
let orderItemsOptions = {
  context: 'orders',          // 'orders' | 'cart'
  onRemove: null              // function(item, index) { ... }
};

function openOrderItemsPopup(orderId, options = {}) {
  orderItemsOptions = { context: 'orders', onRemove: null, ...options };

  fetch(`/orders/api/${orderId}/order_items`)
    .then(res => (res.ok ? res.json() : Promise.reject()))
    .then(data => {
      orderItemsData = Array.isArray(data) ? data : [];
      currentItemIndex = 0;
      renderOrderItem();
      showOrderItemsModal();
    })
    .catch(() => alert('Could not load order items'));
}

// Use this for the Cart context (you provide the items array)
function openCartItemsPopup(items, options = {}) {
  orderItemsOptions = { context: 'cart', onRemove: null, ...options };
  orderItemsData = Array.isArray(items) ? items : [];
  currentItemIndex = 0;
  renderOrderItem();
  showOrderItemsModal();
}

function showOrderItemsModal() {
  const modal = document.getElementById('orderItemsModal');
  modal.style.display = 'flex';
  modal.addEventListener('click', outsideClickItems);
  document.addEventListener('keydown', keyNavHandler);
}

function closeOrderItemsPopup() {
  const modal = document.getElementById('orderItemsModal');
  modal.style.display = 'none';
  modal.removeEventListener('click', outsideClickItems);
  document.removeEventListener('keydown', keyNavHandler);
}

function keyNavHandler(e) {
  if (e.key === 'ArrowLeft') prevOrderItem();
  else if (e.key === 'ArrowRight') nextOrderItem();
  else if (e.key === 'Escape') closeOrderItemsPopup(); // keeps accessibility without UI close/x
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

function outsideClickItems(e) {
  if (e.target.id === 'orderItemsModal') {
    closeOrderItemsPopup();
  }
}

function renderOrderItem() {
  if (!orderItemsData.length) return;

  const item = orderItemsData[currentItemIndex];

  // Helpers
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => (
    { '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]
  ));
  const fmtMoney = n =>
    (n == null || Number.isNaN(Number(n)))
      ? '—'
      : Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const qty = item.total_quantity ?? item.quantity ?? 0;
  const priceEach =
    item.price_each ?? item.unit_price ?? item.price_per_coin ?? 0;
  const total = Number(qty) * Number(priceEach);

  const title =
    item.title
    ?? item.category_name
    ?? [
         (item.weight ? `${item.weight}` : ''),
         (item.metal ? `${item.metal}` : '')
       ].join(' ').trim() +
       (item.mint || item.year ? ` (${[item.mint, item.year].filter(Boolean).join(', ')})` : '');

  // Header title
  const titleEl = document.getElementById('orderItemsModalTitle');
  if (titleEl) titleEl.textContent = title || 'Item';

  // Optional fields
  const purity = item.purity ?? item.fineness;
  const grading = item.grading_service ?? item.grader;
  const seller  = item.seller_username ?? item.seller;

  // Right column: show Remove only in cart context
  const removeBtnHTML = (orderItemsOptions.context === 'cart')
    ? `<button class="order-items-remove-btn" type="button">Remove Item</button>`
    : '';

  document.getElementById('orderItemsModalContent').innerHTML = `
    <div class="order-items-two-col">
      <div class="order-items-col-left">
        <dl class="kv-list">
          ${item.mint   ? `<div><dt>Mint</dt><dd>${esc(item.mint)}</dd></div>` : ''}
          ${item.metal  ? `<div><dt>Metal</dt><dd>${esc(item.metal)}</dd></div>` : ''}
          ${item.year   ? `<div><dt>Year</dt><dd>${esc(item.year)}</dd></div>` : ''}
          ${purity      ? `<div><dt>Purity</dt><dd>${esc(purity)}</dd></div>` : ''}
          ${grading     ? `<div><dt>Grading</dt><dd>${esc(grading)}</dd></div>` : ''}
          ${seller      ? `<div><dt>Seller</dt><dd>${esc(seller)}</dd></div>` : ''}
        </dl>
      </div>

      <div class="order-items-col-right">
        <div class="kv"><span>Quantity</span><span class="value">${esc(qty)}</span></div>
        <div class="kv"><span>Price / item</span><span class="value">$${fmtMoney(priceEach)}</span></div>
        <div class="kv total"><span>Total</span><span class="value">$${fmtMoney(total)}</span></div>
        ${removeBtnHTML}
      </div>
    </div>
  `;

  // Hook remove action if present
  if (orderItemsOptions.context === 'cart') {
    const btn = document.querySelector('.order-items-remove-btn');
    if (btn) {
      btn.addEventListener('click', () => {
        if (typeof orderItemsOptions.onRemove === 'function') {
          orderItemsOptions.onRemove(item, currentItemIndex);
        }
      });
    }
  }

  // Nav enable/disable
  const prevBtn = document.getElementById('oi-prev');
  const nextBtn = document.getElementById('oi-next');
  if (orderItemsData.length <= 1) {
    prevBtn.disabled = true;
    nextBtn.disabled = true;
  } else {
    prevBtn.disabled = (currentItemIndex === 0);
    nextBtn.disabled = (currentItemIndex === orderItemsData.length - 1);
  }
}

// Expose globals
window.openOrderItemsPopup   = openOrderItemsPopup;
window.openCartItemsPopup    = openCartItemsPopup;
window.prevOrderItem         = prevOrderItem;
window.nextOrderItem         = nextOrderItem;
window.closeOrderItemsPopup  = closeOrderItemsPopup;
