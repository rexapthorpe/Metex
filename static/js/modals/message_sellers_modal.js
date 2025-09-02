// static/js/modals/message_sellers_modal.js

(function() {
  // Module-level state
  let participants = [];
  let currentIndex = 0;
  let currentOrderId = null;

  // Expose API for buttons
  window.openMessageModal = openMessageModal;
  window.closeMessageModal = closeMessageModal;

  function openMessageModal(orderId, type = 'seller') {
    currentOrderId = orderId;
    fetch(`/orders/api/${orderId}/message_${type}s`)
      .then(res => res.json())
      .then(data => {
        // 1) build participants
        participants = data.map(item => ({
          id:   item.seller_id ?? item.buyer_id,
          username: item.username
        }));

        // ← INSERT HERE: show/hide arrows based on participants.length
        const prev = document.getElementById('prevSeller');
        const next = document.getElementById('nextSeller');
        if (participants.length <= 1) {
          prev.style.display = 'none';
          next.style.display = 'none';
        } else {
          prev.style.display = 'flex';
          next.style.display = 'flex';
        }

        // 2) now reset index and render
        currentIndex = 0;
        renderConversation();

        // 3) finally display the modal
        document.getElementById('messageModal').style.display = 'flex';
      })
      .catch(err => console.error('Error loading participants:', err));
  }


  function closeMessageModal() {
    document.getElementById('messageModal').style.display = 'none';
  }

  function renderConversation() {
    // Clear input when switching participants
    const inputEl = document.getElementById('messageInput');
    if (inputEl) inputEl.value = '';

    const p = participants[currentIndex];
    document.getElementById('currentSellerLabel').textContent = `Message: ${p.username}`;
    document.getElementById('conversationIndicator').textContent = `(${currentIndex + 1} of ${participants.length})`;

    fetch(`/orders/api/${currentOrderId}/messages/${p.id}`)
      .then(res => res.json())
      .then(msgs => {
        const body = document.getElementById('messageBody');
        body.innerHTML = '';
        msgs.forEach(m => {
          const bubble = document.createElement('div');
          bubble.className = 'message-bubble ' +
            (m.sender_id === window.CURRENT_USER_ID ? 'user-message' : 'seller-message');
          bubble.innerHTML = `<p>${m.message_text}</p><span class="timestamp">${m.timestamp}</span>`;
          body.appendChild(bubble);
        });
      })
      .catch(err => console.error('Error loading messages:', err));
  }

  function sendMessage() {
    const input = document.getElementById('messageInput');
    const text = input.value.trim();
    if (!text) return;
    console.log('Sending message:', text);

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
       // notify the messages tab UI:
          const p = participants[currentIndex];
          const now = new Date().toLocaleString();
          if (typeof window.notifyNewMessage === 'function') {
            window.notifyNewMessage(
              currentOrderId,
              p.id,
              p.username,
              input.value.trim(),
              now
            );
          }
        } else {
          console.error('Send failed:', resp);
        }
      })
      .catch(err => console.error('Error sending message:', err));
  }

  // Bind UI handlers
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('prevSeller')?.addEventListener('click', () => {
      if (currentIndex > 0) currentIndex--;
      renderConversation();
    });

    document.getElementById('nextSeller')?.addEventListener('click', () => {
      if (currentIndex < participants.length - 1) currentIndex++;
      renderConversation();
    });

    document.getElementById('sendMessageBtn')?.addEventListener('click', sendMessage);

    // Close on outside click
    window.addEventListener('click', e => {
      if (e.target === document.getElementById('messageModal')) {
        closeMessageModal();
      }
    });
  });
})();
