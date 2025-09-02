// universal_outside_click_close.js
(function () {
  // Helper: hide an element safely
  function hide(el) {
    if (el) el.style.display = 'none';
  }

  // Known modal overlays with their inner content selector and a close action.
  // Add here if you introduce new modal types later.
  const MODALS = [
    // Generic Bootstrap-style you use: #messageModal, #editBidModal, #sellerModal, #removeSellerConfirmModal, etc.
    { overlaySel: '.modal', contentSel: '.modal-content',
      close: (overlay) => hide(overlay)
    },

    // Cart “View Item Price Breakdown”
    { overlaySel: '#priceBreakdownModal', contentSel: '.priceBreakdown-modal-content',
      close: () => (window.closePriceBreakdownModal ? window.closePriceBreakdownModal() : hide(document.querySelector('#priceBreakdownModal')))
    },

    // Order Items
    { overlaySel: '.order-items-modal-overlay', contentSel: '.order-items-modal-content',
      close: () => (window.closeOrderItemsPopup ? window.closeOrderItemsPopup() : null)
    },

    // Order Sellers
    { overlaySel: '.order-sellers-modal-overlay', contentSel: '.order-sellers-modal-content',
      close: () => (window.closeOrderSellersPopup ? window.closeOrderSellersPopup() : hide(document.querySelector('.order-sellers-modal-overlay')))
    },

    // Cart remove item confirm
    { overlaySel: '.cart-remove-overlay', contentSel: '.cart-remove-modal-content',
      close: (overlay) => hide(overlay)
    },

    // Listing cancel confirm
    { overlaySel: '.cancel-overlay', contentSel: '.cancel-modal-content',
      close: (overlay) => hide(overlay)
    },

    // Edit listing modal (top-level wrapper is the overlay)
    { overlaySel: '.edit-listing-modal', contentSel: '.modal-content',
      close: (overlay) => hide(overlay)
    },
  ];

  // Single delegated listener for the whole document
  document.addEventListener('click', function (e) {
    for (const { overlaySel, contentSel, close } of MODALS) {
      // Find the nearest overlay ancestor of the click
      const overlay = e.target.closest(overlaySel);
      if (!overlay) continue; // Click wasn't inside this overlay type

      // If the click was inside the overlay BUT outside its content box, close it
      const clickedInsideContent = e.target.closest(contentSel);
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
