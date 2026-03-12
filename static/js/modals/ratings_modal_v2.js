(function(window) {
  'use strict';

  let ratingsModal;
  let counterparties = [];
  let currentIndex = 0;
  let currentOrderId;
  let selectedRating = 0;
  let currentItemData = {};

  const placeholderImage = window.PLACEHOLDER_IMAGE || '';
  const HINTS = ['', 'Terrible', 'Poor', 'Okay', 'Good', 'Excellent'];

  // ── Public entry point ──────────────────────────────────────────────────────

  function openRateModal(orderId, role, itemData) {
    currentOrderId = orderId;
    currentItemData = itemData || {};
    role = role || 'seller';

    // Buyers rating sellers → new endpoint with per-seller rating status.
    // Sellers rating buyers → existing message_buyers endpoint (now also
    // returns already_rated / existing_rating fields).
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
          id:              role === 'seller' ? item.seller_id : item.buyer_id,
          username:        item.username,
          image:           item.profile_image_url || placeholderImage,
          already_rated:   !!item.already_rated,
          existing_rating: item.existing_rating || null,
        }));

        // Start on first unrated, or first if all rated
        const firstUnrated = counterparties.findIndex(p => !p.already_rated);
        currentIndex = firstUnrated >= 0 ? firstUnrated : 0;

        renderProfile();
        ratingsModal.style.display = 'flex';
      })
      .catch(err => console.error('openRateModal error:', err));
  }

  window.openRateModal = openRateModal;

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function getInitials(username) {
    if (!username) return '??';
    return username.slice(0, 2).toUpperCase();
  }

  function buildReadOnlyStars(rating) {
    let html = '';
    for (let i = 1; i <= 5; i++) {
      html += `<i class="${i <= rating ? 'fa-solid' : 'fa-regular'} fa-star"></i>`;
    }
    return html;
  }

  // ── Profile rendering ────────────────────────────────────────────────────────

  function renderProfile() {
    if (!counterparties.length) return;
    const party = counterparties[currentIndex];
    const isRated = party.already_rated;

    // --- Avatar & username (always shown) ---
    const avatar = document.getElementById('rmAvatar');
    if (avatar) avatar.textContent = getInitials(party.username);

    const usernameEl = document.getElementById('ratingUsername');
    if (usernameEl) usernameEl.textContent = party.username || '';
    const handleEl = document.getElementById('rmHandle');
    if (handleEl) handleEl.textContent = party.username ? `@${party.username}` : '';

    // --- User card accent ---
    const userCard = document.getElementById('rmUserCard');
    if (userCard) userCard.classList.toggle('rm-user-card--rated', isRated);

    // --- Header text ---
    const titleEl  = ratingsModal.querySelector('.rm-title');
    const subtitleEl = ratingsModal.querySelector('.rm-subtitle');
    if (isRated) {
      if (titleEl)    titleEl.textContent    = 'Already Rated';
      if (subtitleEl) subtitleEl.textContent = 'You have already submitted a rating for this user.';
    } else {
      if (titleEl)    titleEl.textContent    = 'Leave a Rating';
      if (subtitleEl) subtitleEl.textContent = 'Share your experience with this transaction.';
    }

    // --- Item card ---
    const itemCard = document.getElementById('rmItemCard');
    if (itemCard && currentItemData.title) {
      itemCard.style.display = 'flex';
      const titleField = document.getElementById('rmItemTitle');
      if (titleField) titleField.textContent = currentItemData.title;
      const priceEl = document.getElementById('rmItemPrice');
      if (priceEl) priceEl.textContent = currentItemData.price || '';
      const dateField = document.getElementById('rmItemDateField');
      const dateEl    = document.getElementById('rmItemDate');
      if (dateField && dateEl && currentItemData.date) {
        dateField.style.display = 'flex';
        dateEl.textContent = currentItemData.date;
      } else if (dateField) {
        dateField.style.display = 'none';
      }
    } else if (itemCard) {
      itemCard.style.display = 'none';
    }

    // --- Nav arrows ---
    const leftArrow  = ratingsModal.querySelector('.nav-arrow.left');
    const rightArrow = ratingsModal.querySelector('.nav-arrow.right');
    if (leftArrow && rightArrow) {
      const show = counterparties.length > 1;
      leftArrow.style.display  = show ? '' : 'none';
      rightArrow.style.display = show ? '' : 'none';
    }

    // --- Hide the confirmation panel ---
    const confirmEl = document.getElementById('rmConfirm');
    if (confirmEl) confirmEl.style.display = 'none';

    if (isRated) {
      // ── Already-rated state ────────────────────────────────────────────────
      const divider      = ratingsModal.querySelector('.rm-divider');
      const form         = document.getElementById('ratingForm');
      const alreadyPanel = document.getElementById('rmAlreadyRated');

      if (divider) divider.style.display = 'none';
      if (form)    form.style.display    = 'none';
      if (alreadyPanel) alreadyPanel.style.display = '';

      // Show the star rating they gave
      const ratedStars = document.getElementById('rmRatedStars');
      if (ratedStars) ratedStars.innerHTML = buildReadOnlyStars(party.existing_rating || 0);

      const ratedHint = document.getElementById('rmRatedHint');
      if (ratedHint) ratedHint.textContent = HINTS[party.existing_rating] || '';

    } else {
      // ── Normal rating state ────────────────────────────────────────────────
      const divider      = ratingsModal.querySelector('.rm-divider');
      const form         = document.getElementById('ratingForm');
      const alreadyPanel = document.getElementById('rmAlreadyRated');

      if (divider) divider.style.display = '';
      if (form)    form.style.display    = '';
      if (alreadyPanel) alreadyPanel.style.display = 'none';

      // Set the ratee_id hidden field so the server knows who is being rated
      const rateeInput = document.getElementById('rateeIdInput');
      if (rateeInput) rateeInput.value = party.id;

      // Set form action
      if (form) form.action = `/rate/${currentOrderId}`;

      // Reset stars
      selectedRating = 0;
      highlightStars(0);
      const ratingInput = document.getElementById('ratingInput');
      if (ratingInput) ratingInput.value = 0;
      const comment = document.getElementById('rmComment');
      if (comment) comment.value = '';

      // Disable submit, add hint circle
      const submitBtn = form ? form.querySelector('.submit-btn') : null;
      if (submitBtn) submitBtn.disabled = true;

      const starsEl = document.getElementById('starContainer');
      if (starsEl) starsEl.classList.add('rm-no-rating');

      const hintEl = document.getElementById('rmStarsHint');
      if (hintEl) hintEl.textContent = 'Click a star to rate';
    }
  }

  function changeProfile(offset) {
    currentIndex = (currentIndex + offset + counterparties.length) % counterparties.length;
    renderProfile();
  }

  // ── Star interaction ─────────────────────────────────────────────────────────

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
    const submitBtn = document.querySelector('#ratingForm .submit-btn');
    if (submitBtn) submitBtn.disabled = false;
    const starsEl = document.getElementById('starContainer');
    if (starsEl) starsEl.classList.remove('rm-no-rating');
    const hintEl = document.getElementById('rmStarsHint');
    if (hintEl) hintEl.textContent = HINTS[selectedRating] || 'Click a star to rate';
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

  // ── Modal lifecycle ──────────────────────────────────────────────────────────

  function closeModal() {
    ratingsModal.style.display = 'none';

    // Restore all standard elements to default visibility
    const divider = ratingsModal.querySelector('.rm-divider');
    const form    = document.getElementById('ratingForm');
    if (divider) divider.style.display = '';
    if (form)    form.style.display    = '';

    // Hide special panels
    const confirmEl    = document.getElementById('rmConfirm');
    const alreadyPanel = document.getElementById('rmAlreadyRated');
    if (confirmEl)    confirmEl.style.display    = 'none';
    if (alreadyPanel) alreadyPanel.style.display = 'none';

    // Remove green accent from user card
    const userCard = document.getElementById('rmUserCard');
    if (userCard) userCard.classList.remove('rm-user-card--rated');
  }

  function showConfirmation() {
    // Mark current party as rated in local state
    if (counterparties[currentIndex]) {
      counterparties[currentIndex].already_rated   = true;
      counterparties[currentIndex].existing_rating = selectedRating;
    }

    // Hide body elements, show success panel
    const divider      = ratingsModal.querySelector('.rm-divider');
    const form         = document.getElementById('ratingForm');
    const itemCard     = document.getElementById('rmItemCard');
    const alreadyPanel = document.getElementById('rmAlreadyRated');
    const leftArrow    = ratingsModal.querySelector('.nav-arrow.left');
    const rightArrow   = ratingsModal.querySelector('.nav-arrow.right');

    if (divider)      divider.style.display      = 'none';
    if (form)         form.style.display          = 'none';
    if (itemCard)     itemCard.style.display      = 'none';
    if (alreadyPanel) alreadyPanel.style.display  = 'none';
    if (leftArrow)    leftArrow.style.display     = 'none';
    if (rightArrow)   rightArrow.style.display    = 'none';

    const confirmEl = document.getElementById('rmConfirm');
    if (confirmEl) confirmEl.style.display = 'flex';

    // Update the triggering Rate button in the DOM immediately
    if (currentOrderId) {
      document.querySelectorAll('button[onclick]').forEach(btn => {
        const oc = btn.getAttribute('onclick');
        if (oc && oc.includes(`openRateModal(${currentOrderId}`)) {
          btn.classList.add('order-quick-action--rated', 'sold-footer-btn--rated');
          const icon = btn.querySelector('i');
          if (icon) icon.className = 'fa-solid fa-star';
          btn.childNodes.forEach(n => {
            if (n.nodeType === 3) n.textContent = n.textContent.replace(/\bRate\b/, 'Rated');
          });
        }
      });
    }

    setTimeout(() => {
      // Find the next unrated party
      const nextIdx = counterparties.findIndex(p => !p.already_rated);
      if (nextIdx >= 0) {
        // There are more people to rate — advance automatically
        currentIndex = nextIdx;
        // Hide confirmation, restore modal state
        if (confirmEl) confirmEl.style.display = 'none';
        if (divider)   divider.style.display   = '';
        if (itemCard && currentItemData.title) itemCard.style.display = 'flex';
        renderProfile();
      } else {
        // All rated — close and reload
        closeModal();
        window.location.reload();
      }
    }, 1800);
  }

  // ── DOMContentLoaded wiring ──────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', () => {
    ratingsModal = document.getElementById('ratingsModal');
    if (!ratingsModal) return;

    ratingsModal.querySelector('.nav-arrow.left')
      .addEventListener('click', () => changeProfile(-1));
    ratingsModal.querySelector('.nav-arrow.right')
      .addEventListener('click', () => changeProfile(1));
    ratingsModal.querySelector('.rm-close').addEventListener('click', closeModal);

    // Cancel/Close button(s) — delegated so both form and already-rated panels work
    ratingsModal.addEventListener('click', e => {
      if (e.target.classList.contains('cancel-btn')) closeModal();
      if (e.target === ratingsModal) closeModal();
    });

    // Star events
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
        body: new FormData(this),
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          showConfirmation();
        } else {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fa-regular fa-star"></i> Submit Rating';
          }
          console.error('Rating error:', data.error);
        }
      })
      .catch(err => {
        console.error('Rating submission error:', err);
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<i class="fa-regular fa-star"></i> Submit Rating';
        }
      });
    });
  });

})(window);
