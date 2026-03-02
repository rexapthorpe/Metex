function loadBucketStats() {
  fetch('/admin/api/buckets/stats')
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        document.getElementById('bucketStatTotal').textContent =
          data.stats.total_buckets?.toLocaleString() || '0';
        document.getElementById('bucketStatCustomFees').textContent =
          data.stats.buckets_with_custom_fees?.toLocaleString() || '0';
        document.getElementById('bucketStatListings').textContent =
          data.stats.total_active_listings?.toLocaleString() || '0';
        document.getElementById('bucketStatBids').textContent =
          data.stats.total_active_bids?.toLocaleString() || '0';
      }
    })
    .catch(err => {
      console.error('Error loading bucket stats:', err);
    });
}

function loadBuckets() {
  const tbody = document.getElementById('bucketsTableBody');
  tbody.innerHTML = `
    <tr>
      <td colspan="7" style="text-align: center; color: #6b7280; padding: 40px;">
        <i class="fa-solid fa-spinner fa-spin"></i> Loading buckets...
      </td>
    </tr>
  `;

  const params = new URLSearchParams({
    page: bucketPage,
    per_page: bucketPerPage,
    search: bucketFilters.search,
    metal: bucketFilters.metal
  });

  fetch(`/admin/api/buckets?${params}`)
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        renderBucketsTable(data.buckets);
        updateBucketPagination(data.pagination);
        populateBucketMetalFilter(data.filters.metals);

        // Update count display
        const countDisplay = document.getElementById('bucketCountDisplay');
        countDisplay.textContent = `${data.pagination.total.toLocaleString()} buckets`;
      } else {
        tbody.innerHTML = `
          <tr>
            <td colspan="7" style="text-align: center; color: #ef4444; padding: 40px;">
              Error loading buckets: ${data.error}
            </td>
          </tr>
        `;
      }
    })
    .catch(err => {
      console.error('Error loading buckets:', err);
      tbody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align: center; color: #ef4444; padding: 40px;">
            Error loading buckets. Please try again.
          </td>
        </tr>
      `;
    });
}

function renderBucketsTable(buckets) {
  const tbody = document.getElementById('bucketsTableBody');

  if (!buckets || buckets.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; color: #6b7280; padding: 40px;">
          No buckets found
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = buckets.map(bucket => `
    <tr data-bucket-id="${bucket.bucket_id}">
      <td>
        <a href="/bucket/${bucket.bucket_id}" target="_blank" class="bucket-id-link">#${bucket.bucket_id}</a>
      </td>
      <td class="bucket-name">${escapeHtml(bucket.name)}</td>
      <td>
        <span class="metal-badge metal-${bucket.metal?.toLowerCase() || 'unknown'}">${bucket.metal || 'Unknown'}</span>
      </td>
      <td>${bucket.active_listings}</td>
      <td>${bucket.active_bids}</td>
      <td>
        <span class="fee-badge ${bucket.fee_type ? 'fee-custom' : 'fee-default'}">${bucket.fee_display}</span>
      </td>
      <td class="actions-cell">
        <button class="action-icon" title="View Details" onclick="viewBucketDetails(${bucket.bucket_id})">
          <i class="fa-solid fa-eye"></i>
        </button>
        <button class="action-icon action-warning" title="Edit Fee" onclick="openBucketFeeModal(${bucket.bucket_id}, '${bucket.fee_type || ''}', ${bucket.fee_value ?? ''})">
          <i class="fa-solid fa-percent"></i>
        </button>
        <a href="/bucket/${bucket.bucket_id}" target="_blank" class="action-icon" title="View Public Page">
          <i class="fa-solid fa-external-link-alt"></i>
        </a>
      </td>
    </tr>
  `).join('');
}

function updateBucketPagination(pagination) {
  bucketTotalPages = pagination.total_pages;

  const prevBtn = document.getElementById('bucketPrevBtn');
  const nextBtn = document.getElementById('bucketNextBtn');
  const pageInfo = document.getElementById('bucketPageInfo');

  prevBtn.disabled = !pagination.has_prev;
  nextBtn.disabled = !pagination.has_next;
  pageInfo.textContent = `Page ${pagination.page} of ${pagination.total_pages}`;
}

function populateBucketMetalFilter(metals) {
  const select = document.getElementById('bucketMetalFilter');
  const currentValue = select.value;

  // Keep first option (All Metals)
  select.innerHTML = '<option value="">All Metals</option>';

  metals.forEach(metal => {
    const option = document.createElement('option');
    option.value = metal;
    option.textContent = metal;
    if (metal === currentValue) {
      option.selected = true;
    }
    select.appendChild(option);
  });
}

function bucketPrevPage() {
  if (bucketPage > 1) {
    bucketPage--;
    loadBuckets();
  }
}

function bucketNextPage() {
  if (bucketPage < bucketTotalPages) {
    bucketPage++;
    loadBuckets();
  }
}

// Initialize bucket search and filter handlers
document.addEventListener('DOMContentLoaded', function() {
  const bucketSearch = document.getElementById('bucketSearch');
  const bucketMetalFilter = document.getElementById('bucketMetalFilter');

  if (bucketSearch) {
    bucketSearch.addEventListener('input', debounce(function() {
      bucketFilters.search = this.value;
      bucketPage = 1;
      loadBuckets();
    }, 300));
  }

  if (bucketMetalFilter) {
    bucketMetalFilter.addEventListener('change', function() {
      bucketFilters.metal = this.value;
      bucketPage = 1;
      loadBuckets();
    });
  }
});

// View bucket details
let bucketPriceChartInstance = null;

function viewBucketDetails(bucketId) {
  const modal = document.getElementById('bucketDetailModal');
  const content = document.getElementById('bucketDetailContent');
  const title = document.getElementById('bucketDetailTitle');

  modal.style.display = 'flex';
  title.textContent = `#${bucketId}`;
  content.innerHTML = `
    <div class="modal-loading">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Loading bucket details...</span>
    </div>
  `;

  fetch(`/admin/api/buckets/${bucketId}`)
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        title.textContent = data.bucket.name;
        content.innerHTML = renderBucketDetailContent(data);

        // Initialize price history chart after DOM update
        if (data.price_history && data.price_history.length > 0) {
          setTimeout(() => {
            initBucketPriceChart(data.price_history);
          }, 50);
        }
      } else {
        content.innerHTML = `
          <div style="text-align: center; color: #ef4444; padding: 40px;">
            Error: ${data.error}
          </div>
        `;
      }
    })
    .catch(err => {
      console.error('Error loading bucket details:', err);
      content.innerHTML = `
        <div style="text-align: center; color: #ef4444; padding: 40px;">
          Error loading bucket details. Please try again.
        </div>
      `;
    });
}

function initBucketPriceChart(priceHistory) {
  const canvas = document.getElementById('bucketPriceChart');
  if (!canvas) {
    console.warn('Price chart canvas not found');
    return;
  }

  // Destroy existing chart if any
  if (bucketPriceChartInstance) {
    bucketPriceChartInstance.destroy();
    bucketPriceChartInstance = null;
  }

  const ctx = canvas.getContext('2d');

  // Prepare data
  const labels = priceHistory.map(p => p.date);
  const avgPrices = priceHistory.map(p => p.avg_price);
  const minPrices = priceHistory.map(p => p.min_price);
  const maxPrices = priceHistory.map(p => p.max_price);

  bucketPriceChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Avg Price',
          data: avgPrices,
          borderColor: '#8b5cf6',
          backgroundColor: 'rgba(139, 92, 246, 0.1)',
          borderWidth: 2,
          fill: true,
          tension: 0,
          pointRadius: 3,
          pointHoverRadius: 5
        },
        {
          label: 'Min',
          data: minPrices,
          borderColor: '#10b981',
          borderWidth: 1,
          borderDash: [5, 5],
          fill: false,
          tension: 0,
          pointRadius: 0
        },
        {
          label: 'Max',
          data: maxPrices,
          borderColor: '#ef4444',
          borderWidth: 1,
          borderDash: [5, 5],
          fill: false,
          tension: 0,
          pointRadius: 0
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        intersect: false,
        mode: 'index'
      },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            usePointStyle: true,
            padding: 15,
            font: { size: 11 }
          }
        },
        tooltip: {
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          padding: 12,
          titleFont: { size: 12 },
          bodyFont: { size: 11 },
          callbacks: {
            label: function(context) {
              return `${context.dataset.label}: ${formatPrice(context.parsed.y)}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            font: { size: 10 },
            maxRotation: 45,
            minRotation: 45
          }
        },
        y: {
          grid: { color: 'rgba(0, 0, 0, 0.05)' },
          ticks: {
            font: { size: 10 },
            callback: function(value) {
              return '$' + value.toLocaleString();
            }
          }
        }
      }
    }
  });
}

function renderBucketDetailContent(data) {
  const bucket = data.bucket;
  const stats = data.stats;
  const priceHistory = data.price_history;
  const feeHistory = data.fee_history;

  // Fee display
  let feeDisplay = 'Default (2.5%)';
  if (bucket.fee_config.fee_type && bucket.fee_config.fee_value !== null) {
    if (bucket.fee_config.fee_type === 'percent') {
      feeDisplay = `${bucket.fee_config.fee_value}%`;
    } else {
      feeDisplay = formatPrice(bucket.fee_config.fee_value);
    }
  }

  // Price history chart
  let priceChartHtml = '';
  if (priceHistory && priceHistory.length > 0) {
    priceChartHtml = `
      <div class="bucket-price-chart">
        <canvas id="bucketPriceChart" width="400" height="200"></canvas>
      </div>
    `;
  } else {
    priceChartHtml = `
      <div style="text-align: center; color: #6b7280; padding: 20px;">
        No price history available
      </div>
    `;
  }

  // Fee history
  let feeHistoryHtml = '';
  if (feeHistory && feeHistory.length > 0) {
    feeHistoryHtml = feeHistory.map(event => {
      const oldFee = event.old_fee_type ?
        (event.old_fee_type === 'percent' ? `${event.old_fee_value}%` : `$${event.old_fee_value}`) :
        'Default';
      const newFee = event.new_fee_type === 'percent' ?
        `${event.new_fee_value}%` :
        `$${event.new_fee_value}`;
      return `
        <div class="fee-history-item">
          <span class="fee-change">${oldFee} → ${newFee}</span>
          <span class="fee-meta">by @${escapeHtml(event.admin_username)} • ${event.created_at}</span>
        </div>
      `;
    }).join('');
  } else {
    feeHistoryHtml = '<div style="color: #6b7280; font-size: 13px;">No fee changes recorded</div>';
  }

  return `
    <div class="bucket-detail-grid">
      <!-- Bucket Info -->
      <div class="bucket-detail-section">
        <h4><i class="fa-solid fa-info-circle"></i> Bucket Information</h4>
        <div class="bucket-info-grid">
          <div class="info-item">
            <span class="info-label">Bucket ID</span>
            <span class="info-value">#${bucket.bucket_id}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Metal</span>
            <span class="info-value"><span class="metal-badge metal-${bucket.metal?.toLowerCase()}">${bucket.metal || 'N/A'}</span></span>
          </div>
          <div class="info-item">
            <span class="info-label">Product Line</span>
            <span class="info-value">${bucket.product_line || bucket.product_type || 'N/A'}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Weight</span>
            <span class="info-value">${bucket.weight || 'N/A'}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Purity</span>
            <span class="info-value">${bucket.purity || 'N/A'}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Mint</span>
            <span class="info-value">${bucket.mint || 'N/A'}</span>
          </div>
        </div>
      </div>

      <!-- Fee Configuration -->
      <div class="bucket-detail-section">
        <h4><i class="fa-solid fa-percent"></i> Platform Fee</h4>
        <div class="fee-config-display">
          <div class="fee-current">
            <span class="fee-value">${feeDisplay}</span>
            ${bucket.fee_config.updated_at ? `<span class="fee-updated">Updated: ${bucket.fee_config.updated_at}</span>` : ''}
          </div>
          <button class="btn-primary btn-sm" onclick="openBucketFeeModal(${bucket.bucket_id}, '${bucket.fee_config.fee_type || ''}', ${bucket.fee_config.fee_value ?? ''})">
            <i class="fa-solid fa-edit"></i> Edit Fee
          </button>
        </div>
        <div class="fee-history">
          <h5>Recent Fee Changes</h5>
          ${feeHistoryHtml}
        </div>
      </div>

      <!-- Stats -->
      <div class="bucket-detail-section bucket-detail-section-wide">
        <h4><i class="fa-solid fa-chart-bar"></i> Marketplace Analytics</h4>
        <div class="bucket-stats-grid">
          <div class="bucket-stat-card">
            <span class="stat-label">Total Listings</span>
            <span class="stat-value">${stats.listings.total}</span>
          </div>
          <div class="bucket-stat-card">
            <span class="stat-label">Active Listings</span>
            <span class="stat-value">${stats.listings.active}</span>
          </div>
          <div class="bucket-stat-card">
            <span class="stat-label">Total Quantity</span>
            <span class="stat-value">${stats.listings.total_quantity || 0}</span>
          </div>
          <div class="bucket-stat-card">
            <span class="stat-label">Active Bids</span>
            <span class="stat-value">${stats.bids.active}</span>
          </div>
          <div class="bucket-stat-card">
            <span class="stat-label">Total Orders</span>
            <span class="stat-value">${stats.orders.total_orders}</span>
          </div>
          <div class="bucket-stat-card">
            <span class="stat-label">Total Volume</span>
            <span class="stat-value">$${stats.orders.total_volume.toLocaleString()}</span>
          </div>
          <div class="bucket-stat-card">
            <span class="stat-label">Avg Sale Price</span>
            <span class="stat-value">${formatPrice(stats.orders.avg_sale_price)}</span>
          </div>
          <div class="bucket-stat-card">
            <span class="stat-label">Fees Collected</span>
            <span class="stat-value">${formatPrice(stats.orders.total_fees_collected)}</span>
          </div>
        </div>
      </div>

      <!-- Price History Chart -->
      <div class="bucket-detail-section bucket-detail-section-wide">
        <h4><i class="fa-solid fa-chart-line"></i> Price History (30 days)</h4>
        ${priceChartHtml}
      </div>

      <!-- Navigation Links -->
      <div class="bucket-detail-section bucket-detail-section-wide">
        <div class="bucket-nav-links">
          <a href="/bucket/${bucket.bucket_id}" target="_blank" class="btn-outline">
            <i class="fa-solid fa-external-link-alt"></i> View Public Page
          </a>
          <a href="#ledger" onclick="filterLedgerByBucket(${bucket.bucket_id}); closeBucketDetailModal(); return false;" class="btn-outline">
            <i class="fa-solid fa-book"></i> View Ledger Orders
          </a>
        </div>
      </div>
    </div>
  `;
}

function closeBucketDetailModal() {
  document.getElementById('bucketDetailModal').style.display = 'none';
}

// Bucket Fee Modal
function openBucketFeeModal(bucketId, currentFeeType, currentFeeValue) {
  const modal = document.getElementById('bucketFeeModal');
  const formContent = modal.querySelector('.bucket-fee-form-content');
  const successContent = document.getElementById('bucketFeeSuccessContent');

  // Reset to form view
  formContent.style.display = 'block';
  successContent.style.display = 'none';

  // Set current values
  document.getElementById('bucketFeeEditBucketId').value = bucketId;

  // Display current fee
  const currentDisplay = document.getElementById('bucketFeeCurrentValue');
  if (currentFeeType && currentFeeValue !== null && !isNaN(currentFeeValue)) {
    currentDisplay.textContent = currentFeeType === 'percent' ? `${currentFeeValue}%` : formatPrice(currentFeeValue);
    document.getElementById('bucketFeeType').value = currentFeeType;
    document.getElementById('bucketFeeValue').value = currentFeeValue;
  } else {
    currentDisplay.textContent = 'Default (2.5%)';
    document.getElementById('bucketFeeType').value = 'percent';
    document.getElementById('bucketFeeValue').value = '';
  }

  updateBucketFeePrefix();
  modal.style.display = 'flex';

  // Add change handler for fee type
  document.getElementById('bucketFeeType').onchange = updateBucketFeePrefix;
}

function updateBucketFeePrefix() {
  const feeType = document.getElementById('bucketFeeType').value;
  const prefix = document.getElementById('bucketFeePrefix');
  const input = document.getElementById('bucketFeeValue');

  if (feeType === 'percent') {
    prefix.textContent = '%';
    input.placeholder = '2.5';
    input.max = '100';
  } else {
    prefix.textContent = '$';
    input.placeholder = '5.00';
    input.max = '';
  }
}

function saveBucketFee() {
  const bucketId = document.getElementById('bucketFeeEditBucketId').value;
  const feeType = document.getElementById('bucketFeeType').value;
  const feeValue = parseFloat(document.getElementById('bucketFeeValue').value);
  const errorEl = document.getElementById('bucketFeeValueError');
  const saveBtn = document.getElementById('bucketFeeSaveBtn');

  // Validate
  if (isNaN(feeValue) || feeValue < 0) {
    errorEl.textContent = 'Please enter a valid fee value (>= 0)';
    errorEl.style.display = 'block';
    return;
  }

  if (feeType === 'percent' && feeValue > 100) {
    errorEl.textContent = 'Percentage cannot exceed 100%';
    errorEl.style.display = 'block';
    return;
  }

  errorEl.style.display = 'none';
  saveBtn.disabled = true;
  saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';

  fetch(`/admin/api/buckets/${bucketId}/fee`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      fee_type: feeType,
      fee_value: feeValue
    })
  })
    .then(response => response.json())
    .then(data => {
      saveBtn.disabled = false;
      saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> Save Fee';

      if (data.success) {
        // Show success animation
        const formContent = document.querySelector('.bucket-fee-form-content');
        const successContent = document.getElementById('bucketFeeSuccessContent');
        const successMessage = document.getElementById('bucketFeeSuccessMessage');

        successMessage.textContent = `Bucket fee updated to ${data.fee_config.fee_display}`;
        formContent.style.display = 'none';
        successContent.style.display = 'flex';
      } else {
        errorEl.textContent = data.error || 'Failed to update fee';
        errorEl.style.display = 'block';
      }
    })
    .catch(err => {
      console.error('Error saving bucket fee:', err);
      saveBtn.disabled = false;
      saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> Save Fee';
      errorEl.textContent = 'Network error. Please try again.';
      errorEl.style.display = 'block';
    });
}

function closeBucketFeeModal() {
  document.getElementById('bucketFeeModal').style.display = 'none';
}

function closeBucketFeeModalAndRefresh() {
  closeBucketFeeModal();
  loadBuckets();
  loadBucketStats();
}

function filterLedgerByBucket(bucketId) {
  // This would filter the ledger by bucket - for now just switch to ledger tab
  switchTab('ledger');
  // Could add bucket filter to ledger in future
}

// Escape HTML helper
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Export bucket functions
window.loadBuckets = loadBuckets;
window.loadBucketStats = loadBucketStats;
window.bucketPrevPage = bucketPrevPage;
window.bucketNextPage = bucketNextPage;
window.viewBucketDetails = viewBucketDetails;
window.closeBucketDetailModal = closeBucketDetailModal;
window.openBucketFeeModal = openBucketFeeModal;
window.saveBucketFee = saveBucketFee;
window.closeBucketFeeModal = closeBucketFeeModal;
window.closeBucketFeeModalAndRefresh = closeBucketFeeModalAndRefresh;
window.filterLedgerByBucket = filterLedgerByBucket;


// ============================================
// METRICS PERFORMANCE MODAL
// ============================================

let metricsChart = null;
let currentMetricType = null;
let currentMetricsDays = 30;

const METRIC_CONFIG = {
  users: {
    title: 'Total Users',
    subtitle: 'User growth over time',
    icon: 'fa-users',
    iconClass: 'metrics-icon-users',
    color: '#3b82f6',
    bgColor: 'rgba(59, 130, 246, 0.1)',
    formatValue: (val) => val.toLocaleString(),
    chartLabel: 'Total Users'
  },
  listings: {
    title: 'Active Listings',
    subtitle: 'Listing inventory over time',
    icon: 'fa-tags',
    iconClass: 'metrics-icon-listings',
    color: '#10b981',
    bgColor: 'rgba(16, 185, 129, 0.1)',
    formatValue: (val) => val.toLocaleString(),
    chartLabel: 'Active Listings'
  },
  volume: {
    title: 'Transaction Volume',
    subtitle: 'Cumulative transaction value',
    icon: 'fa-chart-line',
    iconClass: 'metrics-icon-volume',
    color: '#8b5cf6',
    bgColor: 'rgba(139, 92, 246, 0.1)',
    formatValue: (val) => formatCurrency(val),
    chartLabel: 'Total Volume'
  },
  revenue: {
    title: 'Platform Revenue',
    subtitle: 'Platform fee earnings',
    icon: 'fa-dollar-sign',
    iconClass: 'metrics-icon-revenue',
    color: '#f59e0b',
    bgColor: 'rgba(245, 158, 11, 0.1)',
    formatValue: (val) => formatCurrency(val),
    chartLabel: 'Total Revenue'
  }
};

