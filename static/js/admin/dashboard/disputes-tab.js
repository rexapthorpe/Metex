function loadDisputes() {
  const listEl = document.getElementById('disputesList');
  const emptyEl = document.getElementById('disputeEmpty');

  if (!listEl) return;

  // Show loading
  listEl.innerHTML = `
    <div class="dispute-loading">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Loading disputes...</span>
    </div>
  `;
  listEl.style.display = 'block';
  if (emptyEl) emptyEl.style.display = 'none';

  fetch('/admin/api/reports')
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        disputesData = data.reports || [];

        // Update stats
        const openEl = document.getElementById('disputeStatsOpen');
        const resolvedEl = document.getElementById('disputeStatsResolvedToday');
        if (openEl) openEl.textContent = data.stats.open;
        if (resolvedEl) resolvedEl.textContent = data.stats.resolved_today;

        renderDisputes();
      } else {
        listEl.innerHTML = '<p class="error-message">Failed to load disputes.</p>';
      }
    })
    .catch(err => {
      console.error('[Admin Disputes] Error:', err);
      listEl.innerHTML = '<p class="error-message">Failed to load disputes.</p>';
    });
}

function renderDisputes() {
  const listEl = document.getElementById('disputesList');
  const emptyEl = document.getElementById('disputeEmpty');

  if (!listEl) return;

  // Filter to open disputes only for the main list
  const openDisputes = disputesData.filter(r =>
    ['open', 'under_investigation', 'pending_review'].includes(r.status)
  );

  if (openDisputes.length === 0) {
    listEl.style.display = 'none';
    if (emptyEl) emptyEl.style.display = 'block';
    return;
  }

  listEl.style.display = 'flex';
  if (emptyEl) emptyEl.style.display = 'none';

  let html = '';
  openDisputes.forEach(report => {
    html += renderDisputeCard(report);
  });

  listEl.innerHTML = html;
}

function renderDisputeCard(report) {
  const statusClass = getStatusClass(report.status);
  const amount = report.order_amount ? '$' + report.order_amount.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : 'N/A';

  // Get initials for avatars
  const reporterInitials = getInitials(report.reporter_username);
  const reportedInitials = getInitials(report.reported_username);

  // Format date nicely
  const formattedDate = formatDisputeDate(report.created_at);

  // Photo badge
  const photoHtml = report.photo_count > 0
    ? `<span class="dispute-photos-badge">${report.photo_count} photo${report.photo_count > 1 ? 's' : ''} attached</span>`
    : '';

  return `
    <div class="dispute-card" data-report-id="${report.id}">
      <!-- Header Row -->
      <div class="dispute-header-row">
        <div class="dispute-header-left">
          <div class="dispute-type-icon">
            <i class="fa-regular fa-flag"></i>
          </div>
          <span class="status-badge ${statusClass}">${report.status_display}</span>
          <span class="dispute-id">#d${report.id}</span>
          <span class="dispute-reason-title">${escapeHtml(report.reason_display)}</span>
        </div>
        <div class="dispute-header-right">
          <span class="dispute-date"><i class="fa-regular fa-clock"></i> ${formattedDate}</span>
          <span class="dispute-amount">${amount}</span>
        </div>
      </div>

      <!-- Parties Row -->
      <div class="dispute-parties-row">
        <div class="dispute-party-left">
          <div class="party-avatar party-avatar-blue">${reporterInitials}</div>
          <div class="party-info">
            <span class="party-label">Reporter</span>
            <span class="party-username" onclick="viewUserStats(${report.reporter_user_id})">@${escapeHtml(report.reporter_username)}</span>
          </div>
          <button class="party-stats-btn" onclick="viewUserStats(${report.reporter_user_id})" title="View Stats">
            <i class="fa-solid fa-chart-simple"></i>
          </button>
        </div>

        <div class="dispute-arrow">
          <i class="fa-solid fa-arrow-right"></i>
        </div>

        <div class="dispute-party-right">
          <span class="party-label">Reported</span>
          <span class="party-username" onclick="viewUserStats(${report.reported_user_id})">@${escapeHtml(report.reported_username)}</span>
          <button class="party-stats-btn" onclick="viewUserStats(${report.reported_user_id})" title="View Stats">
            <i class="fa-solid fa-chart-simple"></i>
          </button>
          <div class="party-avatar party-avatar-red">${reportedInitials}</div>
        </div>
      </div>

      <!-- Description -->
      ${report.comment ? `<p class="dispute-description">${escapeHtml(report.comment)}</p>` : ''}

      <!-- Photos Badge -->
      ${photoHtml}

      <!-- Actions Row -->
      <div class="dispute-actions-row">
        <div class="dispute-actions-left">
          <button class="dispute-btn dispute-btn-primary" onclick="viewReportDetails(${report.id})">
            <i class="fa-regular fa-eye"></i> View Details
          </button>
          <button class="dispute-btn dispute-btn-warning-outline" onclick="haltFunds(${report.id})">
            <i class="fa-regular fa-circle-pause"></i> Halt Funds
          </button>
          <button class="dispute-btn dispute-btn-success-outline" onclick="refundBuyer(${report.id})">
            <i class="fa-solid fa-rotate-left"></i> Refund Buyer
          </button>
        </div>
        <div class="dispute-actions-right">
          <button class="dispute-icon-btn" title="Message User" onclick="messageUser(${report.reported_user_id}, '${escapeHtml(report.reported_username)}')">
            <i class="fa-regular fa-comment"></i>
          </button>
          <button class="dispute-icon-btn dispute-icon-btn-blue" title="Freeze User" onclick="freezeUser(${report.reported_user_id}, false)">
            <i class="fa-solid fa-snowflake"></i>
          </button>
          <button class="dispute-icon-btn dispute-icon-btn-red" title="Delete User" onclick="deleteUser(${report.reported_user_id}, '${escapeHtml(report.reported_username)}')">
            <i class="fa-regular fa-trash-can"></i>
          </button>
        </div>
      </div>
    </div>
  `;
}

function getInitials(username) {
  if (!username) return '??';
  // Take first two characters and uppercase
  return username.substring(0, 2).toUpperCase();
}

function formatDisputeDate(dateStr) {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    const options = { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' };
    return date.toLocaleDateString('en-US', options).replace(',', ',');
  } catch (e) {
    return dateStr;
  }
}

function getStatusClass(status) {
  const classes = {
    'open': 'status-investigating',
    'under_investigation': 'status-investigating',
    'pending_review': 'status-pending',
    'resolved': 'status-resolved',
    'dismissed': 'status-dismissed'
  };
  return classes[status] || 'status-pending';
}

function viewReportDetails(reportId) {
  currentReportId = reportId;

  fetch(`/admin/api/reports/${reportId}`)
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        renderReportDetailsModal(data.report);
        document.getElementById('adminReportDetailsModal').style.display = 'flex';
      } else {
        alert('Failed to load report details.');
      }
    })
    .catch(err => {
      console.error('[Admin] Error loading report:', err);
      alert('Failed to load report details.');
    });
}

function renderReportDetailsModal(report) {
  const bodyEl = document.getElementById('adminReportDetailsBody');
  const footerEl = document.getElementById('adminReportDetailsFooter');

  if (!bodyEl) return;

  // Photos HTML
  let photosHtml = '';
  if (report.attachments && report.attachments.length > 0) {
    photosHtml = `
      <div class="report-detail-section">
        <label>Attachments</label>
        <div class="report-photos-grid">
          ${report.attachments.map(a => `
            <a href="${a.file_path}" target="_blank" class="report-photo-thumb">
              <img src="${a.file_path}" alt="Attachment">
            </a>
          `).join('')}
        </div>
      </div>
    `;
  }

  bodyEl.innerHTML = `
    <div class="report-detail-grid">
      <div class="report-detail-section">
        <label>Status</label>
        <span class="status-badge ${getStatusClass(report.status)}">${escapeHtml(report.status_display)}</span>
      </div>

      <div class="report-detail-section">
        <label>Reporter</label>
        <span class="user-link" onclick="viewUserStats(${report.reporter_user_id})">@${escapeHtml(report.reporter_username)}</span>
      </div>

      <div class="report-detail-section">
        <label>Reported User</label>
        <span class="user-link" onclick="viewUserStats(${report.reported_user_id})">@${escapeHtml(report.reported_username)}</span>
      </div>

      <div class="report-detail-section">
        <label>Order</label>
        <span>#${report.order_id} - $${(report.order_amount || 0).toLocaleString('en-US', {minimumFractionDigits: 2})}</span>
      </div>

      <div class="report-detail-section full-width">
        <label>Reason</label>
        <span>${escapeHtml(report.reason_display)}</span>
      </div>

      <div class="report-detail-section full-width">
        <label>Description</label>
        <p class="report-comment-full">${escapeHtml(report.comment || 'No description provided.')}</p>
      </div>

      ${photosHtml}

      <div class="report-detail-section">
        <label>Submitted</label>
        <span>${report.created_at}</span>
      </div>

      ${report.admin_notes ? `
        <div class="report-detail-section full-width">
          <label>Admin Notes</label>
          <p>${escapeHtml(report.admin_notes)}</p>
        </div>
      ` : ''}
    </div>
  `;

  // Footer actions
  if (['open', 'under_investigation', 'pending_review'].includes(report.status)) {
    footerEl.innerHTML = `
      <button class="btn-outline" onclick="closeAdminReportModal()">Close</button>
      <button class="btn-warning" onclick="haltFunds(${report.id})">
        <i class="fa-solid fa-hand"></i> Halt Funds
      </button>
      <button class="btn-success-outline" onclick="refundBuyer(${report.id})">
        <i class="fa-solid fa-rotate-left"></i> Refund Buyer
      </button>
      <button class="btn-primary" onclick="openResolveModal(${report.id})">
        <i class="fa-solid fa-gavel"></i> Resolve
      </button>
    `;
  } else {
    footerEl.innerHTML = `
      <button class="btn-outline" onclick="closeAdminReportModal()">Close</button>
    `;
  }
}

function closeAdminReportModal() {
  document.getElementById('adminReportDetailsModal').style.display = 'none';
  currentReportId = null;
}

function viewUserStats(userId) {
  fetch(`/admin/api/user/${userId}/stats`)
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        renderUserStatsModal(data.user);
        document.getElementById('adminUserStatsModal').style.display = 'flex';
      } else {
        alert('Failed to load user stats.');
      }
    })
    .catch(err => {
      console.error('[Admin] Error loading user stats:', err);
      alert('Failed to load user stats.');
    });
}

function renderUserStatsModal(user) {
  const bodyEl = document.getElementById('adminUserStatsBody');

  if (!bodyEl) return;

  const stats = user.stats;

  // Status badges
  let statusBadges = '';
  if (user.is_admin) statusBadges += '<span class="status-badge status-admin">Admin</span> ';
  if (user.is_banned) statusBadges += '<span class="status-badge status-banned">Banned</span> ';
  if (user.is_frozen) statusBadges += '<span class="status-badge status-frozen">Frozen</span> ';
  if (!statusBadges) statusBadges = '<span class="status-badge status-active">Active</span>';

  bodyEl.innerHTML = `
    <div class="user-stats-header">
      <div class="user-stats-avatar">${user.username.charAt(0).toUpperCase()}</div>
      <div class="user-stats-info">
        <h4>@${escapeHtml(user.username)}</h4>
        <span class="user-stats-email">${escapeHtml(user.email)}</span>
        <div class="user-stats-badges">${statusBadges}</div>
      </div>
    </div>

    <div class="user-stats-grid">
      <div class="stat-box">
        <span class="stat-box-label">Reports Filed</span>
        <span class="stat-box-value">${stats.reports_filed}</span>
      </div>
      <div class="stat-box stat-box-warning">
        <span class="stat-box-label">Reports Received</span>
        <span class="stat-box-value">${stats.reports_received}</span>
      </div>
      <div class="stat-box">
        <span class="stat-box-label">Rating</span>
        <span class="stat-box-value">${stats.rating_avg} <small>(${stats.rating_count})</small></span>
      </div>
      <div class="stat-box">
        <span class="stat-box-label">Active Listings</span>
        <span class="stat-box-value">${stats.active_listings}</span>
      </div>
      <div class="stat-box">
        <span class="stat-box-label">Total Listings</span>
        <span class="stat-box-value">${stats.total_listings}</span>
      </div>
      <div class="stat-box">
        <span class="stat-box-label">Orders (Buyer)</span>
        <span class="stat-box-value">${stats.orders_as_buyer}</span>
      </div>
      <div class="stat-box">
        <span class="stat-box-label">Sales (Seller)</span>
        <span class="stat-box-value">${stats.sales_as_seller}</span>
      </div>
      <div class="stat-box">
        <span class="stat-box-label">Total Volume</span>
        <span class="stat-box-value">$${stats.total_volume.toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0})}</span>
      </div>
    </div>

    <div class="user-stats-meta">
      <span>Member since: ${user.created_at}</span>
    </div>

    <div class="user-stats-actions">
      <button class="btn-outline" onclick="messageUser(${user.id}, '${escapeHtml(user.username)}')">
        <i class="fa-solid fa-message"></i> Message
      </button>
      <button class="btn-warning" onclick="freezeUser(${user.id}, ${user.is_frozen})">
        <i class="fa-solid fa-snowflake"></i> ${user.is_frozen ? 'Unfreeze' : 'Freeze'}
      </button>
    </div>
  `;
}

function closeUserStatsModal() {
  document.getElementById('adminUserStatsModal').style.display = 'none';
}

function openResolveModal(reportId) {
  currentReportId = reportId;
  document.getElementById('resolveReportStatus').value = 'resolved';
  document.getElementById('resolveReportNote').value = '';
  document.getElementById('resolveReportAdminNotes').value = '';
  document.getElementById('adminResolveReportModal').style.display = 'flex';
}

function closeResolveReportModal() {
  document.getElementById('adminResolveReportModal').style.display = 'none';
}

function submitResolveReport() {
  const status = document.getElementById('resolveReportStatus').value;
  const note = document.getElementById('resolveReportNote').value;
  const adminNotes = document.getElementById('resolveReportAdminNotes').value;

  fetch(`/admin/api/reports/${currentReportId}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      status: status,
      resolution_note: note,
      admin_notes: adminNotes
    })
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        closeResolveReportModal();
        closeAdminReportModal();
        loadDisputes();
        showToast('Report resolved successfully', 'success');
      } else {
        alert('Error: ' + data.error);
      }
    })
    .catch(err => {
      console.error('[Admin] Error resolving report:', err);
      alert('Failed to resolve report.');
    });
}

function quickResolve(reportId, status) {
  if (!confirm(`Are you sure you want to mark this report as ${status}?`)) return;

  fetch(`/admin/api/reports/${reportId}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: status })
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        loadDisputes();
        showToast('Report updated', 'success');
      } else {
        alert('Error: ' + data.error);
      }
    })
    .catch(err => {
      console.error('[Admin] Error:', err);
      alert('Failed to update report.');
    });
}

function haltFunds(reportId) {
  fetch(`/admin/api/reports/${reportId}/halt-funds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
    .then(res => res.json())
    .then(data => {
      alert(data.message || 'Halt funds functionality is not yet implemented.');
    })
    .catch(err => {
      console.error('[Admin] Error:', err);
      alert('Failed to halt funds.');
    });
}

function refundBuyer(reportId) {
  fetch(`/admin/api/reports/${reportId}/refund`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
    .then(res => res.json())
    .then(data => {
      alert(data.message || 'Refund functionality is not yet implemented.');
    })
    .catch(err => {
      console.error('[Admin] Error:', err);
      alert('Failed to refund buyer.');
    });
}

function showToast(message, type = 'info') {
  let container = document.getElementById('adminToastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'adminToastContainer';
    container.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 100000;';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  const bgColor = type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6';
  toast.style.cssText = `padding: 12px 20px; background: ${bgColor}; color: white; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => toast.remove(), 3000);
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Initialize disputes, messages, and ledger when tab is activated
const originalSwitchTab = window.switchTab;
window.switchTab = function(tabName) {
  originalSwitchTab(tabName);
  if (tabName === 'disputes') {
    loadDisputes();
  } else if (tabName === 'messages') {
    loadAdminConversations();
  } else if (tabName === 'ledger') {
    loadLedgerStats();
    loadLedgerOrders();
  }
};

// ============================================
// LEDGER FUNCTIONS
// ============================================
