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
  if (!confirm('Are you sure you want to close this bid?')) return;
  fetch(`/bids/cancel/${bidId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then(res => {
      if (res.ok) {
        const btn = document.querySelector(`button[onclick="closeBid(${bidId})"]`);
        if (btn) {
          const card = btn.closest('.bid-card');
          if (card) card.remove();
        }
      } else {
        alert('Failed to close bid.');
      }
    })
    .catch(() => alert('Something went wrong.'));
}
window.closeBid = closeBid;
