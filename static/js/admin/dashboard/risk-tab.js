/**
 * Admin User Risk Tab (Phase 4)
 * ================================
 * Handles the user risk profile monitoring workflow:
 *  - List view with filters (flag, score threshold, username)
 *  - "Repeat Offenders" preset filter
 *  - Detail modal (profile stats, event history, admin controls)
 *  - Set flag / Clear flag / Update note actions
 *  - Force recompute button
 */

// ── State ────────────────────────────────────────────────────────────────────
let riskProfilesData = [];
let currentRiskUserId = null;

// ── Constants ─────────────────────────────────────────────────────────────────

const RISK_FLAG_LABELS = {
  none:       'None',
  watch:      'Watch',
  restricted: 'Restricted',
  suspended:  'Suspended',
};

const RISK_EVENT_LABELS = {
  score_updated:  'Score Updated',
  auto_flagged:   'Auto-Flagged',
  manual_flagged: 'Manual Flag',
  flag_cleared:   'Flag Cleared',
};

const RISK_EVENT_ICONS = {
  score_updated:  'fa-arrow-up-right-dots',
  auto_flagged:   'fa-robot',
  manual_flagged: 'fa-flag',
  flag_cleared:   'fa-circle-check',
};

function riskFlagLabel(f) { return RISK_FLAG_LABELS[f] || (f || 'none'); }
function riskEventLabel(t) { return RISK_EVENT_LABELS[t] || (t || '').replace(/_/g, ' '); }

function riskFlagBadgeHtml(flag) {
  const cls = `risk-flag-${flag || 'none'}`;
  const label = riskFlagLabel(flag);
  return `<span class="risk-flag-badge ${cls}">${escapeHtml(label)}</span>`;
}

function riskScoreHtml(score) {
  const s = score || 0;
  const pct = Math.min(100, s);
  const colorClass = s >= 40 ? 'score-high' : s >= 20 ? 'score-medium' : 'score-low';
  return `
    <div class="risk-score-bar">
      <div class="risk-score-bar-track">
        <div class="risk-score-bar-fill ${colorClass}" style="width:${pct}%"></div>
      </div>
      <span class="risk-score-value">${s}</span>
    </div>`;
}

// ── Load list ─────────────────────────────────────────────────────────────────

function loadRiskProfiles() {
  const flag     = document.getElementById('riskFilterFlag').value.trim();
  const scoreMin = document.getElementById('riskFilterScoreMin').value.trim();
  const username = document.getElementById('riskFilterUsername').value.trim();

  const params = new URLSearchParams();
  if (flag)     params.set('flag', flag);
  if (scoreMin) params.set('score_min', scoreMin);
  if (username) params.set('username', username);

  document.getElementById('adminRiskList').innerHTML = `
    <div class="dispute-loading">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Loading risk profiles...</span>
    </div>`;
  document.getElementById('adminRiskEmpty').style.display = 'none';

  fetch('/admin/api/risk?' + params.toString())
    .then(r => r.json())
    .then(data => {
      if (!data.success) { showRiskError(data.error || 'Failed to load'); return; }
      riskProfilesData = data.profiles || [];
      updateRiskStats(riskProfilesData);
      renderRiskList(riskProfilesData);
    })
    .catch(err => showRiskError('Network error: ' + err));
}

function loadRepeatOffenders() {
  // Pre-fill filters: flag != none OR score >= 40
  // Simplest approach: clear flag filter and set score_min=40,
  // then also load all flagged users separately and merge.
  // For simplicity: show flag=watch+restricted+suspended as separate loads,
  // but since our API doesn't support OR, we use score_min=1 to show all
  // with non-trivial score, then filter client-side for label.
  // Actually: just clear filters and set score_min=20 as a reasonable threshold.

  document.getElementById('riskFilterFlag').value = '';
  document.getElementById('riskFilterScoreMin').value = '20';
  document.getElementById('riskFilterUsername').value = '';
  loadRiskProfiles();
}

function updateRiskStats(profiles) {
  const flagged   = profiles.filter(p => p.manual_risk_flag && p.manual_risk_flag !== 'none').length;
  const highScore = profiles.filter(p => (p.risk_score || 0) >= 40).length;
  const total     = profiles.length;

  document.getElementById('riskStatsFlagged').textContent   = flagged;
  document.getElementById('riskStatsHighScore').textContent = highScore;
  document.getElementById('riskStatsTotal').textContent     = total;
}

function showRiskError(msg) {
  document.getElementById('adminRiskList').innerHTML = `
    <p style="color:#ef4444;padding:16px;">${escapeHtml(msg)}</p>`;
}

// ── Render list ───────────────────────────────────────────────────────────────

function renderRiskList(profiles) {
  const listEl  = document.getElementById('adminRiskList');
  const emptyEl = document.getElementById('adminRiskEmpty');

  if (!profiles.length) {
    listEl.innerHTML = '';
    emptyEl.style.display = '';
    return;
  }
  emptyEl.style.display = 'none';

  const rows = profiles.map(p => {
    const roleLabel = buildRoleLabel(p);
    return `
      <tr>
        <td>${escapeHtml(String(p.user_id))}</td>
        <td><strong>${escapeHtml(p.username || '—')}</strong></td>
        <td style="font-size:12px;color:#6b7280;">${escapeHtml(roleLabel)}</td>
        <td>${riskScoreHtml(p.risk_score)}</td>
        <td>${riskFlagBadgeHtml(p.manual_risk_flag)}</td>
        <td style="text-align:center;">${p.total_disputes_as_buyer || 0}</td>
        <td style="text-align:center;">${p.total_disputes_as_seller || 0}</td>
        <td>$${((p.refunds_issued_amount || 0)).toFixed(2)} (${p.refunds_issued_count || 0})</td>
        <td style="font-size:12px;color:#6b7280;">${formatDate(p.account_created_at)}</td>
        <td>
          <button class="action-icon" onclick="viewRiskDetail(${p.user_id})" title="View detail">
            <i class="fa-solid fa-eye"></i>
          </button>
        </td>
      </tr>`;
  }).join('');

  listEl.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Username</th>
          <th>Role</th>
          <th>Risk Score</th>
          <th>Flag</th>
          <th>Buyer Disputes</th>
          <th>Seller Disputes</th>
          <th>Refunds</th>
          <th>Joined</th>
          <th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function buildRoleLabel(p) {
  const buyer  = (p.total_orders_bought  || 0) > 0;
  const seller = (p.total_orders_sold    || 0) > 0;
  if (buyer && seller) return 'Buyer + Seller';
  if (seller)          return 'Seller';
  if (buyer)           return 'Buyer';
  return '—';
}

function formatDate(s) {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleDateString('en-US', { year:'numeric', month:'short', day:'numeric' });
  } catch(_) { return s; }
}

function formatDateTime(s) {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString('en-US', {
      year:'numeric', month:'short', day:'numeric',
      hour:'2-digit', minute:'2-digit',
    });
  } catch(_) { return s; }
}

// ── Detail modal ──────────────────────────────────────────────────────────────

function viewRiskDetail(userId) {
  currentRiskUserId = userId;
  const modal = document.getElementById('adminRiskDetailModal');
  const body  = document.getElementById('adminRiskDetailBody');
  const title = document.getElementById('adminRiskDetailTitle');
  title.innerHTML = '<i class="fa-solid fa-shield-halved"></i> Loading...';
  body.innerHTML  = '<div class="modal-loading"><i class="fa-solid fa-spinner fa-spin fa-lg"></i><span>Loading profile...</span></div>';
  modal.style.display = 'flex';

  fetch(`/admin/api/risk/${userId}`)
    .then(r => r.json())
    .then(data => {
      if (!data.success) {
        body.innerHTML = `<p style="color:#ef4444">${escapeHtml(data.error || 'Error loading profile')}</p>`;
        return;
      }
      title.innerHTML = `<i class="fa-solid fa-shield-halved"></i> Risk Profile — ${escapeHtml(data.profile.username || String(userId))}`;
      body.innerHTML = renderRiskDetailBody(data.profile, data.events || []);
    })
    .catch(err => {
      body.innerHTML = `<p style="color:#ef4444">Network error: ${escapeHtml(String(err))}</p>`;
    });
}

function renderRiskDetailBody(profile, events) {
  const flag = profile.manual_risk_flag || 'none';

  const statsHtml = `
    <div class="risk-detail-grid">
      <div class="risk-detail-card">
        <h4>Risk Summary</h4>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Risk Score</span>
          <span class="risk-stat-value">${riskScoreHtml(profile.risk_score)}</span>
        </div>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Manual Flag</span>
          <span class="risk-stat-value">${riskFlagBadgeHtml(flag)}</span>
        </div>
        ${flag !== 'none' ? `
        <div class="risk-stat-row">
          <span class="risk-stat-label">Reason</span>
          <span class="risk-stat-value" style="font-size:12px;max-width:180px;text-align:right;">${escapeHtml(profile.manual_flag_reason || '—')}</span>
        </div>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Flagged At</span>
          <span class="risk-stat-value" style="font-size:12px;">${formatDateTime(profile.manual_flagged_at)}</span>
        </div>` : ''}
        <div class="risk-stat-row">
          <span class="risk-stat-label">Account Status</span>
          <span class="risk-stat-value">
            ${profile.is_banned ? '<span class="status-badge status-banned">Banned</span>' :
              profile.is_frozen ? '<span class="status-badge status-frozen">Frozen</span>' :
              '<span class="status-badge status-active">Active</span>'}
          </span>
        </div>
      </div>

      <div class="risk-detail-card">
        <h4>Account Info</h4>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Username</span>
          <span class="risk-stat-value">${escapeHtml(profile.username || '—')}</span>
        </div>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Email</span>
          <span class="risk-stat-value" style="font-size:12px;">${escapeHtml(profile.email || '—')}</span>
        </div>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Joined</span>
          <span class="risk-stat-value" style="font-size:12px;">${formatDate(profile.account_created_at)}</span>
        </div>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Last Login</span>
          <span class="risk-stat-value" style="font-size:12px;">${formatDateTime(profile.last_login_at)}</span>
        </div>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Last Login IP</span>
          <span class="risk-stat-value" style="font-size:12px;">${escapeHtml(profile.last_login_ip || '—')}</span>
        </div>
      </div>

      <div class="risk-detail-card">
        <h4>Dispute Stats</h4>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Disputes as Buyer</span>
          <span class="risk-stat-value">${profile.total_disputes_as_buyer || 0}</span>
        </div>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Buyer Won</span>
          <span class="risk-stat-value" style="color:#16a34a;">${profile.disputes_upheld_buyer || 0}</span>
        </div>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Buyer Denied</span>
          <span class="risk-stat-value">${profile.disputes_denied_buyer || 0}</span>
        </div>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Disputes as Seller</span>
          <span class="risk-stat-value">${profile.total_disputes_as_seller || 0}</span>
        </div>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Upheld vs Seller</span>
          <span class="risk-stat-value" style="color:#dc2626;">${profile.disputes_upheld_against_seller || 0}</span>
        </div>
      </div>

      <div class="risk-detail-card">
        <h4>Order &amp; Refund Stats</h4>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Orders Bought</span>
          <span class="risk-stat-value">${profile.total_orders_bought || 0}</span>
        </div>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Orders Sold</span>
          <span class="risk-stat-value">${profile.total_orders_sold || 0}</span>
        </div>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Refunds Issued</span>
          <span class="risk-stat-value">${profile.refunds_issued_count || 0}</span>
        </div>
        <div class="risk-stat-row">
          <span class="risk-stat-label">Refund Total</span>
          <span class="risk-stat-value">$${((profile.refunds_issued_amount || 0)).toFixed(2)}</span>
        </div>
      </div>
    </div>`;

  // Admin notes
  const notesHtml = `
    <div class="risk-notes-section">
      <h4><i class="fa-solid fa-lock"></i> Admin Notes (internal only)</h4>
      <p id="riskCurrentNotes">${escapeHtml(profile.notes || 'No notes.')}</p>
    </div>`;

  // Event history
  const eventsHtml = events.length ? events.map(e => {
    const icon = RISK_EVENT_ICONS[e.event_type] || 'fa-circle';
    return `
      <div class="risk-event-item">
        <div class="risk-event-icon type-${e.event_type || 'unknown'}">
          <i class="fa-solid ${icon}"></i>
        </div>
        <div class="risk-event-content">
          <div class="risk-event-type">${escapeHtml(riskEventLabel(e.event_type))}</div>
          ${e.note ? `<div class="risk-event-note">${escapeHtml(e.note)}</div>` : ''}
          <div class="risk-event-meta">
            ${e.old_flag !== e.new_flag ? `Flag: ${escapeHtml(e.old_flag||'none')} → ${escapeHtml(e.new_flag||'none')} &nbsp;|&nbsp; ` : ''}
            ${e.old_score !== e.new_score ? `Score: ${e.old_score||0} → ${e.new_score||0} &nbsp;|&nbsp; ` : ''}
            by ${escapeHtml(e.triggered_by||'system')} &nbsp;·&nbsp; ${formatDateTime(e.created_at)}
          </div>
        </div>
      </div>`;
  }).join('') : '<p style="color:#6b7280;font-size:13px;padding:8px 0;">No events recorded yet.</p>';

  // Admin controls
  const userId = profile.user_id;
  const flagLabel = flag !== 'none' ? 'Change Flag' : 'Set Flag';
  const controlsHtml = `
    <div class="risk-admin-controls">
      <button class="admin-action-btn" onclick="openRiskFlagModal(${userId}, '${escapeHtml(flag)}')">
        <i class="fa-solid fa-flag"></i> ${flagLabel}
      </button>
      ${flag !== 'none' ? `
      <button class="admin-action-btn" onclick="doRiskClearFlag(${userId})">
        <i class="fa-solid fa-circle-xmark"></i> Clear Flag
      </button>` : ''}
      <button class="admin-action-btn" onclick="openRiskNoteModal(${userId}, ${JSON.stringify(profile.notes || '')})">
        <i class="fa-solid fa-note-sticky"></i> Edit Note
      </button>
      <button class="admin-action-btn" onclick="doRiskRecompute(${userId})" style="margin-left:auto;" title="Recompute risk score from live data">
        <i class="fa-solid fa-rotate"></i> Recompute
      </button>
    </div>`;

  return statsHtml + notesHtml + `
    <div style="margin-top:20px;">
      <h4 style="font-size:14px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;margin:0 0 12px 0;">
        Risk Event History
      </h4>
      <div class="risk-events-list">${eventsHtml}</div>
    </div>` + controlsHtml;
}

function closeRiskDetailModal() {
  document.getElementById('adminRiskDetailModal').style.display = 'none';
  currentRiskUserId = null;
}

// ── Flag modal ────────────────────────────────────────────────────────────────

function openRiskFlagModal(userId, currentFlag) {
  document.getElementById('riskFlagUserId').value = userId;
  document.getElementById('riskFlagReason').value = '';
  document.getElementById('riskFlagNote').value   = '';
  document.getElementById('adminRiskFlagError').textContent = '';
  // Pre-select next reasonable flag
  const sel = document.getElementById('riskFlagValue');
  sel.value = currentFlag === 'none' ? 'watch' : currentFlag;
  document.getElementById('adminRiskFlagModal').style.display = 'flex';
}

function closeRiskFlagModal() {
  document.getElementById('adminRiskFlagModal').style.display = 'none';
}

function submitRiskFlag() {
  const userId  = document.getElementById('riskFlagUserId').value;
  const flag    = document.getElementById('riskFlagValue').value;
  const reason  = document.getElementById('riskFlagReason').value.trim();
  const note    = document.getElementById('riskFlagNote').value.trim() || null;
  const errEl   = document.getElementById('adminRiskFlagError');
  errEl.textContent = '';

  if (!reason) { errEl.textContent = 'Reason is required.'; return; }

  fetch(`/admin/api/risk/${userId}/flag`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({flag, reason, note}),
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) { errEl.textContent = data.error || 'Error setting flag.'; return; }
      closeRiskFlagModal();
      showToast('Flag updated.');
      if (currentRiskUserId === parseInt(userId)) viewRiskDetail(parseInt(userId));
      loadRiskProfiles();
    })
    .catch(err => { errEl.textContent = 'Network error: ' + err; });
}

function doRiskClearFlag(userId) {
  if (!confirm('Clear the manual flag for this user?')) return;
  fetch(`/admin/api/risk/${userId}/flag/clear`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({}),
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) { alert(data.error || 'Error clearing flag.'); return; }
      showToast('Flag cleared.');
      if (currentRiskUserId === userId) viewRiskDetail(userId);
      loadRiskProfiles();
    })
    .catch(err => alert('Network error: ' + err));
}

// ── Note modal ────────────────────────────────────────────────────────────────

function openRiskNoteModal(userId, currentNote) {
  document.getElementById('riskNoteUserId').value   = userId;
  document.getElementById('riskNoteText').value     = currentNote || '';
  document.getElementById('adminRiskNoteError').textContent = '';
  document.getElementById('adminRiskNoteModal').style.display = 'flex';
}

function closeRiskNoteModal() {
  document.getElementById('adminRiskNoteModal').style.display = 'none';
}

function submitRiskNote() {
  const userId  = document.getElementById('riskNoteUserId').value;
  const note    = document.getElementById('riskNoteText').value.trim();
  const errEl   = document.getElementById('adminRiskNoteError');
  errEl.textContent = '';

  fetch(`/admin/api/risk/${userId}/note`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({note}),
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) { errEl.textContent = data.error || 'Error saving note.'; return; }
      closeRiskNoteModal();
      showToast('Note saved.');
      // Update the notes display in the detail modal if open
      const notesEl = document.getElementById('riskCurrentNotes');
      if (notesEl) notesEl.textContent = note || 'No notes.';
    })
    .catch(err => { errEl.textContent = 'Network error: ' + err; });
}

// ── Recompute ─────────────────────────────────────────────────────────────────

function doRiskRecompute(userId) {
  const btn = event && event.target ? event.target.closest('button') : null;
  if (btn) btn.disabled = true;

  fetch(`/admin/api/risk/${userId}/recompute`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({}),
  })
    .then(r => r.json())
    .then(data => {
      if (btn) btn.disabled = false;
      if (!data.success) { showToast('Recompute failed: ' + (data.error||'unknown')); return; }
      showToast('Score recomputed.');
      // Refresh detail modal
      if (currentRiskUserId === userId) viewRiskDetail(userId);
      loadRiskProfiles();
    })
    .catch(err => {
      if (btn) btn.disabled = false;
      showToast('Network error: ' + err);
    });
}

// ── Tab activation hook ───────────────────────────────────────────────────────

(function() {
  const _origSwitch = window.switchTab;
  window.switchTab = function(tab) {
    if (_origSwitch) _origSwitch(tab);
    if (tab === 'risk' && riskProfilesData.length === 0) {
      loadRiskProfiles();
    }
  };
})();
