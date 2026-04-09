/**
 * Admin Disputes Tab (Phase 3)
 * ============================
 * Handles the admin dispute adjudication workflow:
 *  - List view with filters
 *  - Detail modal (metadata, evidence, timeline, snapshots)
 *  - Status change actions (evidence_requested, under_review, escalated)
 *  - Resolution actions (resolved_refund, resolved_denied, closed)
 *  - Internal admin notes
 */

// ── State ────────────────────────────────────────────────────────────────────
let adminDisputesData = [];
let currentAdminDisputeId = null;

// ── Status helpers ────────────────────────────────────────────────────────────

const DISPUTE_STATUS_LABELS = {
  open:               'Open',
  evidence_requested: 'Evidence Requested',
  under_review:       'Under Review',
  escalated:          'Escalated',
  resolved_refund:    'Resolved — Refund',
  resolved_denied:    'Resolved — Denied',
  resolved_partial:   'Resolved — Partial',
  closed:             'Closed',
};

const DISPUTE_TYPE_LABELS = {
  not_received:    'Item Not Received',
  not_as_described:'Not as Described',
  counterfeit:     'Counterfeit',
  wrong_item:      'Wrong Item',
};

const DISPUTE_STATUS_CSS = {
  open:               'status-investigating',
  evidence_requested: 'status-pending',
  under_review:       'status-pending',
  escalated:          'status-banned',
  resolved_refund:    'status-resolved',
  resolved_denied:    'status-dismissed',
  resolved_partial:   'status-resolved',
  closed:             'status-dismissed',
};

const ACTIVE_STATUSES = new Set(['open', 'evidence_requested', 'under_review', 'escalated']);

function disputeStatusLabel(s)  { return DISPUTE_STATUS_LABELS[s]  || s; }
function disputeTypeLabel(t)    { return DISPUTE_TYPE_LABELS[t]    || (t || '').replace(/_/g, ' '); }
function disputeStatusCss(s)    { return DISPUTE_STATUS_CSS[s]     || 'status-pending'; }
function isActiveDispute(s)     { return ACTIVE_STATUSES.has(s); }

// ── Load & Render List ────────────────────────────────────────────────────────

function loadAdminDisputes() {
  const listEl  = document.getElementById('adminDisputesList');
  const emptyEl = document.getElementById('adminDisputesEmpty');
  if (!listEl) return;

  listEl.innerHTML = `
    <div class="dispute-loading">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Loading disputes...</span>
    </div>`;
  listEl.style.display = 'block';
  if (emptyEl) emptyEl.style.display = 'none';

  const status       = document.getElementById('disputeFilterStatus')?.value  || '';
  const disputeType  = document.getElementById('disputeFilterType')?.value    || '';
  const buyer        = document.getElementById('disputeFilterBuyer')?.value   || '';
  const seller       = document.getElementById('disputeFilterSeller')?.value  || '';

  const params = new URLSearchParams();
  if (status)      params.set('status',       status);
  if (disputeType) params.set('dispute_type', disputeType);
  if (buyer)       params.set('buyer',        buyer);
  if (seller)      params.set('seller',       seller);

  fetch('/admin/api/disputes?' + params.toString())
    .then(r => r.json())
    .then(data => {
      if (!data.success) throw new Error(data.error || 'Unknown error');

      adminDisputesData = data.disputes || [];

      // Update stats
      const s = data.stats || {};
      const el = id => document.getElementById(id);
      if (el('disputeStatsOpen'))         el('disputeStatsOpen').textContent         = s.open          ?? '—';
      if (el('disputeStatsUnderReview'))  el('disputeStatsUnderReview').textContent  = s.under_review   ?? '—';
      if (el('disputeStatsResolvedToday'))el('disputeStatsResolvedToday').textContent= s.resolved_today ?? '—';

      renderAdminDisputesList(adminDisputesData);
    })
    .catch(err => {
      console.error('[Admin Disputes]', err);
      listEl.innerHTML = '<p class="error-message">Failed to load disputes.</p>';
    });
}

function renderAdminDisputesList(disputes) {
  const listEl  = document.getElementById('adminDisputesList');
  const emptyEl = document.getElementById('adminDisputesEmpty');
  if (!listEl) return;

  if (!disputes.length) {
    listEl.style.display = 'none';
    if (emptyEl) emptyEl.style.display = 'block';
    return;
  }
  if (emptyEl) emptyEl.style.display = 'none';

  const rows = disputes.map(d => {
    const amount = d.order_amount
      ? '$' + d.order_amount.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})
      : '—';
    const opened = d.opened_at ? d.opened_at.substring(0, 10) : '—';
    const days   = d.days_open != null ? d.days_open + 'd' : '—';
    const badgeCss = disputeStatusCss(d.status);
    return `
      <tr>
        <td><a href="#" class="user-link" onclick="viewAdminDisputeDetail(${d.id});return false;">#${d.id}</a></td>
        <td>#${d.order_id}</td>
        <td>
          <span class="user-link" onclick="viewUserStats(${d.buyer_id})">@${escapeHtml(d.buyer_username)}</span>
        </td>
        <td>
          <span class="user-link" onclick="viewUserStats(${d.seller_id || 0})">@${escapeHtml(d.seller_username || '—')}</span>
        </td>
        <td>${escapeHtml(disputeTypeLabel(d.dispute_type))}</td>
        <td><span class="status-badge ${badgeCss}">${disputeStatusLabel(d.status)}</span></td>
        <td>${amount}</td>
        <td>${opened}</td>
        <td>${days}</td>
        <td>
          <button class="dispute-btn dispute-btn-primary" style="padding:4px 10px;font-size:12px;"
                  onclick="viewAdminDisputeDetail(${d.id})">
            <i class="fa-regular fa-eye"></i> View
          </button>
        </td>
      </tr>`;
  }).join('');

  listEl.innerHTML = `
    <table class="data-table" style="width:100%;min-width:800px;">
      <thead>
        <tr>
          <th>Dispute</th>
          <th>Order</th>
          <th>Buyer</th>
          <th>Seller</th>
          <th>Type</th>
          <th>Status</th>
          <th>Amount</th>
          <th>Opened</th>
          <th>Age</th>
          <th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ── Detail Modal ──────────────────────────────────────────────────────────────

function viewAdminDisputeDetail(disputeId) {
  currentAdminDisputeId = disputeId;
  const modal = document.getElementById('adminDisputeDetailModal');
  const body  = document.getElementById('adminDisputeDetailBody');
  const title = document.getElementById('adminDisputeDetailTitle');
  if (!modal || !body) return;

  body.innerHTML = '<p style="padding:20px;text-align:center;"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</p>';
  if (title) title.textContent = `Dispute #${disputeId}`;
  modal.style.display = 'flex';

  fetch(`/admin/api/disputes/${disputeId}`)
    .then(r => r.json())
    .then(data => {
      if (!data.success) throw new Error(data.error || 'Unknown error');
      renderDisputeDetailModal(data.dispute);
    })
    .catch(err => {
      console.error('[Admin Disputes]', err);
      body.innerHTML = `<p class="error-message">Failed to load dispute: ${escapeHtml(err.message)}</p>`;
    });
}

function renderDisputeDetailModal(d) {
  const body   = document.getElementById('adminDisputeDetailBody');
  const footer = document.getElementById('adminDisputeDetailFooter');
  if (!body) return;

  // ── Snapshot section ──
  let snapshotHtml = '';
  if (d.snapshots && d.snapshots.length) {
    const s = d.snapshots[0];
    snapshotHtml = `
      <div class="report-detail-section full-width" style="margin-top:12px;">
        <label>Transaction Snapshot</label>
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:12px;font-size:13px;display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;">
          <div><strong>Listing</strong><br>${escapeHtml(s.listing_title || '—')}</div>
          <div><strong>Metal</strong><br>${escapeHtml(s.metal || '—')}</div>
          <div><strong>Weight</strong><br>${escapeHtml(s.weight || '—')}</div>
          <div><strong>Year</strong><br>${escapeHtml(s.year || '—')}</div>
          <div><strong>Qty</strong><br>${s.quantity ?? '—'}</div>
          <div><strong>Price Each</strong><br>${s.price_each != null ? '$' + s.price_each.toFixed(2) : '—'}</div>
          <div><strong>Seller</strong><br>${escapeHtml(s.seller_username || '—')}</div>
          <div><strong>Buyer</strong><br>${escapeHtml(s.buyer_username || '—')}</div>
          ${s.payment_intent_id ? `<div style="grid-column:1/-1;"><strong>Payment Intent</strong><br><code style="font-size:11px;">${escapeHtml(s.payment_intent_id)}</code></div>` : ''}
        </div>
      </div>`;
  }

  // ── Evidence section ──
  let evidenceHtml = '';
  if (d.evidence && d.evidence.length) {
    const items = d.evidence.map(e => `
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:10px;font-size:13px;">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
          <strong>${escapeHtml(e.actor_type)} — ${escapeHtml(e.evidence_type)}</strong>
          <span style="color:#6b7280;">${(e.submitted_at||'').substring(0,16)}</span>
        </div>
        <div style="color:#6b7280;font-size:11px;margin-bottom:4px;">by @${escapeHtml(e.submitter_username||'?')}</div>
        ${e.note ? `<p style="margin:0 0 4px;">${escapeHtml(e.note)}</p>` : ''}
        ${e.file_path ? `<a href="/static/${escapeHtml(e.file_path)}" target="_blank" style="color:#7c3aed;font-size:12px;">View attachment</a>` : ''}
      </div>`).join('');
    evidenceHtml = `
      <div class="report-detail-section full-width" style="margin-top:12px;">
        <label>Evidence (${d.evidence.length})</label>
        <div style="display:grid;gap:8px;">${items}</div>
      </div>`;
  }

  // ── Timeline section ──
  let timelineHtml = '';
  if (d.timeline && d.timeline.length) {
    const entries = d.timeline.map(t => {
      const isAdmin = t.actor_type === 'admin';
      const bg      = isAdmin ? '#fef3c7' : '#f9fafb';
      const label   = isAdmin && t.event_type === 'admin_note' ? '🔒 Admin Note (internal)' : escapeHtml(t.event_type);
      return `
        <div style="background:${bg};border:1px solid #e5e7eb;border-radius:6px;padding:8px 12px;font-size:13px;">
          <div style="display:flex;justify-content:space-between;margin-bottom:2px;">
            <strong>${label}</strong>
            <span style="color:#6b7280;font-size:11px;">${(t.created_at||'').substring(0,16)}</span>
          </div>
          <div style="color:#6b7280;font-size:11px;">by ${t.actor_type} @${escapeHtml(t.actor_username||String(t.actor_id))}</div>
          ${t.note ? `<p style="margin:4px 0 0;color:#374151;">${escapeHtml(t.note)}</p>` : ''}
        </div>`;
    }).join('');
    timelineHtml = `
      <div class="report-detail-section full-width" style="margin-top:12px;">
        <label>Timeline</label>
        <div style="display:flex;flex-direction:column;gap:6px;max-height:280px;overflow-y:auto;">${entries}</div>
      </div>`;
  }

  const amount  = d.order_amount ? '$' + d.order_amount.toFixed(2) : '—';
  const badgeCss = disputeStatusCss(d.status);

  body.innerHTML = `
    <div class="report-detail-grid">
      <div class="report-detail-section">
        <label>Status</label>
        <span class="status-badge ${badgeCss}">${disputeStatusLabel(d.status)}</span>
      </div>
      <div class="report-detail-section">
        <label>Dispute Type</label>
        <span>${escapeHtml(disputeTypeLabel(d.dispute_type))}</span>
      </div>
      <div class="report-detail-section">
        <label>Buyer</label>
        <span class="user-link" onclick="viewUserStats(${d.buyer_id})">@${escapeHtml(d.buyer_username)}</span>
        <span style="color:#6b7280;font-size:12px;"> ${escapeHtml(d.buyer_email)}</span>
      </div>
      <div class="report-detail-section">
        <label>Seller</label>
        <span class="user-link" onclick="viewUserStats(${d.seller_id||0})">@${escapeHtml(d.seller_username||'—')}</span>
        <span style="color:#6b7280;font-size:12px;"> ${escapeHtml(d.seller_email||'')}</span>
      </div>
      <div class="report-detail-section">
        <label>Order</label>
        <span>#${d.order_id} — ${amount}</span>
      </div>
      <div class="report-detail-section">
        <label>Opened</label>
        <span>${(d.opened_at||'').substring(0,16)}</span>
      </div>
      ${d.resolved_at ? `
      <div class="report-detail-section">
        <label>Resolved</label>
        <span>${d.resolved_at.substring(0,16)}</span>
      </div>` : ''}
      ${d.stripe_payment_intent_id ? `
      <div class="report-detail-section">
        <label>Stripe PI</label>
        <code style="font-size:11px;">${escapeHtml(d.stripe_payment_intent_id)}</code>
      </div>` : ''}
      ${d.refund_amount ? `
      <div class="report-detail-section">
        <label>Refund Issued</label>
        <span>$${d.refund_amount.toFixed(2)}</span>
      </div>` : ''}
      <div class="report-detail-section full-width">
        <label>Buyer Description</label>
        <p class="report-comment-full">${escapeHtml(d.description || '—')}</p>
      </div>
      ${d.resolution_note ? `
      <div class="report-detail-section full-width">
        <label>Resolution Note</label>
        <p class="report-comment-full">${escapeHtml(d.resolution_note)}</p>
      </div>` : ''}
      ${snapshotHtml}
      ${evidenceHtml}
      ${timelineHtml}
    </div>`;

  // Footer action buttons
  if (footer) {
    let actionBtns = '';
    if (isActiveDispute(d.status)) {
      actionBtns = `
        <button class="btn-warning" onclick="openDisputeStatusModal(${d.id}, '${escapeHtml(d.status)}')">
          <i class="fa-solid fa-arrow-right-arrow-left"></i> Change Status
        </button>
        <button class="btn-primary" onclick="openDisputeResolveModal(${d.id})">
          <i class="fa-solid fa-gavel"></i> Resolve
        </button>`;
    }
    footer.innerHTML = `
      <button class="btn-outline" onclick="openDisputeNoteModal(${d.id})">
        <i class="fa-solid fa-note-sticky"></i> Add Note
      </button>
      ${actionBtns}
      <button class="btn-outline" onclick="closeAdminDisputeDetail()">Close</button>`;
  }
}

function closeAdminDisputeDetail() {
  const modal = document.getElementById('adminDisputeDetailModal');
  if (modal) modal.style.display = 'none';
  currentAdminDisputeId = null;
}

// ── Action Modal (status change + resolve) ────────────────────────────────────

function openDisputeStatusModal(disputeId, currentStatus) {
  currentAdminDisputeId = disputeId;
  const modal = document.getElementById('adminDisputeActionModal');
  if (!modal) return;

  document.getElementById('actionDisputeId').value = disputeId;
  document.getElementById('actionMode').value = 'status';
  document.getElementById('adminDisputeActionTitle').textContent = `Change Status — Dispute #${disputeId}`;
  document.getElementById('actionStatusGroup').style.display = 'block';
  document.getElementById('actionResolutionGroup').style.display = 'none';
  document.getElementById('actionNoteLabel').textContent = 'Note (optional)';
  document.getElementById('actionNoteHint').textContent = 'Added to the dispute timeline.';
  document.getElementById('actionNote').value = '';
  document.getElementById('adminDisputeActionError').textContent = '';
  document.getElementById('adminDisputeActionSubmitBtn').textContent = 'Change Status';

  // Filter status options to valid transitions
  const allowedTransitions = {
    open:               ['evidence_requested', 'under_review', 'escalated'],
    evidence_requested: ['open', 'under_review', 'escalated'],
    under_review:       ['evidence_requested', 'escalated'],
    escalated:          ['under_review', 'evidence_requested'],
  };
  const allowed = allowedTransitions[currentStatus] || [];
  const sel = document.getElementById('actionNewStatus');
  Array.from(sel.options).forEach(opt => {
    opt.disabled = !allowed.includes(opt.value);
  });
  // Select first enabled
  const first = Array.from(sel.options).find(o => !o.disabled);
  if (first) sel.value = first.value;

  modal.style.display = 'flex';
}

function openDisputeResolveModal(disputeId) {
  currentAdminDisputeId = disputeId;
  const modal = document.getElementById('adminDisputeActionModal');
  if (!modal) return;

  document.getElementById('actionDisputeId').value = disputeId;
  document.getElementById('actionMode').value = 'resolve';
  document.getElementById('adminDisputeActionTitle').textContent = `Resolve Dispute #${disputeId}`;
  document.getElementById('actionStatusGroup').style.display = 'none';
  document.getElementById('actionResolutionGroup').style.display = 'block';
  document.getElementById('actionNoteLabel').textContent = 'Resolution Note (required)';
  document.getElementById('actionNoteHint').textContent = 'Visible to buyer and seller in their notifications.';
  document.getElementById('actionNote').value = '';
  document.getElementById('adminDisputeActionError').textContent = '';
  document.getElementById('adminDisputeActionSubmitBtn').textContent = 'Resolve Dispute';
  document.getElementById('actionResolution').value = 'resolved_denied';

  modal.style.display = 'flex';
}

function closeAdminDisputeAction() {
  const modal = document.getElementById('adminDisputeActionModal');
  if (modal) modal.style.display = 'none';
}

function submitDisputeAction() {
  const disputeId = document.getElementById('actionDisputeId').value;
  const mode      = document.getElementById('actionMode').value;
  const note      = document.getElementById('actionNote').value.trim();
  const errEl     = document.getElementById('adminDisputeActionError');
  errEl.textContent = '';

  const btn = document.getElementById('adminDisputeActionSubmitBtn');
  btn.disabled = true;

  let url, body;
  if (mode === 'status') {
    const newStatus = document.getElementById('actionNewStatus').value;
    url  = `/admin/api/disputes/${disputeId}/status`;
    body = JSON.stringify({ new_status: newStatus, note: note || null });
  } else {
    const resolution = document.getElementById('actionResolution').value;
    if (!note) {
      errEl.textContent = 'A resolution note is required.';
      btn.disabled = false;
      return;
    }
    url  = `/admin/api/disputes/${disputeId}/resolve`;
    body = JSON.stringify({ resolution, note });
  }

  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  })
    .then(r => r.json())
    .then(data => {
      btn.disabled = false;
      if (!data.success) {
        errEl.textContent = data.error || 'Unknown error.';
        return;
      }
      closeAdminDisputeAction();
      closeAdminDisputeDetail();
      loadAdminDisputes();
      let msg = 'Dispute updated successfully.';
      if (data.refund_result) {
        if (data.refund_result.success === false && data.refund_result.warning) {
          msg = 'Dispute resolved. Warning: ' + data.refund_result.warning;
        } else if (data.refund_result.success && data.refund_result.refund_id) {
          msg = `Dispute resolved. Stripe refund issued: ${data.refund_result.refund_id}`;
        }
      }
      showToast(msg, 'success');
    })
    .catch(err => {
      btn.disabled = false;
      errEl.textContent = 'Request failed: ' + err.message;
    });
}

// ── Note Modal ────────────────────────────────────────────────────────────────

function openDisputeNoteModal(disputeId) {
  currentAdminDisputeId = disputeId;
  document.getElementById('noteDisputeId').value = disputeId;
  document.getElementById('noteText').value = '';
  document.getElementById('adminDisputeNoteError').textContent = '';
  document.getElementById('adminDisputeNoteModal').style.display = 'flex';
}

function closeAdminDisputeNoteModal() {
  document.getElementById('adminDisputeNoteModal').style.display = 'none';
}

function submitDisputeNote() {
  const disputeId = document.getElementById('noteDisputeId').value;
  const note      = document.getElementById('noteText').value.trim();
  const errEl     = document.getElementById('adminDisputeNoteError');
  errEl.textContent = '';

  if (!note) {
    errEl.textContent = 'Note cannot be empty.';
    return;
  }

  fetch(`/admin/api/disputes/${disputeId}/note`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note }),
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) {
        errEl.textContent = data.error || 'Unknown error.';
        return;
      }
      closeAdminDisputeNoteModal();
      showToast('Note saved.', 'success');
      // Refresh detail if open
      if (currentAdminDisputeId) viewAdminDisputeDetail(currentAdminDisputeId);
    })
    .catch(err => {
      errEl.textContent = 'Request failed: ' + err.message;
    });
}

// ── User Stats Modal (preserved from original) ────────────────────────────────

function viewUserStats(userId) {
  if (!userId) return;
  fetch(`/admin/api/user/${userId}/stats`)
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        renderUserStatsModal(data.user);
        document.getElementById('adminUserStatsModal').style.display = 'flex';
      } else {
        alert('Failed to load user stats.');
      }
    })
    .catch(() => alert('Failed to load user stats.'));
}

function renderUserStatsModal(user) {
  const bodyEl = document.getElementById('adminUserStatsBody');
  if (!bodyEl) return;
  const stats = user.stats;
  let statusBadges = '';
  if (user.is_admin)  statusBadges += '<span class="status-badge status-admin">Admin</span> ';
  if (user.is_banned) statusBadges += '<span class="status-badge status-banned">Banned</span> ';
  if (user.is_frozen) statusBadges += '<span class="status-badge status-frozen">Frozen</span> ';
  if (!statusBadges)  statusBadges  = '<span class="status-badge status-active">Active</span>';

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
      <div class="stat-box"><span class="stat-box-label">Reports Filed</span><span class="stat-box-value">${stats.reports_filed}</span></div>
      <div class="stat-box stat-box-warning"><span class="stat-box-label">Reports Received</span><span class="stat-box-value">${stats.reports_received}</span></div>
      <div class="stat-box"><span class="stat-box-label">Rating</span><span class="stat-box-value">${stats.rating_avg} <small>(${stats.rating_count})</small></span></div>
      <div class="stat-box"><span class="stat-box-label">Active Listings</span><span class="stat-box-value">${stats.active_listings}</span></div>
      <div class="stat-box"><span class="stat-box-label">Orders (Buyer)</span><span class="stat-box-value">${stats.orders_as_buyer}</span></div>
      <div class="stat-box"><span class="stat-box-label">Sales (Seller)</span><span class="stat-box-value">${stats.sales_as_seller}</span></div>
    </div>
    <div class="user-stats-meta"><span>Member since: ${user.created_at}</span></div>
    <div class="user-stats-actions">
      <button class="btn-outline" onclick="messageUser(${user.id}, '${escapeHtml(user.username)}')">
        <i class="fa-solid fa-message"></i> Message
      </button>
      <button class="btn-warning" onclick="freezeUser(${user.id}, ${user.is_frozen})">
        <i class="fa-solid fa-snowflake"></i> ${user.is_frozen ? 'Unfreeze' : 'Freeze'}
      </button>
    </div>`;
}

function closeUserStatsModal() {
  const m = document.getElementById('adminUserStatsModal');
  if (m) m.style.display = 'none';
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function showToast(message, type) {
  let container = document.getElementById('adminToastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'adminToastContainer';
    container.style.cssText = 'position:fixed;top:20px;right:20px;z-index:100000;';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  const bg = type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6';
  toast.style.cssText = `padding:12px 20px;background:${bg};color:white;border-radius:8px;margin-bottom:10px;box-shadow:0 4px 12px rgba(0,0,0,0.15);max-width:400px;`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function escapeHtml(text) {
  if (text == null) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

// ── Tab activation hook ───────────────────────────────────────────────────────

const _originalSwitchTabDisputes = window.switchTab;
window.switchTab = function(tabName) {
  _originalSwitchTabDisputes(tabName);
  if (tabName === 'disputes') loadAdminDisputes();
  else if (tabName === 'messages') { if (typeof loadAdminConversations === 'function') loadAdminConversations(); }
  else if (tabName === 'ledger') {
    if (typeof loadLedgerStats  === 'function') loadLedgerStats();
    if (typeof loadLedgerOrders === 'function') loadLedgerOrders();
  }
};

// ============================================
// LEDGER FUNCTIONS
// ============================================
