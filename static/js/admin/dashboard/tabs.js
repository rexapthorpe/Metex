// Admin Dashboard Tab Switching (left-sidebar nav)

let currentUserId = null;
let pendingAction = null;
let messageRecipientId = null;
let messageRecipientUsername = null;

document.addEventListener('DOMContentLoaded', function() {
  initTabs();
  initSearch();
  initFilters();
  initModalClose();
});

// ── Tab Switching ─────────────────────────────────────────────────────────────

function initTabs() {
  // Check URL hash for initial tab
  if (window.location.hash) {
    const hashTab = window.location.hash.replace('#', '');
    const validTabs = [
      'overview','users','listings','buckets','transactions','ledger',
      'reconciliation','tax','refunds','disputes','risk','feedback','messages','system'
    ];
    if (validTabs.includes(hashTab)) {
      switchTab(hashTab);
      return;
    }
  }
  // Default: ensure overview is active
  switchTab('overview');
}

function switchTab(tabId) {
  const navItems = document.querySelectorAll('.admin-nav-item');
  const panels = document.querySelectorAll('.tab-panel');

  // Update sidebar nav active state
  navItems.forEach(item => {
    if (item.dataset.tab === tabId) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });

  // Update panels
  panels.forEach(panel => {
    if (panel.id === `panel-${tabId}`) {
      panel.classList.add('active');
    } else {
      panel.classList.remove('active');
    }
  });

  // Update URL hash without scrolling
  history.replaceState(null, null, `#${tabId}`);

  // Update mobile header label
  const activeItem = document.querySelector(`.admin-nav-item[data-tab="${tabId}"]`);
  if (activeItem) {
    const label = activeItem.querySelector('.sidebar-label');
    const mobileLabel = document.getElementById('adminMobileTabName');
    if (label && mobileLabel) mobileLabel.textContent = label.textContent;
  }

  // Close mobile sidebar after selection
  closeAdminSidebar();

  // Load bucket data when switching to buckets tab
  if (tabId === 'buckets') {
    if (typeof loadBucketStats === 'function') loadBucketStats();
    if (typeof loadBuckets === 'function') loadBuckets();
  }

  // Load reconciliation data on first visit
  if (tabId === 'reconciliation') {
    if (typeof loadReconStats === 'function') loadReconStats();
    if (typeof loadReconRows === 'function') loadReconRows();
  }

  // Load Sales Tax tab data on first visit
  if (tabId === 'tax') {
    if (typeof loadTaxStats === 'function') loadTaxStats();
    if (typeof loadTaxRows === 'function') loadTaxRows();
    if (typeof loadTaxJurisdictions === 'function') loadTaxJurisdictions();
  }
}

// ── Mobile Sidebar ────────────────────────────────────────────────────────────

function openAdminSidebar() {
  const sidebar = document.getElementById('adminSidebar');
  const overlay = document.getElementById('adminSidebarOverlay');
  if (sidebar) sidebar.classList.add('mobile-open');
  if (overlay) overlay.classList.add('show');
}

function closeAdminSidebar() {
  const sidebar = document.getElementById('adminSidebar');
  const overlay = document.getElementById('adminSidebarOverlay');
  if (sidebar) sidebar.classList.remove('mobile-open');
  if (overlay) overlay.classList.remove('show');
}
