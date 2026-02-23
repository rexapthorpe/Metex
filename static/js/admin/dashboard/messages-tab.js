function loadAdminConversations() {
  const listEl = document.getElementById('adminMessagesList');
  const emptyEl = document.getElementById('adminMessagesEmpty');

  if (!listEl) return;

  // Show loading
  listEl.innerHTML = `
    <div class="admin-messages-loading">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Loading conversations...</span>
    </div>
  `;
  listEl.style.display = 'block';
  if (emptyEl) emptyEl.style.display = 'none';

  fetch('/admin/api/conversations')
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        renderAdminConversations(data.conversations);
      } else {
        listEl.innerHTML = '<p class="error-message">Failed to load conversations.</p>';
      }
    })
    .catch(err => {
      console.error('[Admin Messages] Error:', err);
      listEl.innerHTML = '<p class="error-message">Failed to load conversations.</p>';
    });
}

function renderAdminConversations(conversations) {
  const listEl = document.getElementById('adminMessagesList');
  const emptyEl = document.getElementById('adminMessagesEmpty');

  if (!listEl) return;

  if (!conversations || conversations.length === 0) {
    listEl.style.display = 'none';
    if (emptyEl) emptyEl.style.display = 'block';
    return;
  }

  listEl.style.display = 'flex';
  listEl.style.flexDirection = 'column';
  listEl.style.gap = '12px';
  if (emptyEl) emptyEl.style.display = 'none';

  let html = '';
  conversations.forEach(convo => {
    const formattedTime = formatMessageTime(convo.last_message_time);
    const unreadBadge = convo.unread_count > 0
      ? `<span class="admin-convo-unread">${convo.unread_count}</span>`
      : '';

    html += `
      <div class="admin-conversation-card ${convo.unread_count > 0 ? 'has-unread' : ''}" onclick="messageUser(${convo.other_user_id}, '${escapeHtml(convo.other_username)}')">
        <div class="admin-convo-avatar">${convo.other_username.charAt(0).toUpperCase()}</div>
        <div class="admin-convo-content">
          <div class="admin-convo-header">
            <span class="admin-convo-username">@${escapeHtml(convo.other_username)}</span>
            <span class="admin-convo-time">${formattedTime}</span>
          </div>
          <div class="admin-convo-preview">${escapeHtml(convo.last_message_content || 'No messages')}</div>
        </div>
        ${unreadBadge}
      </div>
    `;
  });

  listEl.innerHTML = html;
}

window.loadAdminConversations = loadAdminConversations;

