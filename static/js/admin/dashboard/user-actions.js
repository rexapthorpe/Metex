function freezeUser(userId, isFrozen) {
  pendingAction = { type: 'freeze', userId: userId, isFrozen: isFrozen };

  if (isFrozen) {
    // Unfreezing - use simple confirm modal
    document.getElementById('confirmModalTitle').textContent = 'Unfreeze Account';
    document.getElementById('confirmModalMessage').textContent =
      'Are you sure you want to unfreeze this account? The user will be able to buy, sell, and place bids again.';
    document.getElementById('confirmModalBtn').textContent = 'Unfreeze Account';
    document.getElementById('confirmModalBtn').className = 'btn-primary';
    document.getElementById('confirmModal').style.display = 'flex';
  } else {
    // Freezing - use freeze modal with reason input
    document.getElementById('freezeReason').value = '';
    document.getElementById('freezeReasonError').style.display = 'none';
    document.getElementById('freezeModal').style.display = 'flex';
  }
}

function closeFreezeModal() {
  // Reset success animation state
  const dialog = document.getElementById('freezeModalDialog');
  const successContent = document.getElementById('freezeSuccessContent');
  if (dialog) dialog.classList.remove('success');
  if (successContent) successContent.classList.remove('show');

  // Restore default heading (may have been changed for bulk mode)
  const heading = document.querySelector('#freezeModal .admin-modal-header h2');
  if (heading) {
    heading.innerHTML = '<i class="fa-solid fa-snowflake" style="color: #3b82f6;"></i> Freeze Account';
  }

  document.getElementById('freezeModal').style.display = 'none';
  document.getElementById('freezeReason').value = '';
  document.getElementById('freezeReasonError').style.display = 'none';
  pendingAction = null;
}

function confirmFreezeAction() {
  if (!pendingAction || (pendingAction.type !== 'freeze' && pendingAction.type !== 'bulk-freeze')) return;

  const reason = document.getElementById('freezeReason').value.trim();

  // Validate reason is provided
  if (!reason) {
    document.getElementById('freezeReasonError').style.display = 'block';
    document.getElementById('freezeReason').focus();
    return;
  }

  document.getElementById('freezeReasonError').style.display = 'none';

  const isBulk = pendingAction.type === 'bulk-freeze';
  const endpoint = isBulk
    ? '/admin/api/users/bulk-freeze'
    : `/admin/api/user/${pendingAction.userId}/freeze`;
  const body = isBulk
    ? JSON.stringify({ user_ids: pendingAction.userIds, action: 'freeze', reason: reason })
    : JSON.stringify({ action: 'freeze', reason: reason });

  const btn = document.getElementById('freezeModalBtn');
  const originalHTML = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Freezing...';

  // Capture bulk flag before clearing pendingAction
  const wasBulk = isBulk;
  pendingAction = null;

  fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body
  })
    .then(response => response.json())
    .then(data => {
      btn.disabled = false;
      btn.innerHTML = originalHTML;

      if (data.success) {
        showFreezeSuccessAnimation(data.message);
        if (wasBulk) clearBulkSelection();
      } else {
        closeFreezeModal();
        alert('Error: ' + data.error);
      }
    })
    .catch(error => {
      closeFreezeModal();
      btn.disabled = false;
      btn.innerHTML = originalHTML;
      alert('Failed to freeze account(s)');
      console.error('Error:', error);
    });
}

function showFreezeSuccessAnimation(message) {
  const dialog = document.getElementById('freezeModalDialog');
  const successContent = document.getElementById('freezeSuccessContent');
  const successMessage = document.getElementById('freezeSuccessMessage');

  // Update success message
  if (message) {
    successMessage.textContent = message;
  }

  // Show success animation
  dialog.classList.add('success');
  successContent.classList.add('show');
}

function closeFreezeModalAndRefresh() {
  // Reset modal state
  const dialog = document.getElementById('freezeModalDialog');
  const successContent = document.getElementById('freezeSuccessContent');

  dialog.classList.remove('success');
  successContent.classList.remove('show');

  // Close the modal
  document.getElementById('freezeModal').style.display = 'none';
  document.getElementById('freezeReason').value = '';
  document.getElementById('freezeReasonError').style.display = 'none';

  // Refresh the page
  location.reload();
}

function deleteUser(userId, username) {
  pendingAction = { type: 'delete', userId: userId, username: username };

  document.getElementById('confirmModalTitle').innerHTML = '<i class="fa-solid fa-triangle-exclamation" style="color: #dc2626;"></i> Permanently Delete User';
  document.getElementById('confirmModalMessage').innerHTML = `
    <p style="margin-bottom: 12px;"><strong>Are you absolutely sure you want to delete @${username}?</strong></p>
    <p style="color: #dc2626; margin-bottom: 12px;">This action is <strong>permanent and irreversible</strong>.</p>
    <p style="font-size: 0.9rem; color: #6b7280;">The following data will be permanently deleted:</p>
    <ul style="font-size: 0.85rem; color: #6b7280; margin-top: 8px; margin-left: 20px;">
      <li>All listings and photos</li>
      <li>All orders (as buyer)</li>
      <li>All bids</li>
      <li>All cart items</li>
      <li>All ratings (given and received)</li>
      <li>All messages</li>
      <li>All notifications</li>
      <li>All addresses</li>
    </ul>
  `;
  document.getElementById('confirmModalBtn').textContent = 'Delete Permanently';
  document.getElementById('confirmModalBtn').className = 'btn-danger';

  document.getElementById('confirmModal').style.display = 'flex';
}

function confirmAction() {
  if (!pendingAction) return;

  // Save action info before async operations (pendingAction will be cleared)
  const actionType = pendingAction.type;
  const actionUserId = pendingAction.userId;
  const actionUsername = pendingAction.username;

  let endpoint;
  let fetchOptions = { method: 'POST' };

  if (actionType === 'bulk-delete') {
    endpoint = '/admin/api/users/bulk-delete';
    fetchOptions.headers = { 'Content-Type': 'application/json' };
    fetchOptions.body = JSON.stringify({ user_ids: pendingAction.userIds });
  } else if (actionType === 'delete') {
    endpoint = `/admin/api/user/${actionUserId}/delete`;
  } else if (actionType === 'freeze') {
    endpoint = `/admin/api/user/${actionUserId}/freeze`;
    // For unfreezing (comes through confirm modal), send action: 'unfreeze'
    fetchOptions.headers = { 'Content-Type': 'application/json' };
    fetchOptions.body = JSON.stringify({ action: 'unfreeze' });
  }

  // Clear pendingAction immediately to prevent double-submits
  pendingAction = null;

  // Disable the button during request
  const btn = document.getElementById('confirmModalBtn');
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';

  fetch(endpoint, fetchOptions)
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return response.json();
    })
    .then(data => {
      btn.disabled = false;
      btn.textContent = originalText;

      if (data.success) {
        // For delete actions, show success animation
        if (actionType === 'bulk-delete') {
          clearBulkSelection();
          showConfirmSuccess('Users Deleted', data.message);
        } else if (actionType === 'delete') {
          closeUserModal();
          showConfirmSuccess(
            'User Deleted',
            `@${actionUsername} and all associated data have been permanently deleted.`
          );
        } else {
          // For other actions (ban/unban, freeze/unfreeze), use the simple flow
          closeConfirmModal();
          alert(data.message);
          // Refresh the user modal if still open
          if (document.getElementById('userDetailModal').style.display === 'flex') {
            viewUser(actionUserId);
          }
          // Refresh the page to update the table
          setTimeout(() => location.reload(), 500);
        }
      } else {
        closeConfirmModal();
        alert('Error: ' + (data.error || 'Unknown error occurred'));
      }
    })
    .catch(error => {
      closeConfirmModal();
      btn.disabled = false;
      btn.textContent = originalText;
      alert('Failed to perform action: ' + error.message);
      console.error('Error:', error);
    });
}

function showConfirmSuccess(title, message) {
  const dialog = document.getElementById('confirmModalDialog');
  const successContent = document.getElementById('confirmSuccessContent');
  const successTitle = document.getElementById('confirmSuccessTitle');
  const successMessage = document.getElementById('confirmSuccessMessage');

  // Update message
  successTitle.textContent = title;
  successMessage.textContent = message;

  // Show success animation
  dialog.classList.add('success');
  successContent.classList.add('show');
}

function closeConfirmModalAndRefresh() {
  closeConfirmModal();
  location.reload();
}

// ============================================
// BULK SELECTION
// ============================================

function toggleSelectAll(checkbox) {
  const table = document.querySelector('#panel-users .data-table tbody');
  if (!table) return;
  // Only toggle visible rows
  table.querySelectorAll('tr:not([style*="display: none"]) .user-select-cb').forEach(cb => {
    cb.checked = checkbox.checked;
  });
  updateBulkActionBar();
}

function updateBulkActionBar() {
  const checked = document.querySelectorAll('#panel-users .user-select-cb:checked');
  const bar = document.getElementById('bulkActionBar');
  const countEl = document.getElementById('bulkSelectedCount');
  if (checked.length > 0) {
    bar.classList.add('visible');
    countEl.textContent = checked.length;
  } else {
    bar.classList.remove('visible');
    const selectAll = document.getElementById('selectAllUsers');
    if (selectAll) selectAll.checked = false;
  }
}

function clearBulkSelection() {
  document.querySelectorAll('#panel-users .user-select-cb').forEach(cb => { cb.checked = false; });
  const selectAll = document.getElementById('selectAllUsers');
  if (selectAll) selectAll.checked = false;
  updateBulkActionBar();
}

function getSelectedUserIds() {
  return Array.from(
    document.querySelectorAll('#panel-users .user-select-cb:checked')
  ).map(cb => parseInt(cb.getAttribute('data-user-id')));
}

// ============================================
// BULK FREEZE / BULK DELETE TRIGGERS
// ============================================

function bulkFreezeUsers() {
  const ids = getSelectedUserIds();
  if (ids.length === 0) return;

  pendingAction = { type: 'bulk-freeze', userIds: ids };

  // Update freeze modal header to reflect bulk count
  const heading = document.querySelector('#freezeModal .admin-modal-header h2');
  if (heading) {
    heading.innerHTML = `<i class="fa-solid fa-snowflake" style="color: #3b82f6;"></i> Freeze ${ids.length} Account${ids.length !== 1 ? 's' : ''}`;
  }

  document.getElementById('freezeReason').value = '';
  document.getElementById('freezeReasonError').style.display = 'none';
  document.getElementById('freezeModal').style.display = 'flex';
}

function bulkDeleteUsers() {
  const ids = getSelectedUserIds();
  if (ids.length === 0) return;

  pendingAction = { type: 'bulk-delete', userIds: ids };

  const noun = `${ids.length} account${ids.length !== 1 ? 's' : ''}`;
  document.getElementById('confirmModalTitle').innerHTML =
    '<i class="fa-solid fa-triangle-exclamation" style="color: #dc2626;"></i> Permanently Delete Users';
  document.getElementById('confirmModalMessage').innerHTML = `
    <p style="margin-bottom: 12px;"><strong>Are you absolutely sure you want to permanently delete ${noun}?</strong></p>
    <p style="color: #dc2626; margin-bottom: 12px;">This action is <strong>permanent and irreversible</strong>.</p>
    <p style="font-size: 0.9rem; color: #6b7280;">All listings, orders, bids, messages, and account data for each selected user will be deleted.</p>
  `;
  document.getElementById('confirmModalBtn').textContent = `Delete ${noun} Permanently`;
  document.getElementById('confirmModalBtn').className = 'btn-danger';
  document.getElementById('confirmModal').style.display = 'flex';
}

// ============================================
// ORDER ACTIONS
// ============================================

