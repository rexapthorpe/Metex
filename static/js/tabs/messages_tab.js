// static/js/tabs/messages_tab.js

const READ_KEY = (orderId, participantId) => `msg_last_read:${orderId}:${participantId}`;

function parseTimestamp(tsText) {
  if (!tsText) return 0;
  const isoish = tsText.trim().replace(' ', 'T');
  const t = Date.parse(isoish);
  return Number.isNaN(t) ? 0 : t;
}

function markThreadReadUI(tile) {
  const dot = tile.querySelector('.unread-dot');
  if (dot) dot.classList.add('hidden');
  tile.dataset.hasUnread = '0';
}

function markThreadReadPersist(orderId, participantId, isAdmin) {
  const now = Date.now();
  localStorage.setItem(READ_KEY(orderId, participantId), String(now));
  if (isAdmin || parseInt(orderId) === 0) {
    fetch('/api/admin/messages/read', { method: 'POST' }).catch(() => {});
  } else {
    fetch(`/orders/api/${orderId}/messages/${participantId}/read`, { method: 'POST' }).catch(() => {});
  }
}

// After sending a message elsewhere, update (or add) a conversation tile
window.notifyNewMessage = function(orderId, participantId, username, lastMessage, timestamp) {
  const list = document.querySelector('.messages-tab .conversation-list');
  if (!list) return;

  let tile = list.querySelector(`.conversation-tile[data-user-id="${participantId}"]`);
  if (tile) {
    const lastEl = tile.querySelector('.last-message');
    const tsEl   = tile.querySelector('.timestamp');
    if (lastEl) lastEl.textContent = lastMessage;
    if (tsEl)   tsEl.textContent   = timestamp;
    markThreadReadUI(tile);
    markThreadReadPersist(orderId, participantId, false);
  }
};

function bindTileForm(tile) {
  const form = tile.querySelector('.message-input-row');
  if (!form) return;
  const isAdmin = form.dataset.isAdmin === 'true' || tile.dataset.type === 'admin';

  form.addEventListener('submit', e => {
    e.preventDefault();
    const userId  = form.dataset.userId;
    const orderId = form.dataset.orderId;
    const input   = form.querySelector('.message-input');
    const text    = input.value.trim();
    if (!text) return;

    const url = isAdmin
      ? '/api/admin/messages'
      : `/orders/api/${orderId}/messages/${userId}`;

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message_text: text })
    })
    .then(r => r.json())
    .then(data => {
      if (data.status === 'sent') {
        const history = tile.querySelector('.message-history');
        const msgDiv  = document.createElement('div');
        msgDiv.className = 'message sent';
        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        textDiv.textContent = text; // XSS-safe: textContent never interprets HTML
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = (function(d){const hh=String(d.getHours()).padStart(2,'0'),mm=String(d.getMinutes()).padStart(2,'0'),dd=String(d.getDate()).padStart(2,'0'),day=d.toLocaleDateString('en-US',{weekday:'long'}),mon=d.toLocaleDateString('en-US',{month:'long'}),y=d.getFullYear();return `${hh}:${mm}, ${dd}, ${day}, ${mon}, ${y}`;})(new Date());
        msgDiv.appendChild(textDiv);
        msgDiv.appendChild(timeDiv);
        history.appendChild(msgDiv);
        history.scrollTop = history.scrollHeight;
        input.value = '';
        // Update preview
        const lastEl = tile.querySelector('.last-message');
        if (lastEl) lastEl.textContent = text;
      } else {
        alert(data.error || 'Failed to send.');
      }
    })
    .catch(() => alert('Network error.'));
  });
}

// Parse "[Files: path, ...]" out of stored message text and render as inline images.
function renderMessageContent(el) {
  const raw = el.textContent || '';
  const fileMatch = raw.match(/\[Files:\s*([^\]]+)\]/);
  if (!fileMatch) return; // plain text, nothing to do

  let displayText = raw
    .replace(fileMatch[0], '')
    .replace(/\[\d+ attachment\(s\)\]/, '')
    .trim();

  const paths = fileMatch[1].split(',').map(p => p.trim());

  // Use textContent for safe display text, then append images via DOM (never innerHTML with user data)
  el.textContent = displayText;
  paths.forEach(path => {
    // Validate path is a relative static upload path before rendering
    const safePath = path.startsWith('/') ? path : '/' + path;
    if (!/^\/static\/uploads\/[a-zA-Z0-9_./-]+$/.test(safePath)) return;
    const img = document.createElement('img');
    img.className = 'msg-tab-image-attachment';
    img.src = safePath;
    img.alt = 'Image attachment';
    el.appendChild(img);
  });
}

function escapeHtmlBasic(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Clean up conversation preview: replace raw [Files: ...] with a tidy label.
function cleanConvoPreview(el) {
  const raw = el.textContent || '';
  if (!raw.includes('[Files:')) return;
  const textPart = raw
    .replace(/\[Files:[^\]]+\]/, '')
    .replace(/\[\d+ attachment\(s\)\]/, '')
    .trim();
  el.textContent = textPart ? `${textPart} · 📎 Image` : '📎 Image';
}

document.addEventListener('DOMContentLoaded', () => {
  const tiles = document.querySelectorAll('.messages-tab .conversation-tile');
  tiles.forEach(tile => {
    bindTileForm(tile);
  });

  // Render any server-side message content that includes image file paths.
  document.querySelectorAll('.messages-tab .message-text').forEach(renderMessageContent);
  document.querySelectorAll('.messages-tab .convo-preview').forEach(cleanConvoPreview);

  // On load, reconcile unread dots with localStorage timestamps
  tiles.forEach(tile => {
    const orderId = tile.dataset.orderId;
    const participantId = tile.dataset.userId;
    const lastRead = parseInt(localStorage.getItem(READ_KEY(orderId, participantId)) || '0', 10);
    if (!lastRead) return;
    const tsText = tile.querySelector('.timestamp')?.textContent || '';
    const latestTs = parseTimestamp(tsText);
    if (lastRead >= latestTs) {
      markThreadReadUI(tile);
    }
  });
});
