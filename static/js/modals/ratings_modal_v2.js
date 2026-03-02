(function(window) {
  'use strict';

  let ratingsModal;
  let counterparties = [];
  let currentIndex = 0;
  let currentOrderId;
  let selectedRating = 0;
  let currentItemData = {};

  const placeholderImage = window.PLACEHOLDER_IMAGE || '';

  function openRateModal(orderId, role, itemData) {
    currentOrderId = orderId;
    currentItemData = itemData || {};
    role = role || 'seller';

    const endpoint = role === 'seller'
      ? `/orders/api/${orderId}/order_sellers`
      : `/orders/api/${orderId}/message_buyers`;

    fetch(endpoint)
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch users');
        return res.json();
      })
      .then(data => {
        counterparties = data.map(item => ({
          id: role === 'seller' ? item.seller_id : item.buyer_id,
          username: item.username,
          image: item.profile_image_url || placeholderImage
        }));
        currentIndex = 0;
        renderProfile();
        ratingsModal.style.display = 'flex';
      })
      .catch(err => console.error('openRateModal error:', err));
  }

  window.openRateModal = openRateModal;

  function getInitials(username) {
    if (!username) return '??';
    return username.slice(0, 2).toUpperCase();
  }

  function renderProfile() {
    if (!counterparties.length) return;
    const party = counterparties[currentIndex];

    // Avatar initials
    const avatar = document.getElementById('rmAvatar');
    if (avatar) avatar.textContent = getInitials(party.username);

    // Username + handle
    const usernameEl = document.getElementById('ratingUsername');
    if (usernameEl) usernameEl.textContent = party.username || '';
    const handleEl = document.getElementById('rmHandle');
    if (handleEl) handleEl.textContent = party.username ? `@${party.username}` : '';

    // Item card
    const itemCard = document.getElementById('rmItemCard');
    if (itemCard && currentItemData.title) {
      itemCard.style.display = 'flex';
      const titleEl = document.getElementById('rmItemTitle');
      if (titleEl) titleEl.textContent = currentItemData.title;
      const priceEl = document.getElementById('rmItemPrice');
      if (priceEl) priceEl.textContent = currentItemData.price || '';
      const dateField = document.getElementById('rmItemDateField');
      const dateEl = document.getElementById('rmItemDate');
      if (dateField && dateEl && currentItemData.date) {
        dateField.style.display = 'flex';
        dateEl.textContent = currentItemData.date;
      } else if (dateField) {
        dateField.style.display = 'none';
      }
    } else if (itemCard) {
      itemCard.style.display = 'none';
    }

    // Form action
    const form = document.getElementById('ratingForm');
    if (form) form.action = `/rate/${currentOrderId}`;

    // Show/hide nav arrows
    const leftArrow  = ratingsModal.querySelector('.nav-arrow.left');
    const rightArrow = ratingsModal.querySelector('.nav-arrow.right');
    if (leftArrow && rightArrow) {
      const show = counterparties.length > 1;
      leftArrow.style.display  = show ? '' : 'none';
      rightArrow.style.display = show ? '' : 'none';
    }

    // Reset star rating
    selectedRating = 0;
    highlightStars(0);
    document.getElementById('ratingInput').value = 0;
    const comment = document.getElementById('rmComment');
    if (comment) comment.value = '';

    // Disable submit
    const submitBtn = document.querySelector('#ratingForm .submit-btn');
    if (submitBtn) submitBtn.disabled = true;

    // Add circle-hint class to stars
    const starsEl = document.getElementById('starContainer');
    if (starsEl) starsEl.classList.add('rm-no-rating');
  }

  function changeProfile(offset) {
    currentIndex = (currentIndex + offset + counterparties.length) % counterparties.length;
    renderProfile();
  }

  function onStarHover(e) {
    const val = parseInt(e.currentTarget.querySelector('i').dataset.value, 10);
    highlightStars(val);
  }

  function onStarLeave() {
    highlightStars(selectedRating);
  }

  function onStarClick(e) {
    selectedRating = parseInt(e.currentTarget.querySelector('i').dataset.value, 10);
    document.getElementById('ratingInput').value = selectedRating;
    highlightStars(selectedRating);
    // Enable submit
    const submitBtn = document.querySelector('#ratingForm .submit-btn');
    if (submitBtn) submitBtn.disabled = false;
    // Remove circle hint once a star is chosen
    const starsEl = document.getElementById('starContainer');
    if (starsEl) starsEl.classList.remove('rm-no-rating');
    // Update hint
    const hints = ['Terrible', 'Poor', 'Okay', 'Good', 'Excellent'];
    const hintEl = document.getElementById('rmStarsHint');
    if (hintEl) hintEl.textContent = hints[selectedRating - 1] || 'Click a star to rate';
  }

  function highlightStars(count) {
    document.querySelectorAll('#starContainer i').forEach(star => {
      const v = parseInt(star.dataset.value, 10);
      const filled = v <= count;
      star.classList.toggle('filled', filled);
      star.classList.toggle('fa-solid', filled);
      star.classList.toggle('fa-regular', !filled);
    });
  }

  function closeModal() {
    ratingsModal.style.display = 'none';
    // Restore elements hidden by showConfirmation so next open is fully populated
    ['.rm-user-card', '.rm-divider', '#ratingForm'].forEach(sel => {
      const el = ratingsModal.querySelector(sel);
      if (el) el.style.display = '';
    });
    const confirm = document.getElementById('rmConfirm');
    if (confirm) confirm.style.display = 'none';
  }

  function showConfirmation() {
    // Hide all body content
    ['.rm-user-card', '.rm-divider', '#ratingForm'].forEach(sel => {
      const el = ratingsModal.querySelector(sel);
      if (el) el.style.display = 'none';
    });
    const itemCard = document.getElementById('rmItemCard');
    if (itemCard) itemCard.style.display = 'none';

    // Show confirmation panel
    const confirm = document.getElementById('rmConfirm');
    if (confirm) confirm.style.display = 'flex';

    // Update triggering Rate button in the DOM immediately
    if (currentOrderId) {
      document.querySelectorAll('button[onclick]').forEach(btn => {
        if (btn.getAttribute('onclick') && btn.getAttribute('onclick').includes(`openRateModal(${currentOrderId}`)) {
          btn.classList.add('order-quick-action--rated', 'sold-footer-btn--rated');
          btn.disabled = true;
          btn.removeAttribute('onclick');
          const icon = btn.querySelector('i');
          if (icon) icon.className = 'fa-solid fa-star';
          btn.childNodes.forEach(n => { if (n.nodeType === 3) n.textContent = n.textContent.replace(/Rate\b/, 'Rated'); });
        }
      });
    }

    setTimeout(() => {
      closeModal();
      window.location.reload();
    }, 1800);
  }

  document.addEventListener('DOMContentLoaded', () => {
    ratingsModal = document.getElementById('ratingsModal');
    if (!ratingsModal) return;

    ratingsModal.querySelector('.nav-arrow.left')
      .addEventListener('click', () => changeProfile(-1));
    ratingsModal.querySelector('.nav-arrow.right')
      .addEventListener('click', () => changeProfile(1));
    ratingsModal.querySelector('.rm-close').addEventListener('click', closeModal);
    ratingsModal.querySelector('.rm-cancel-btn').addEventListener('click', closeModal);

    // Click outside to close
    ratingsModal.addEventListener('click', e => {
      if (e.target === ratingsModal) closeModal();
    });

    // Star events (on wrappers)
    document.querySelectorAll('#starContainer .rm-star-wrap').forEach(wrap => {
      wrap.addEventListener('mouseenter', onStarHover);
      wrap.addEventListener('mouseleave', onStarLeave);
      wrap.addEventListener('click', onStarClick);
    });

    // Intercept form submit → AJAX → confirmation animation
    const form = document.getElementById('ratingForm');
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      if (selectedRating === 0) return;

      const submitBtn = form.querySelector('.submit-btn');
      if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Submitting…'; }

      fetch(this.action, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: new FormData(this)
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          showConfirmation();
        } else {
          // Re-enable submit on error
          if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Submit Rating'; }
          console.error('Rating error:', data.error);
        }
      })
      .catch(err => {
        console.error('Rating submission error:', err);
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Submit Rating'; }
      });
    });
  });

})(window);
