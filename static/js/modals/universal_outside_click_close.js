// universal_outside_click_close.js
(function () {
  // Helper: hide an element safely
  function hide(el) {
    if (el) el.style.display = 'none';
  }

  // Known modal overlays with their inner content selector and a close action.
  // Add here if you introduce new modal types later.
  const MODALS = [
    // Generic Bootstrap-style you use: #messageModal, #editBidModal, etc.
    {
      overlaySel: '.modal',
      contentSel: '.modal-content',
      close: (overlay) => hide(overlay)
    },

    // Cart “View Item Price Breakdown”
    {
      // Accept both the id and the new overlay class (back-compat)
      overlaySel: '#priceBreakdownModal, .cart-items-modal-overlay',
      // Use the NEW content class; keep the old one for back-compat
      contentSel: '.cart-items-modal-content, .priceBreakdown-modal-content',
      // Call the actual close function; fallback hides this overlay only
      close: (overlay) => (window.closePriceBreakdown ? window.closePriceBreakdown() : hide(overlay))
    },

    // Order Items
    {
      overlaySel: '.order-items-modal-overlay',
      contentSel: '.order-items-modal-content',
      close: (overlay) => (window.closeOrderItemsPopup ? window.closeOrderItemsPopup() : hide(overlay))
    },

    // Order Sellers
    {
      overlaySel: '.order-sellers-modal-overlay',
      contentSel: '.order-sellers-modal-content',
      close: (overlay) => (window.closeOrderSellersPopup ? window.closeOrderSellersPopup() : hide(overlay))
    },

    // Cart remove item confirm
    {
      overlaySel: '.cart-remove-overlay',
      contentSel: '.cart-remove-modal-content',
      close: (overlay) => hide(overlay)
    },

    // Listing cancel confirm
    {
      overlaySel: '.cancel-overlay',
      contentSel: '.cancel-modal-content',
      close: (overlay) => hide(overlay)
    },

    // Edit listing modal (top-level wrapper is the overlay)
    {
      overlaySel: '.edit-listing-modal',
      contentSel: '.modal-content',
      close: (overlay) => hide(overlay)
    },
  ];

  // Single delegated listener for the whole document
  document.addEventListener('click', function (e) {
    for (const { overlaySel, contentSel, close } of MODALS) {
      // Find the nearest overlay ancestor of the click
      const overlay = e.target.closest(overlaySel);
      if (!overlay) continue; // Click wasn't inside this overlay type

      // Find the nearest content node and ensure it belongs to THIS overlay
      const insideNode = e.target.closest(contentSel);
      const clickedInsideContent = insideNode && overlay.contains(insideNode);

      // If the click was inside the overlay BUT outside its content box, close it
      if (!clickedInsideContent) {
        // Prevent accidental follow-on clicks
        e.preventDefault();
        e.stopPropagation();
        try { close(overlay); } catch (err) { console.warn('Modal close error', err); }
        return; // Only act on one modal at a time
      }
    }
  }, true); // capture phase to intercept early
})();
