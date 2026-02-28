// ============================================================
// Sidebar: sticky until footer, then scroll away
// ============================================================
(function () {
  var SIDEBAR_TOP = 64;  // matches CSS top: 64px
  var GAP = 0;           // flush against footer

  function updateAccountSidebarTop() {
    // Only applies on desktop (sidebar is a fixed drawer on mobile)
    if (window.innerWidth <= 768) return;

    var sidebar = document.getElementById('accountSidebar');
    var footer  = document.getElementById('siteFooter');
    if (!sidebar || !footer) return;

    var footerTop    = footer.getBoundingClientRect().top;
    var sidebarH     = sidebar.offsetHeight;
    var threshold    = SIDEBAR_TOP + sidebarH + GAP;

    if (footerTop < threshold) {
      sidebar.style.top = (footerTop - sidebarH - GAP) + 'px';
    } else {
      sidebar.style.top = SIDEBAR_TOP + 'px';
    }
  }

  window.addEventListener('scroll', updateAccountSidebarTop, { passive: true });
  window.addEventListener('resize', updateAccountSidebarTop, { passive: true });
})();

// ============================================================
// Mobile Sidebar: close helper
// ============================================================
function closeMobileAccountSidebar() {
  var sidebar = document.getElementById('accountSidebar');
  var overlay = document.getElementById('accountSidebarOverlay');
  if (sidebar) sidebar.classList.remove('mobile-open');
  if (overlay) overlay.classList.remove('show');
  document.body.style.overflow = '';
}

// ============================================================
// Show the selected tab
// ============================================================
function showTab(tabName) {
  // Hide all tab panels
  document.querySelectorAll('.tab-content').forEach(tab => {
    tab.style.display = 'none';
  });

  // Show the active tab
  const active = document.getElementById(`${tabName}-tab`);
  if (active) {
    active.style.display = 'block';
  }

  // Highlight active sidebar tab
  document.querySelectorAll('.account-sidebar .sidebar-item').forEach(item => {
    item.classList.remove('active');
    const clickAttr = item.getAttribute('onclick') || '';
    if (clickAttr.includes(`'${tabName}'`)) {
      item.classList.add('active');
    }
  });

  // Tell the layout whether Account Details is open
  const layout = document.querySelector('.account-layout');
  if (layout) {
    if (tabName === 'details') {
      layout.classList.add('details-nav-open');
      // Show the overview section by default when opening Account Details
      if (typeof showDetailsSection === 'function') {
        setTimeout(() => showDetailsSection('overview'), 50);
      }
    } else {
      layout.classList.remove('details-nav-open');
    }
  }

  // Fade in average rating if entering ratings tab
  if (tabName === 'ratings' && typeof fadeInAverageRating === 'function') {
    fadeInAverageRating();
  }

  // Initialize portfolio if entering portfolio tab
  if (tabName === 'portfolio' && typeof initPortfolioTab === 'function') {
    initPortfolioTab();
  }

  // Initialize reports tab on first open
  if (tabName === 'reports' && typeof initReportsTab === 'function') {
    initReportsTab();
  }

  // Update the tab name shown in the mobile menu button, then close sidebar
  var mobileTabName = document.getElementById('accountMobileTabName');
  if (mobileTabName) {
    var activeItem = document.querySelector('.account-sidebar .sidebar-item.active');
    if (activeItem) {
      var label = activeItem.querySelector('.sidebar-label');
      if (label) mobileTabName.textContent = label.textContent.trim();
    }
  }
  closeMobileAccountSidebar();
}

// Automatically open tab based on URL hash (e.g. #bids), or default to cart
// ============================================================
// Position mobile sidebar below the actual subheader bottom
// ============================================================
function positionMobileAccountSidebar() {
  var header    = document.querySelector('.header-bar');
  var subheader = document.querySelector('.subheader-bar');
  var sidebar   = document.getElementById('accountSidebar');
  var overlay   = document.getElementById('accountSidebarOverlay');
  if (!header || !sidebar) return;

  // Anchor the sidebar to the bottom of the main header.
  // The subheader (z-index 999) sits above the sidebar (z-index 998)
  // so it remains fully visible regardless of where the sidebar starts.
  var headerBottom = Math.round(header.getBoundingClientRect().bottom);

  // Also keep the subheader's mobile top in sync with the header bottom
  if (subheader) {
    subheader.style.top = headerBottom + 'px';
  }

  // Sidebar starts at main header bottom; subheader floats above it naturally
  sidebar.style.top    = headerBottom + 'px';
  sidebar.style.height = 'calc(100vh - ' + headerBottom + 'px)';

  // Overlay greys out everything below the header (including account mobile header)
  if (overlay) overlay.style.top = headerBottom + 'px';

  // Keep account-layout padding and account-mobile-header sticky-top in sync
  // with the actual header height (CSS provides a fallback; JS corrects it exactly)
  var layout = document.querySelector('.account-layout');
  if (layout) layout.style.paddingTop = headerBottom + 'px';

  var mobileAccountHeader = document.querySelector('.account-mobile-header');
  if (mobileAccountHeader) mobileAccountHeader.style.top = headerBottom + 'px';
}

document.addEventListener('DOMContentLoaded', () => {
  const hash = window.location.hash.slice(1); // "orders" from "#orders"
  handleHashNavigation(hash);

  // ── Position sidebar below the subheader ──
  positionMobileAccountSidebar();
  window.addEventListener('resize', positionMobileAccountSidebar);

  // ── Mobile Account Sidebar Toggle ──
  var menuBtn = document.getElementById('accountMobileMenuBtn');
  var sidebar = document.getElementById('accountSidebar');
  var overlay = document.getElementById('accountSidebarOverlay');

  if (menuBtn && sidebar) {
    menuBtn.addEventListener('click', function() {
      positionMobileAccountSidebar(); // recalc in case header reflowed
      sidebar.classList.toggle('mobile-open');
      if (overlay) overlay.classList.toggle('show');
      document.body.style.overflow = sidebar.classList.contains('mobile-open') ? 'hidden' : '';
    });
  }

  if (overlay) {
    overlay.addEventListener('click', closeMobileAccountSidebar);
  }
});

// Handle hash changes (e.g., when clicking notification "View Order" button)
window.addEventListener('hashchange', () => {
  const hash = window.location.hash.slice(1);
  handleHashNavigation(hash);
});

// Handle hash-based navigation with support for compound hashes (e.g., #details-personal)
function handleHashNavigation(hash) {
  const validTabs = ['cart','bids','listings','sold','orders','portfolio','ratings','messages','reports','details'];

  // Check for compound hash (e.g., "details-personal")
  let tab = hash;
  let detailsSection = null;

  if (hash.includes('-')) {
    const parts = hash.split('-');
    tab = parts[0];
    detailsSection = parts[1];
  }

  // Validate and show main tab
  if (validTabs.includes(tab)) {
    showTab(tab);

    // If it's the details tab with a sub-section, navigate to that section
    if (tab === 'details' && detailsSection && typeof showDetailsSection === 'function') {
      setTimeout(() => showDetailsSection(detailsSection), 100);
    }
  } else if (hash === '') {
    // No hash, show default cart tab
    showTab('cart');
  }
}

// Remove a single listing from cart (AJAX)
function removeCartItem(listingId, buttonElement) {
  fetch(`/cart/remove_item/${listingId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
  .then(response => {
    if (response.ok) {
      const tile = buttonElement.closest('.cart-item-tile');
      if (tile) tile.remove();

      const emptyMsg = document.querySelector('.cart-tab .empty-message');
      if (!document.querySelector('.cart-tab .cart-item-tile') && emptyMsg) {
        emptyMsg.style.display = 'block';
      }
    } else {
      alert("Failed to remove item from cart.");
    }
  })
  .catch(err => {
    console.error("Error:", err);
    alert("Something went wrong.");
  });
}
window.removeCartItem = removeCartItem;
