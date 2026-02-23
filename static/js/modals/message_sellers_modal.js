// static/js/modals/message_sellers_modal.js

(function() {
  // Module-level state
  let participants = [];
  let currentIndex = 0;
  let currentOrderId = null;

  // Expose API for buttons
  window.openMessageModal = openMessageModal;
  window.closeMessageModal = closeMessageModal;

  function getInitials(username) {
    const parts = username.split(/[\s_\-\.]+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return username.slice(0, 2).toUpperCase();
  }

  function formatOrderNumber(orderId) {
    return '#ORD-' + String(orderId).padStart(4, '0');
  }

  function openMessageModal(orderId, type = 'seller') {
    currentOrderId = orderId;
    fetch(`/orders/api/${orderId}/message_${type}s`)
      .then(res => res.json())
      .then(data => {
        // Build participants list
        participants = data.map(item => ({
          id: item.seller_id ?? item.buyer_id,
          username: item.username
        }));

        // Show/hide prev/next arrows based on participant count
        const prev = document.getElementById('prevSeller');
        const next = document.getElementById('nextSeller');
        if (participants.length <= 1) {
          prev.style.display = 'none';
          next.style.display = 'none';
        } else {
          prev.style.display = 'flex';
          next.style.display = 'flex';
        }

        // Populate order context bar
        const orderIdEl = document.getElementById('msgOrderId');
        if (orderIdEl) orderIdEl.textContent = formatOrderNumber(orderId);

        const viewBtn = document.getElementById('msgViewOrderBtn');
        if (viewBtn) {
          viewBtn.onclick = () => {
            window.location.href = '/account?tab=orders';
          };
        }

        // Reset and render
        currentIndex = 0;
        renderConversation();

        // Show modal
        document.getElementById('messageModal').style.display = 'flex';
      })
      .catch(err => console.error('Error loading participants:', err));
  }

  function closeMessageModal() {
    document.getElementById('messageModal').style.display = 'none';
  }

  function renderConversation() {
    // Clear input
    const inputEl = document.getElementById('messageInput');
    if (inputEl) { inputEl.value = ''; autoResizeTextarea(inputEl); }

    const p = participants[currentIndex];

    // Update header
    const initials = getInitials(p.username);
    const avatarEl = document.getElementById('msgAvatar');
    if (avatarEl) avatarEl.textContent = initials;

    const nameEl = document.getElementById('msgHeaderName');
    if (nameEl) nameEl.textContent = p.username;

    const handleEl = document.getElementById('msgHeaderHandle');
    if (handleEl) handleEl.textContent = '@' + p.username.toLowerCase().replace(/\s+/g, '');

    // Update multi-participant indicator
    const indicator = document.getElementById('conversationIndicator');
    if (indicator) {
      if (participants.length > 1) {
        indicator.textContent = `${currentIndex + 1} of ${participants.length}`;
        indicator.style.display = 'block';
      } else {
        indicator.style.display = 'none';
      }
    }

    // Load messages
    fetch(`/orders/api/${currentOrderId}/messages/${p.id}`)
      .then(res => res.json())
      .then(msgs => {
        const body = document.getElementById('messageBody');
        body.innerHTML = '';

        let lastDate = null;

        msgs.forEach(m => {
          const isSent = m.sender_id === window.CURRENT_USER_ID;

          // Date separator
          const msgDate = m.timestamp ? m.timestamp.split(' ')[0] : null;
          if (msgDate && msgDate !== lastDate) {
            const sep = document.createElement('div');
            sep.className = 'msg-date-separator';
            sep.innerHTML = `
              <div class="msg-date-separator-line"></div>
              <span class="msg-date-separator-text">${formatDate(m.timestamp)}</span>
              <div class="msg-date-separator-line"></div>
            `;
            body.appendChild(sep);
            lastDate = msgDate;
          }

          const bubble = document.createElement('div');
          bubble.className = 'message-bubble ' + (isSent ? 'user-message' : 'seller-message');

          const timeStr = formatTime(m.timestamp);

          if (isSent) {
            bubble.innerHTML = `
              <div class="msg-text">${escapeHtml(m.message_text)}</div>
              <div class="msg-meta sent">
                <span class="timestamp">${timeStr}</span>
                <span class="msg-checks">&#10003;&#10003;</span>
              </div>
            `;
          } else {
            bubble.innerHTML = `
              <div class="msg-text">${escapeHtml(m.message_text)}</div>
              <div class="msg-meta received">
                <span class="timestamp">${timeStr}</span>
              </div>
            `;
          }

          body.appendChild(bubble);
        });

        // Scroll to bottom
        body.scrollTop = body.scrollHeight;
      })
      .catch(err => console.error('Error loading messages:', err));
  }

  function sendMessage() {
    const input = document.getElementById('messageInput');
    const text = input.value.trim();
    if (!text) return;

    const p = participants[currentIndex];
    fetch(`/orders/api/${currentOrderId}/messages/${p.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message_text: text })
    })
      .then(res => res.json())
      .then(resp => {
        if (resp.status === 'sent') {
          renderConversation();
          const now = new Date().toLocaleString();
          if (typeof window.notifyNewMessage === 'function') {
            window.notifyNewMessage(currentOrderId, p.id, p.username, text, now);
          }
        } else {
          console.error('Send failed:', resp);
        }
      })
      .catch(err => console.error('Error sending message:', err));
  }

  // Format timestamp for display (time only: "02:30 PM")
  function formatTime(timestamp) {
    if (!timestamp) return '';
    try {
      const d = new Date(timestamp);
      if (isNaN(d)) return timestamp;
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch(e) { return timestamp; }
  }

  // Format timestamp for date separator ("Wednesday, Jan 7")
  function formatDate(timestamp) {
    if (!timestamp) return '';
    try {
      const d = new Date(timestamp);
      if (isNaN(d)) return '';
      return d.toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' });
    } catch(e) { return ''; }
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function autoResizeTextarea(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }

  // Bind UI handlers
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('prevSeller')?.addEventListener('click', () => {
      if (currentIndex > 0) { currentIndex--; renderConversation(); }
    });

    document.getElementById('nextSeller')?.addEventListener('click', () => {
      if (currentIndex < participants.length - 1) { currentIndex++; renderConversation(); }
    });

    document.getElementById('sendMessageBtn')?.addEventListener('click', sendMessage);

    // Enter to send, Shift+Enter for new line
    const textarea = document.getElementById('messageInput');
    if (textarea) {
      textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendMessage();
        }
      });
      textarea.addEventListener('input', () => autoResizeTextarea(textarea));
    }

    // Close on backdrop click
    window.addEventListener('click', e => {
      if (e.target === document.getElementById('messageModal')) {
        closeMessageModal();
      }
    });
  });
})();
