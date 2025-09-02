let orderItemsData = [];
let currentItemIndex = 0;

function openOrderItemsPopup(orderId) {
  fetch(`/orders/api/${orderId}/order_items`)
    .then(res => res.ok ? res.json() : Promise.reject())
    .then(data => {
      orderItemsData = data;
      currentItemIndex = 0;
      renderOrderItem();
      const modal = document.getElementById('orderItemsModal');
      modal.style.display = 'flex';
      modal.addEventListener('click', outsideClickItems);
    })
    .catch(() => alert('Could not load order items'));
}

function renderOrderItem() {
  const item = orderItemsData[currentItemIndex];
  document.getElementById('orderItemsModalContent').innerHTML = `
    <div class="item-row">
      <div class="item-detail">
        ${item.weight} ${item.metal} (${item.mint}, ${item.year})
      </div>
      <div class="item-qty">x${item.total_quantity}</div>
      <div class="item-price">$${item.price_each.toFixed(2)}</div>
    </div>
  `;
  
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

function closeOrderItemsPopup() {
  const modal = document.getElementById('orderItemsModal');
  modal.style.display = 'none';
  modal.removeEventListener('click', outsideClickItems);
}

function outsideClickItems(e) {
  if (e.target.id === 'orderItemsModal') {
    closeOrderItemsPopup();
  }
}

// expose globals
window.openOrderItemsPopup = openOrderItemsPopup;
window.prevOrderItem      = prevOrderItem;
window.nextOrderItem      = nextOrderItem;
window.closeOrderItemsPopup = closeOrderItemsPopup;
