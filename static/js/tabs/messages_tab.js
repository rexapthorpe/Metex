// static/js/tabs/messages_tab.js

// After sending a message elsewhere, this helper updates (or adds) a conversation tile
window.notifyNewMessage = function(orderId, participantId, username, lastMessage, timestamp) {
  const list = document.querySelector('.messages-tab .conversation-list');
  if (!list) return;

  let tile = list.querySelector(`.conversation-tile[data-user-id="${participantId}"]`);
  if (tile) {
    // update existing tile
    tile.querySelector('.last-message').textContent = lastMessage;
    tile.querySelector('.timestamp').textContent = timestamp;
    tile.querySelector('.unread-dot').classList.remove('hidden');
  } else {
    // create a new tile
    tile = document.createElement('div');
    tile.className = 'conversation-tile collapsed';
    tile.dataset.userId  = participantId;
    tile.dataset.orderId = orderId;
    tile.innerHTML = `
      <div class="tile-header">
        <div class="unread-dot"></div>
        <div class="username">${username}</div>
        <div class="last-message">${lastMessage}</div>
        <div class="timestamp">${timestamp}</div>
        <i class="arrow-icon fa fa-chevron-left"></i>
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

    // bind click on the new header
    bindTileHeader(tile);
    bindTileForm(tile);
  }
};

function bindTileHeader(tile) {
  const header = tile.querySelector('.tile-header');
  header.addEventListener('click', () => {
    const orderId = tile.dataset.orderId;
    // read the type straight from the DOM
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
  });
}


// Binds form submit for inline messaging in the messages tab
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
        // append to history
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

        // notify main modal
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

// On DOM ready, bind existing tiles
document.addEventListener('DOMContentLoaded', () => {
  const tiles = document.querySelectorAll('.messages-tab .conversation-tile');
  tiles.forEach(tile => {
    bindTileHeader(tile);
    bindTileForm(tile);
  });
});
