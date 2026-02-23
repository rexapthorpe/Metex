// static/js/tabs/reports_tab.js

let reportsData = [];
let currentReportsFilter = 'all';

/**
 * Initialize the reports tab
 */
function initReportsTab() {
  loadReports();
}

/**
 * Load reports from the API
 */
function loadReports() {
  const listEl = document.getElementById('reportsList');
  const emptyEl = document.getElementById('reportsEmptyState');
  const filteredEmptyEl = document.getElementById('reportsFilteredEmpty');
  const statsEl = document.getElementById('reportsStats');

  // Show loading
  if (listEl) {
    listEl.innerHTML = `
      <div class="reports-loading">
        <i class="fa-solid fa-spinner fa-spin"></i>
        <span>Loading reports...</span>
      </div>
    `;
    listEl.style.display = 'block';
  }
  if (emptyEl) emptyEl.style.display = 'none';
  if (filteredEmptyEl) filteredEmptyEl.style.display = 'none';

  fetch('/api/reports/my-reports')
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        reportsData = data.reports || [];

        // Update stats
        if (statsEl) {
          statsEl.textContent = `${data.total} total reports • ${data.active} active`;
        }

        // Update sidebar badge
        const badge = document.getElementById('sidebarReportsBadge');
        if (badge) {
          if (data.active > 0) {
            badge.textContent = data.active;
            badge.style.display = '';
          } else {
            badge.style.display = 'none';
          }
        }

        // Render reports
        renderReports();
      } else {
        console.error('[Reports Tab] Error:', data.error);
        if (listEl) {
          listEl.innerHTML = '<p class="error-message">Failed to load reports. Please try again.</p>';
        }
      }
    })
    .catch(err => {
      console.error('[Reports Tab] Error:', err);
      if (listEl) {
        listEl.innerHTML = '<p class="error-message">Failed to load reports. Please try again.</p>';
      }
    });
}

/**
 * Render reports based on current filter
 */
function renderReports() {
  const listEl = document.getElementById('reportsList');
  const emptyEl = document.getElementById('reportsEmptyState');
  const filteredEmptyEl = document.getElementById('reportsFilteredEmpty');

  if (!listEl) return;

  // Filter reports
  let filteredReports = reportsData;
  if (currentReportsFilter === 'active') {
    filteredReports = reportsData.filter(r =>
      ['open', 'under_investigation', 'pending_review'].includes(r.status)
    );
  } else if (currentReportsFilter === 'resolved') {
    filteredReports = reportsData.filter(r => r.status === 'resolved');
  } else if (currentReportsFilter === 'dismissed') {
    filteredReports = reportsData.filter(r => r.status === 'dismissed');
  }

  // Handle empty states
  if (reportsData.length === 0) {
    listEl.style.display = 'none';
    if (emptyEl) emptyEl.style.display = 'block';
    if (filteredEmptyEl) filteredEmptyEl.style.display = 'none';
    return;
  }

  if (filteredReports.length === 0) {
    listEl.style.display = 'none';
    if (emptyEl) emptyEl.style.display = 'none';
    if (filteredEmptyEl) {
      filteredEmptyEl.style.display = 'block';
      const filterName = filteredEmptyEl.querySelector('.filter-type-name');
      if (filterName) {
        const names = {
          'active': 'Active',
          'resolved': 'Resolved',
          'dismissed': 'Dismissed'
        };
        filterName.textContent = names[currentReportsFilter] || '';
      }
    }
    return;
  }

  // Show list and hide empty states
  listEl.style.display = 'flex';
  if (emptyEl) emptyEl.style.display = 'none';
  if (filteredEmptyEl) filteredEmptyEl.style.display = 'none';

  // Build HTML
  let html = '';
  filteredReports.forEach(report => {
    html += renderReportCard(report);
  });

  listEl.innerHTML = html;
}

/**
 * Render a single report card
 */
function renderReportCard(report) {
  // Get icon class based on reason
  const iconClasses = {
    'counterfeit_fake': 'icon-counterfeit',
    'not_as_described': 'icon-not-as-described',
    'scam_fraud': 'icon-scam',
    'harassment_abuse': 'icon-harassment',
    'payment_issues': 'icon-payment',
    'other': 'icon-other'
  };

  const iconIcons = {
    'counterfeit_fake': 'fa-solid fa-gem',
    'not_as_described': 'fa-solid fa-triangle-exclamation',
    'scam_fraud': 'fa-solid fa-circle-dollar-to-slot',
    'harassment_abuse': 'fa-solid fa-user-slash',
    'payment_issues': 'fa-solid fa-credit-card',
    'other': 'fa-solid fa-ellipsis'
  };

  const iconClass = iconClasses[report.reason] || 'icon-other';
  const iconIcon = iconIcons[report.reason] || 'fa-solid fa-flag';

  // Get status badge class
  const statusClass = `status-${report.status.replace(/_/g, '-')}`;

  // Format date
  const createdDate = report.created_at ? formatReportDate(report.created_at) : 'Unknown';

  // Resolution note if resolved
  let resolutionHtml = '';
  if (report.status === 'resolved' && report.resolution_note) {
    resolutionHtml = `
      <div class="report-resolution-note">
        <strong>Resolution:</strong>
        ${escapeHtml(report.resolution_note)}
      </div>
    `;
  }

  // Photo count
  const photoHtml = report.photo_count > 0
    ? `<span class="report-card-photos"><i class="fa-solid fa-image"></i> ${report.photo_count} photo${report.photo_count > 1 ? 's' : ''}</span>`
    : '';

  return `
    <div class="report-card" data-report-id="${report.id}">
      <div class="report-card-header">
        <div class="report-card-icon ${iconClass}">
          <i class="${iconIcon}"></i>
        </div>

        <div class="report-card-info">
          <div class="report-card-title">
            <h3>Report against @${escapeHtml(report.reported_username)}</h3>
            <span class="report-status-badge ${statusClass}">${escapeHtml(report.status_display)}</span>
          </div>
          <div class="report-card-reason">${escapeHtml(report.reason_display)}</div>
          <div class="report-card-meta">
            <span><i class="fa-regular fa-clock"></i> ${createdDate}</span>
            <span><i class="fa-solid fa-receipt"></i> Order #${escapeHtml(report.order_id_formatted)}</span>
            ${photoHtml}
          </div>
        </div>

        <div class="report-card-action">
          <button class="report-view-btn" onclick="openReportDetails(${report.id})">
            <i class="fa-solid fa-eye"></i>
            View Details
          </button>
        </div>
      </div>

      ${resolutionHtml}
    </div>
  `;
}

/**
 * Filter reports by status
 */
function filterReports(filter) {
  currentReportsFilter = filter;

  // Update filter button states (supports both old .filter-btn and new .filter-pill)
  const filterBtns = document.querySelectorAll('.reports-tab .filter-btn, .reports-tab .filter-pill');
  filterBtns.forEach(btn => {
    btn.classList.toggle('active', btn.dataset.filter === filter);
  });

  renderReports();
}

/**
 * Open report details modal
 */
function openReportDetails(reportId) {
  fetch(`/api/reports/${reportId}`)
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        renderReportDetails(data.report);
        showReportDetailsModal();
      } else {
        alert(data.error || 'Failed to load report details.');
      }
    })
    .catch(err => {
      console.error('[Reports Tab] Error loading details:', err);
      alert('Failed to load report details. Please try again.');
    });
}

/**
 * Render report details in the modal (read-only view matching submit modal)
 */
function renderReportDetails(report) {
  // Update header info
  const usernameEl = document.getElementById('viewReportUsername');
  const orderBadgeEl = document.getElementById('viewReportOrderBadge');

  if (usernameEl) usernameEl.textContent = '@' + escapeHtml(report.reported_username);
  if (orderBadgeEl) orderBadgeEl.textContent = 'Order #' + escapeHtml(report.order_id_formatted);

  // Update status banner based on report status
  const statusBanner = document.getElementById('viewReportStatusBanner');
  const statusTitle = document.getElementById('viewReportStatusTitle');
  const statusDesc = document.getElementById('viewReportStatusDesc');

  if (statusBanner && statusTitle && statusDesc) {
    // Remove existing status classes
    statusBanner.className = 'report-view-status-banner';

    const statusInfo = getStatusBannerInfo(report.status);
    statusBanner.classList.add(statusInfo.class);
    statusBanner.querySelector('i').className = statusInfo.icon;
    statusTitle.textContent = statusInfo.title;
    statusDesc.textContent = statusInfo.description;
  }

  // Highlight the selected reason
  const reasonsList = document.getElementById('viewReportReasonsList');
  if (reasonsList) {
    const allReasons = reasonsList.querySelectorAll('.report-reason-option');
    allReasons.forEach(option => {
      option.classList.remove('selected');
      option.style.display = 'none'; // Hide all by default
    });

    // Map reason values to indices
    const reasonMap = {
      'counterfeit_fake': 0,
      'not_as_described': 1,
      'scam_fraud': 2,
      'harassment_abuse': 3,
      'payment_issues': 4,
      'other': 5
    };

    const selectedIndex = reasonMap[report.reason];
    if (selectedIndex !== undefined && allReasons[selectedIndex]) {
      allReasons[selectedIndex].classList.add('selected');
      allReasons[selectedIndex].style.display = 'block'; // Show only selected
    }
  }

  // Update description
  const descEl = document.getElementById('viewReportDescription');
  if (descEl) {
    descEl.textContent = report.comment || 'No additional details provided.';
  }

  // Update photos
  const photosSection = document.getElementById('viewReportPhotosSection');
  const photosContainer = document.getElementById('viewReportPhotos');

  if (report.attachments && report.attachments.length > 0) {
    if (photosSection) photosSection.style.display = 'block';
    if (photosContainer) {
      photosContainer.innerHTML = report.attachments.map(a => `
        <a class="report-attachment-item report-attachment-readonly" href="${a.file_path}" target="_blank">
          <img src="${a.file_path}" alt="${escapeHtml(a.original_filename || 'Attachment')}">
        </a>
      `).join('');
    }
  } else {
    if (photosSection) photosSection.style.display = 'none';
  }

  // Update submitted date
  const dateEl = document.getElementById('viewReportDate');
  if (dateEl) {
    const dateSpan = dateEl.querySelector('span');
    if (dateSpan) {
      dateSpan.textContent = report.created_at ? formatReportDate(report.created_at, true) : 'Unknown';
    }
  }

  // Update resolution section
  const resolutionSection = document.getElementById('viewReportResolutionSection');
  const resolutionEl = document.getElementById('viewReportResolution');

  if (report.resolution_note && (report.status === 'resolved' || report.status === 'dismissed')) {
    if (resolutionSection) resolutionSection.style.display = 'block';
    if (resolutionEl) resolutionEl.textContent = report.resolution_note;
  } else {
    if (resolutionSection) resolutionSection.style.display = 'none';
  }
}

/**
 * Get status banner info based on report status
 */
function getStatusBannerInfo(status) {
  const statusMap = {
    'open': {
      class: 'status-open',
      icon: 'fa-solid fa-clock',
      title: 'Report Submitted',
      description: 'Your report has been received and is awaiting review.'
    },
    'under_investigation': {
      class: 'status-investigating',
      icon: 'fa-solid fa-magnifying-glass',
      title: 'Under Investigation',
      description: 'Our team is actively investigating this report.'
    },
    'pending_review': {
      class: 'status-pending',
      icon: 'fa-solid fa-hourglass-half',
      title: 'Pending Review',
      description: 'This report is pending final review.'
    },
    'resolved': {
      class: 'status-resolved',
      icon: 'fa-solid fa-circle-check',
      title: 'Resolved',
      description: 'This report has been reviewed and resolved.'
    },
    'dismissed': {
      class: 'status-dismissed',
      icon: 'fa-solid fa-circle-xmark',
      title: 'Dismissed',
      description: 'This report has been reviewed and dismissed.'
    }
  };

  return statusMap[status] || {
    class: 'status-open',
    icon: 'fa-solid fa-circle-info',
    title: 'Status Unknown',
    description: 'Report status is being determined.'
  };
}

/**
 * Show the report details modal
 */
function showReportDetailsModal() {
  const modal = document.getElementById('reportDetailsModal');
  if (modal) {
    modal.style.display = 'flex';
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
    modal.addEventListener('click', reportDetailsOutsideClickListener);
  }
}

/**
 * Close the report details modal
 */
function closeReportDetailsModal() {
  const modal = document.getElementById('reportDetailsModal');
  if (modal) {
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
    modal.style.display = 'none';
    modal.removeEventListener('click', reportDetailsOutsideClickListener);
  }
}

/**
 * Handle clicks outside the modal content
 */
function reportDetailsOutsideClickListener(e) {
  if (e.target && e.target.id === 'reportDetailsModal') {
    closeReportDetailsModal();
  }
}

/**
 * Format a date string
 */
function formatReportDate(dateStr, includeTime = false) {
  try {
    const date = new Date(dateStr);
    const options = {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    };

    if (includeTime) {
      options.hour = '2-digit';
      options.minute = '2-digit';
    }

    return date.toLocaleDateString('en-US', options);
  } catch (e) {
    return dateStr;
  }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Export functions globally
window.initReportsTab = initReportsTab;
window.loadReports = loadReports;
window.filterReports = filterReports;
window.openReportDetails = openReportDetails;
window.closeReportDetailsModal = closeReportDetailsModal;

// Initialize when tab is shown
document.addEventListener('DOMContentLoaded', function() {
  // Watch for tab changes (if using a tab system)
  const reportsTab = document.getElementById('reports-tab');
  if (reportsTab) {
    // Create a MutationObserver to watch for display changes
    const observer = new MutationObserver(function(mutations) {
      mutations.forEach(function(mutation) {
        if (mutation.attributeName === 'style' || mutation.attributeName === 'class') {
          const style = window.getComputedStyle(reportsTab);
          if (style.display !== 'none') {
            // Tab is now visible, load reports if not already loaded
            if (reportsData.length === 0) {
              loadReports();
            }
          }
        }
      });
    });

    observer.observe(reportsTab, { attributes: true });
  }
});
