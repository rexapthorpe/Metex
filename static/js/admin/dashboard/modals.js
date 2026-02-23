
function initModalClose() {
  // Close modals when clicking outside (.admin-modal-overlay for user modals)
  document.querySelectorAll('.admin-modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', function(e) {
      if (e.target === this) {
        // If this is the message modal, use the proper close function to refresh conversations
        if (this.id === 'messageModal') {
          closeMessageModal();
        } else if (this.id === 'metricsModal') {
          // Use proper close function to destroy chart
          if (typeof closeMetricsModal === 'function') {
            closeMetricsModal();
          }
        } else {
          this.style.display = 'none';
          pendingAction = null;
        }
      }
    });
  });

  // Close modals when clicking outside (.admin-modal for dispute modals)
  document.querySelectorAll('.admin-modal').forEach(modal => {
    modal.addEventListener('click', function(e) {
      if (e.target === this) {
        this.style.display = 'none';
        pendingAction = null;
        currentReportId = null;
      }
    });
  });

  // Close modals on Escape key
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      // Check if message modal is open and close it properly
      const messageModal = document.getElementById('messageModal');
      if (messageModal && messageModal.style.display === 'flex') {
        closeMessageModal();
      }

      // Check if metrics modal is open and close it properly (destroys chart)
      const metricsModal = document.getElementById('metricsModal');
      if (metricsModal && metricsModal.style.display === 'flex') {
        if (typeof closeMetricsModal === 'function') {
          closeMetricsModal();
        }
      }

      document.querySelectorAll('.admin-modal-overlay').forEach(modal => {
        if (modal.id !== 'messageModal' && modal.id !== 'metricsModal') {
          modal.style.display = 'none';
        }
      });
      document.querySelectorAll('.admin-modal').forEach(modal => {
        modal.style.display = 'none';
      });
      pendingAction = null;
      currentReportId = null;
    }
  });
}

// ============================================
// HEADER ACTIONS
// ============================================

function exportData() {
  const activeTab = document.querySelector('.admin-tab.active')?.dataset.tab || 'overview';
  alert(`Export functionality for ${activeTab} data would be implemented here.`);
}

function refreshDashboard() {
  location.reload();
}

function openSettings() {
  alert('Settings panel would open here.');
}

// System Settings Actions
function openEmailTemplates() {
  alert('Email Templates management would open here.');
}

function openSecuritySettings() {
  alert('Security Settings would open here.');
}

function openFeeConfig() {
  alert('Fee Configuration would open here.');
}

function openApiManagement() {
  alert('API Management would open here.');
}

// Utility: Debounce function
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func.apply(this, args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// ============================================
// CLEAR DATA FUNCTIONS
// ============================================

