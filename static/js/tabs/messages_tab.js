// static/js/tabs/messages_tab.js

const READ_KEY = (orderId, participantId) => `msg_last_read:${orderId}:${participantId}`;

function parseTimestamp(tsText) {
  // Expect "YYYY-MM-DD HH:MM:SS" or ISO; normalize to ISO-ish
  if (!tsText) return 0;
  const isoish = tsText.trim().replace(' ', 'T');
  const t = Date.parse(isoish);
  return Number.isNaN(t) ? 0 : t;
}

function markThreadReadUI(tile) {
  const dot = tile.querySelector('.unread-dot');
  if (dot) dot.classList.add('hidden');
}

function markThreadReadPersist(orderId, participantId) {
  const now = Date.now();
  localStorage.setItem(READ_KEY(orderId, participantId), String(now));
  // best-effort server persist (creates/updates a small state row)
  fetch(`/orders/api/${orderId}/messages/${participantId}/read`, { method: 'POST' }).catch(() => {});
}

// After sending a message elsewhere, update (or add) a conversation tile
// OUTGOING messages from the current user → keep dot hidden.
window.notifyNewMessage = function(orderId, participantId, username, lastMessage, timestamp) {
  const list = document.querySelector('.messages-tab .conversation-list');
  if (!list) return;

  let tile = list.querySelector(`.conversation-tile[data-user-id="${participantId}"]`);
  if (tile) {
    tile.querySelector('.last-message').textContent = lastMessage;
    tile.querySelector('.timestamp').textContent = timestamp;
    markThreadReadUI(tile);
    markThreadReadPersist(orderId, participantId);
  } else {
    tile = document.createElement('div');
    tile.className = 'conversation-tile collapsed';
    tile.dataset.userId  = participantId;
    tile.dataset.orderId = orderId;
    tile.innerHTML = `
      <div class="tile-header">
        <div class="unread-dot hidden"></div>
        <div class="username">${username}</div>
        <div class="last-message">${lastMessage}</div>
        <div class="timestamp">${timestamp}</div>
      </div>
      <div class="message-body">
        <div class="message-history"></div>
        <form class="message-input-row" data-user-id="${participantId}" data-order-id="${orderId}">
          <input type="text" class="message-input" placeholder="Type a message…" />
          <button type="submit" class="send-button">Send</button>
        </form>
      </div>
    `;
    list.prepend(tile);
    bindTileHeader(tile);
    bindTileForm(tile);
  }
};

function bindTileHeader(tile) {
  const header = tile.querySelector('.tile-header');
  header.addEventListener('click', () => {
    const orderId = tile.dataset.orderId;
    const participantId = tile.dataset.userId;
    const conversationType = tile.dataset.type || 'seller';
    if (orderId) openMessageModal(orderId, conversationType);

    // collapse others
    document.querySelectorAll('.conversation-tile.expanded').forEach(other => {
      if (other !== tile) other.classList.remove('expanded');
    });

    // toggle this one
    tile.classList.toggle('expanded');
    if (tile.classList.contains('expanded')) {
      const history = tile.querySelector('.message-history');
      if (history) history.scrollTop = history.scrollHeight;
    }

    // Persist "read" now that the user has opened it
    markThreadReadUI(tile);
    markThreadReadPersist(orderId, participantId);
  });
}

function bindTileForm(tile) {
  const form = tile.querySelector('.message-input-row');
  form.addEventListener('submit', e => {
    e.preventDefault();
    const userId    = form.dataset.userId;
    const orderId   = form.dataset.orderId;
    const input     = form.querySelector('.message-input');
    const text      = input.value.trim();
    if (!text) return;

    fetch(`/orders/api/${orderId}/messages/${userId}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ message_text: text })
    })
    .then(r => r.json())
    .then(data => {
      if (data.status === 'sent') {
        const history = tile.querySelector('.message-history');
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message sent';
        msgDiv.innerHTML = `
          <div class="message-text">${text}</div>
          <div class="message-time">${new Date().toLocaleString()}</div>
        `;
        history.appendChild(msgDiv);
        history.scrollTop = history.scrollHeight;
        input.value = '';

        // Update header preview + mark as read (it's your outgoing)
        if (typeof notifyNewMessage === 'function') {
          notifyNewMessage(orderId, userId, tile.querySelector('.username').textContent, text, new Date().toLocaleString());
        }
      } else {
        alert(data.error || 'Failed to send.');
      }
    })
    .catch(() => alert('Network error.'));
  });
}

document.addEventListener('DOMContentLoaded', () => {
  // Bind existing tiles
  const tiles = document.querySelectorAll('.messages-tab .conversation-tile');
  tiles.forEach(tile => {
    bindTileHeader(tile);
    bindTileForm(tile);
  });

  // On load, reconcile dots with last_read timestamps
  tiles.forEach(tile => {
    const orderId = tile.dataset.orderId;
    const participantId = tile.dataset.userId;
    const lastRead = parseInt(localStorage.getItem(READ_KEY(orderId, participantId)) || '0', 10);
    if (!lastRead) return;

    const tsText = tile.querySelector('.timestamp')?.textContent || '';
    const latestTs = parseTimestamp(tsText);
    if (lastRead >= latestTs) {
      markThreadReadUI(tile); // hide dot if we've read since latest message
    }
  });
});
