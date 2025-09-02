// sold_tab.js

// placeholder for future sold-tab behaviors
document.addEventListener('DOMContentLoaded', () => {
  // e.g. wire up tracking modals, etc.
});

// open the existing message modal, but fetch buyers instead of sellers
function openMessageModalForBuyer(orderId) {
  currentOrderId = orderId;
  fetch(`/orders/api/${orderId}/message_buyers`)
    .then(res => res.json())
    .then(data => {
      // map buyers into the modal's expected structure (participant_id + username)
      messageSellers = data.map(item => ({
        seller_id: item.buyer_id,
        username: item.username
      }));
      currentIndex = 0;
      renderConversation();
      document.getElementById('messageModal').style.display = 'block';
    })
    .catch(console.error);
}
// expose globally for HTML onclick
window.openMessageModalForBuyer = openMessageModalForBuyer;