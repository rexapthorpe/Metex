// static/js/tabs/bids_tab.js
// NOTE: Modal logic lives in static/js/modals/edit_bid_modal.js.

document.addEventListener('DOMContentLoaded', function () {
  // Sidebar tab state persistence (unrelated to modal)
  document.querySelectorAll('.account-sidebar a').forEach(link => {
    link.addEventListener('click', function () {
      const target = this.getAttribute('href').slice(1);
      localStorage.setItem('activeAccountTab', target);
    });
  });
});

// Close a bid via AJAX and remove its card from the DOM
function closeBid(bidId) {
  // Open the confirmation modal instead of using browser confirm()
  openCloseBidConfirmModal(bidId);
}
window.closeBid = closeBid;
