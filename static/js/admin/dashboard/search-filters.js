// Search functionality
function initSearch() {
  const userSearch = document.getElementById('userSearch');
  const listingSearch = document.getElementById('listingSearch');

  if (userSearch) {
    userSearch.addEventListener('input', debounce(function() {
      filterUsers(this.value);
    }, 300));
  }

  if (listingSearch) {
    listingSearch.addEventListener('input', debounce(function() {
      filterListings(this.value);
    }, 300));
  }
}

function filterUsers(query) {
  const table = document.querySelector('#panel-users .data-table tbody');
  if (!table) return;

  const rows = table.querySelectorAll('tr');
  const lowerQuery = query.toLowerCase();

  rows.forEach(row => {
    const username = row.querySelector('.user-name')?.textContent.toLowerCase() || '';
    const email = row.cells[1]?.textContent.toLowerCase() || '';

    if (username.includes(lowerQuery) || email.includes(lowerQuery)) {
      row.style.display = '';
    } else {
      row.style.display = 'none';
    }
  });
}

function filterListings(query) {
  const table = document.querySelector('#panel-listings .data-table tbody');
  if (!table) return;

  const rows = table.querySelectorAll('tr');
  const lowerQuery = query.toLowerCase();

  rows.forEach(row => {
    const title = row.querySelector('.listing-title')?.textContent.toLowerCase() || '';
    const seller = row.cells[1]?.textContent.toLowerCase() || '';

    if (title.includes(lowerQuery) || seller.includes(lowerQuery)) {
      row.style.display = '';
    } else {
      row.style.display = 'none';
    }
  });
}

// Filter dropdowns
function initFilters() {
  const userStatusFilter = document.getElementById('userStatusFilter');
  const listingStatusFilter = document.getElementById('listingStatusFilter');
  const listingMetalFilter = document.getElementById('listingMetalFilter');

  if (userStatusFilter) {
    userStatusFilter.addEventListener('change', function() {
      filterUsersByStatus(this.value);
    });
  }

  if (listingStatusFilter) {
    listingStatusFilter.addEventListener('change', function() {
      filterListingsByStatus(this.value);
    });
  }

  if (listingMetalFilter) {
    listingMetalFilter.addEventListener('change', function() {
      filterListingsByMetal(this.value);
    });
  }
}

function filterUsersByStatus(status) {
  const table = document.querySelector('#panel-users .data-table tbody');
  if (!table) return;

  const rows = table.querySelectorAll('tr');

  rows.forEach(row => {
    const badge = row.querySelector('.status-badge');
    const rowStatus = badge?.textContent.toLowerCase().trim() || '';

    if (!status || rowStatus === status.toLowerCase()) {
      row.style.display = '';
    } else {
      row.style.display = 'none';
    }
  });
}

function filterListingsByStatus(status) {
  const table = document.querySelector('#panel-listings .data-table tbody');
  if (!table) return;

  const rows = table.querySelectorAll('tr');

  rows.forEach(row => {
    const badge = row.querySelector('.status-badge');
    const rowStatus = badge?.textContent.toLowerCase().trim() || '';

    if (!status || rowStatus === status.toLowerCase()) {
      row.style.display = '';
    } else {
      row.style.display = 'none';
    }
  });
}

function filterListingsByMetal(metal) {
  const table = document.querySelector('#panel-listings .data-table tbody');
  if (!table) return;

  const rows = table.querySelectorAll('tr');

  rows.forEach(row => {
    const badge = row.querySelector('.metal-badge');
    const rowMetal = badge?.textContent.toLowerCase().trim() || '';

    if (!metal || rowMetal === metal.toLowerCase()) {
      row.style.display = '';
    } else {
      row.style.display = 'none';
    }
  });
}

// ============================================
// USER ACTIONS
// ============================================

function viewUser(userId) {
  console.log('[Admin] viewUser called with userId:', userId);
  currentUserId = userId;
  const modal = document.getElementById('userDetailModal');
  const content = document.getElementById('userDetailContent');

  console.log('[Admin] Modal element:', modal);
  console.log('[Admin] Modal current display:', modal ? modal.style.display : 'not found');

  // Show modal with loading state
  modal.style.display = 'flex';
  console.log('[Admin] Modal display set to flex, actual:', modal.style.display);
  content.innerHTML = `
    <div class="modal-loading">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Loading user details...</span>
    </div>
  `;

  // Fetch user details
