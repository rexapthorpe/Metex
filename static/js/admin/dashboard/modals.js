
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

// ── Email Templates Modal ──────────────────────────────────────────────────────

var _emailTemplates = [];
var _emailTemplateIdx = 0;

function openEmailTemplates() {
  var modal = document.getElementById('emailTemplatesModal');
  if (!modal) return;

  _emailTemplates = [];
  _emailTemplateIdx = 0;

  var frame   = document.getElementById('emailTemplateFrame');
  var label   = document.getElementById('emailTemplateLabel');
  var counter = document.getElementById('emailTemplateCounter');
  var prev    = document.getElementById('emailTemplatePrev');
  var next    = document.getElementById('emailTemplateNext');

  if (frame)   frame.srcdoc = '<div style="padding:40px;text-align:center;font-family:sans-serif;color:#6b7280"><i class="fa-solid fa-spinner fa-spin fa-lg"></i><br><br>Loading templates...</div>';
  if (label)   label.textContent = 'Email Templates';
  if (counter) counter.textContent = '';
  if (prev)    prev.disabled = true;
  if (next)    next.disabled = true;

  modal.style.display = 'flex';

  fetch('/admin/api/email-templates')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.success || !data.templates || !data.templates.length) {
        if (frame) frame.srcdoc = '<p style="color:#ef4444;padding:20px">No templates found.</p>';
        return;
      }
      _emailTemplates = data.templates;
      _emailTemplateIdx = 0;
      _renderEmailTemplate();
    })
    .catch(function(err) {
      if (frame) frame.srcdoc = '<p style="color:#ef4444;padding:20px">Failed to load templates: ' + String(err) + '</p>';
    });
}

function _renderEmailTemplate() {
  var t = _emailTemplates[_emailTemplateIdx];
  if (!t) return;
  var frame   = document.getElementById('emailTemplateFrame');
  var label   = document.getElementById('emailTemplateLabel');
  var counter = document.getElementById('emailTemplateCounter');
  var prev    = document.getElementById('emailTemplatePrev');
  var next    = document.getElementById('emailTemplateNext');

  if (label)   label.textContent = t.label;
  if (counter) counter.textContent = (_emailTemplateIdx + 1) + ' of ' + _emailTemplates.length;
  if (frame)   frame.srcdoc = t.html;
  if (prev)    prev.disabled = _emailTemplateIdx === 0;
  if (next)    next.disabled = _emailTemplateIdx === _emailTemplates.length - 1;
}

function emailTemplatePrev() {
  if (_emailTemplateIdx > 0) {
    _emailTemplateIdx--;
    _renderEmailTemplate();
  }
}

function emailTemplateNext() {
  if (_emailTemplateIdx < _emailTemplates.length - 1) {
    _emailTemplateIdx++;
    _renderEmailTemplate();
  }
}

function closeEmailTemplatesModal() {
  var modal = document.getElementById('emailTemplatesModal');
  if (modal) modal.style.display = 'none';
}

function openSecuritySettings() {
  alert('Security Settings would open here.');
}

function openFeeConfig() {
  var overlay = document.getElementById('feeConfigModal');
  var formEl  = document.querySelector('.fee-config-form-content');
  var successEl = document.getElementById('feeConfigSuccessContent');
  var input   = document.getElementById('feeConfigInput');
  var errEl   = document.getElementById('feeConfigError');
  var current = document.getElementById('feeConfigCurrentValue');
  var saveBtn = document.getElementById('feeConfigSaveBtn');

  if (!overlay) return;

  // Reset to form view
  if (formEl)     formEl.style.display = '';
  if (successEl)  successEl.style.display = 'none';
  if (errEl)      errEl.style.display = 'none';
  if (input)      input.value = '';
  if (current)    current.textContent = 'Loading…';
  if (saveBtn)    saveBtn.disabled = false;

  overlay.style.display = 'flex';

  // Load current fee
  fetch('/admin/api/system-settings/default-fee')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.success && current) {
        current.textContent = data.fee_value + '%';
        if (input) input.value = data.fee_value;
      } else if (current) {
        current.textContent = 'Unknown';
      }
    })
    .catch(function () {
      if (current) current.textContent = 'Error loading';
    });
}

function closeFeeConfigModal() {
  var overlay = document.getElementById('feeConfigModal');
  if (overlay) overlay.style.display = 'none';
}

function saveFeeConfig() {
  var input   = document.getElementById('feeConfigInput');
  var errEl   = document.getElementById('feeConfigError');
  var saveBtn = document.getElementById('feeConfigSaveBtn');
  var formEl  = document.querySelector('.fee-config-form-content');
  var successEl = document.getElementById('feeConfigSuccessContent');
  var successMsg = document.getElementById('feeConfigSuccessMessage');

  var val = parseFloat(input.value);
  if (input.value === '' || isNaN(val) || val < 0 || val > 100) {
    errEl.style.display = 'block';
    return;
  }
  errEl.style.display = 'none';
  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving…';

  fetch('/admin/api/system-settings/default-fee', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ fee_type: 'percent', fee_value: val }),
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.success) {
        if (formEl)    formEl.style.display = 'none';
        if (successEl) { successEl.style.display = 'flex'; }
        if (successMsg) successMsg.textContent = 'Platform fee set to ' + val + '%.';
      } else {
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> Save Fee';
        errEl.textContent = data.message || 'Failed to save. Please try again.';
        errEl.style.display = 'block';
      }
    })
    .catch(function () {
      saveBtn.disabled = false;
      saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> Save Fee';
      errEl.textContent = 'Network error — please try again.';
      errEl.style.display = 'block';
    });
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

