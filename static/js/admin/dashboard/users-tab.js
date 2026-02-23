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
  fetch(`/admin/api/user/${userId}`)
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        renderUserDetails(data.user);
      } else {
        content.innerHTML = `<p class="error">Error: ${data.error}</p>`;
      }
    })
    .catch(error => {
      content.innerHTML = `<p class="error">Failed to load user details</p>`;
      console.error('Error:', error);
    });
}

function renderUserDetails(user) {
  const content = document.getElementById('userDetailContent');
  const stats = user.stats;

  const statusClass = user.status === 'banned' ? 'status-suspended' :
                      user.status === 'frozen' ? 'status-pending' : 'status-active';

  content.innerHTML = `
    <div class="user-detail-header">
      <div class="user-detail-avatar">${user.username[0].toUpperCase()}</div>
      <div class="user-detail-info">
        <h3>@${user.username}</h3>
        <p>${user.email}</p>
      </div>
      <div class="user-detail-status">
        <span class="status-badge ${statusClass}">${user.status}</span>
      </div>
    </div>

    <div class="user-stats-grid">
      <div class="user-stat-card">
        <div class="user-stat-label">Purchases</div>
        <div class="user-stat-value">${stats.purchases}</div>
      </div>
      <div class="user-stat-card">
        <div class="user-stat-label">Sales</div>
        <div class="user-stat-value">${stats.sales}</div>
      </div>
      <div class="user-stat-card">
        <div class="user-stat-label">Active Listings</div>
        <div class="user-stat-value">${stats.active_listings}</div>
      </div>
      <div class="user-stat-card">
        <div class="user-stat-label">Active Bids</div>
        <div class="user-stat-value">${stats.active_bids}</div>
      </div>
    </div>

    <div class="user-detail-section">
      <h4>Account Information</h4>
      <div class="user-info-row">
        <span class="user-info-label">User ID</span>
        <span class="user-info-value">#${user.id}</span>
      </div>
      <div class="user-info-row">
        <span class="user-info-label">Full Name</span>
        <span class="user-info-value">${user.first_name || ''} ${user.last_name || ''}</span>
      </div>
      <div class="user-info-row">
        <span class="user-info-label">Phone</span>
        <span class="user-info-value">${user.phone}</span>
      </div>
      <div class="user-info-row">
        <span class="user-info-label">Joined</span>
        <span class="user-info-value">${user.joined_date}</span>
      </div>
      <div class="user-info-row">
        <span class="user-info-label">Rating</span>
        <span class="user-info-value">${stats.rating > 0 ? stats.rating + '/5 (' + stats.rating_count + ' reviews)' : 'No ratings'}</span>
      </div>
    </div>

    <div class="modal-actions-full">
      <button class="modal-action-btn btn-message" onclick="messageUser(${user.id}, '${user.username}')">
        <i class="fa-solid fa-message"></i> Message User
      </button>
      <button class="modal-action-btn btn-freeze ${user.status === 'frozen' ? 'active' : ''}" onclick="freezeUser(${user.id}, ${user.status === 'frozen' ? 1 : 0})">
        <i class="fa-solid fa-snowflake"></i> ${user.status === 'frozen' ? 'Unfreeze Account' : 'Freeze Account'}
      </button>
      <button class="modal-action-btn btn-delete" onclick="deleteUser(${user.id}, '${user.username}')">
        <i class="fa-solid fa-trash"></i> Delete User
      </button>
    </div>
  `;
}

function messageUser(userId, username) {
  // Close user modal if open
  closeUserModal();

  // Store recipient info
  messageRecipientId = userId;
  messageRecipientUsername = username;

  // Update modal with recipient info
  document.getElementById('messageRecipient').textContent = `@${username}`;
  document.getElementById('messageContent').value = '';

  // Show loading state
  const messagesContainer = document.getElementById('adminConversationMessages');
  messagesContainer.innerHTML = `
    <div class="admin-messages-loading">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Loading messages...</span>
    </div>
  `;

  // Show message modal
  document.getElementById('messageModal').style.display = 'flex';

  // Load conversation history
  loadConversationHistory(userId);
}

function loadConversationHistory(userId) {
  const messagesContainer = document.getElementById('adminConversationMessages');

  fetch(`/admin/api/user/${userId}/messages`)
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        renderConversationMessages(data.messages, data.admin_id);
      } else {
        messagesContainer.innerHTML = `<p class="error-message">Failed to load messages.</p>`;
      }
    })
    .catch(error => {
      console.error('Error loading conversation:', error);
      messagesContainer.innerHTML = `<p class="error-message">Failed to load messages.</p>`;
    });
}

function renderConversationMessages(messages, adminId) {
  const messagesContainer = document.getElementById('adminConversationMessages');

  if (!messages || messages.length === 0) {
    messagesContainer.innerHTML = `
      <div class="admin-conversation-empty">
        <i class="fa-regular fa-comment"></i>
        <p>No messages yet. Start the conversation!</p>
      </div>
    `;
    return;
  }

  let html = '';
  messages.forEach(msg => {
    const isAdmin = msg.sender_id === adminId;
    const timestamp = formatMessageTime(msg.timestamp);

    html += `
      <div class="admin-message-bubble ${isAdmin ? 'admin-message-sent' : 'admin-message-received'}">
        <div class="admin-message-content">${escapeHtml(msg.content)}</div>
        <div class="admin-message-meta">
          <span class="admin-message-sender">${isAdmin ? 'You' : '@' + escapeHtml(msg.sender_username)}</span>
          <span class="admin-message-time">${timestamp}</span>
        </div>
      </div>
    `;
  });

  messagesContainer.innerHTML = html;

  // Scroll to bottom
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function formatMessageTime(timestamp) {
  if (!timestamp) return '';
  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;

    // If less than 24 hours, show time
    if (diff < 24 * 60 * 60 * 1000) {
      return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    }
    // If this year, show month/day
    if (date.getFullYear() === now.getFullYear()) {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
    // Otherwise show full date
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch (e) {
    return timestamp;
  }
}

function sendAdminMessage() {
  const content = document.getElementById('messageContent').value.trim();

  if (!content) {
    alert('Please enter a message');
    return;
  }

  // Disable button while sending
  const btn = document.getElementById('sendMessageBtn');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

  fetch(`/admin/api/user/${messageRecipientId}/message`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ message: content })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        // Clear input
        document.getElementById('messageContent').value = '';

        // Reload conversation to show new message
        loadConversationHistory(messageRecipientId);

        showToast('Message sent', 'success');
      } else {
        alert('Error: ' + data.error);
      }
    })
    .catch(error => {
      alert('Failed to send message');
      console.error('Error:', error);
    })
    .finally(() => {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-paper-plane"></i>';
    });
}

function closeMessageModal() {
  document.getElementById('messageModal').style.display = 'none';
  messageRecipientId = null;
  messageRecipientUsername = null;

  // Refresh conversations list if on Messages tab to update unread counts
  const messagesPanel = document.getElementById('panel-messages');
  if (messagesPanel && messagesPanel.classList.contains('active')) {
    loadAdminConversations();
  }
}

// ============================================
// ADMIN MESSAGES TAB FUNCTIONS
// ============================================

