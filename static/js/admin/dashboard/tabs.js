// Admin Dashboard JavaScript

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

// Tab Switching
function initTabs() {
  const tabs = document.querySelectorAll('.admin-tab');
  const panels = document.querySelectorAll('.tab-panel');

  tabs.forEach(tab => {
    tab.addEventListener('click', function() {
      const tabId = this.dataset.tab;
      switchTab(tabId);
    });
  });

  // Check URL hash for initial tab
  if (window.location.hash) {
    const hashTab = window.location.hash.replace('#', '');
    const validTabs = ['overview', 'users', 'listings', 'buckets', 'transactions', 'ledger', 'disputes', 'messages', 'system'];
    if (validTabs.includes(hashTab)) {
      switchTab(hashTab);
    }
  }
}

function switchTab(tabId) {
  const tabs = document.querySelectorAll('.admin-tab');
  const panels = document.querySelectorAll('.tab-panel');

  // Update tabs
  tabs.forEach(tab => {
    if (tab.dataset.tab === tabId) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
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

  // Load bucket data when switching to buckets tab
  if (tabId === 'buckets') {
    loadBucketStats();
    loadBuckets();
  }

}

