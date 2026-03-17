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

    const endpoint = role === 'seller'
      ? `/orders/api/${orderId}/rate_sellers`
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

  // ── Profile rendering ────────────────────────────────────────────────────────

  function renderProfile() {
    if (!counterparties.length) return;
    const party = counterparties[currentIndex];
    const isRated = party.already_rated;

    // --- Avatar & username ---
    const avatar = document.getElementById('rmAvatar');
    if (avatar) avatar.textContent = getInitials(party.username);

    const usernameEl = document.getElementById('ratingUsername');
    if (usernameEl) usernameEl.textContent = party.username || '';
    const handleEl = document.getElementById('rmHandle');
    if (handleEl) handleEl.textContent = party.username ? `@${party.username}` : '';

    // --- User card: green accent when already rated ---
    const userCard = document.getElementById('rmUserCard');
    if (userCard) userCard.classList.toggle('rm-user-card--rated', isRated);

    // --- Header text ---
    const titleEl   = ratingsModal.querySelector('.rm-title');
    const subtitleEl = ratingsModal.querySelector('.rm-subtitle');
    if (isRated) {
      if (titleEl)    titleEl.textContent    = 'Rating Submitted';
      if (subtitleEl) subtitleEl.textContent = 'You have already rated this user for this order.';
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

    // --- Hide confirmation panel + old already-rated panel ---
    const confirmEl    = document.getElementById('rmConfirm');
    const alreadyPanel = document.getElementById('rmAlreadyRated');
    if (confirmEl)    confirmEl.style.display    = 'none';
    if (alreadyPanel) alreadyPanel.style.display = 'none';

    // --- Always show divider and form; state is controlled below ---
    const divider = ratingsModal.querySelector('.rm-divider');
    const form    = document.getElementById('ratingForm');
    if (divider) divider.style.display = '';
    if (form)    form.style.display    = '';

    // Always set ratee_id and action (locked state still needs these for display)
    const rateeInput = document.getElementById('rateeIdInput');
    if (rateeInput) rateeInput.value = party.id;
    if (form) form.action = `/rate/${currentOrderId}`;

    const ratedIndicator = document.getElementById('rmRatedIndicator');
    const starsEl        = document.getElementById('starContainer');
    const hintEl         = document.getElementById('rmStarsHint');
    const submitBtn      = form ? form.querySelector('.submit-btn') : null;
    const ratingInput    = document.getElementById('ratingInput');

    if (isRated) {
      // ── Locked / validated state ─────────────────────────────────────────────

      // Show the "Rating Submitted" badge above the stars
      if (ratedIndicator) ratedIndicator.style.display = 'flex';

      // Stars: locked at the submitted rating value, non-interactive
      if (starsEl) {
        starsEl.classList.remove('rm-no-rating');
        starsEl.classList.add('rm-stars--locked');
      }
      highlightStars(party.existing_rating || 0);
      if (hintEl) hintEl.textContent = HINTS[party.existing_rating] || '';

      // Submit button: disabled, communicates finalized state
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-circle-check"></i> Rating Already Submitted';
        submitBtn.classList.add('rm-submit-btn--submitted');
      }

    } else {
      // ── Normal interactive state ─────────────────────────────────────────────

      // Hide rated indicator
      if (ratedIndicator) ratedIndicator.style.display = 'none';

      // Stars: reset to interactive
      selectedRating = 0;
      if (starsEl) {
        starsEl.classList.remove('rm-stars--locked');
        starsEl.classList.add('rm-no-rating');
      }
      highlightStars(0);
      if (ratingInput) ratingInput.value = 0;
      if (hintEl) hintEl.textContent = 'Click a star to rate';

      const comment = document.getElementById('rmComment');
      if (comment) comment.value = '';

      // Submit button: reset to default awaiting-star-selection state
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-regular fa-star"></i> Submit Rating';
        submitBtn.classList.remove('rm-submit-btn--submitted');
      }
    }
  }

  function changeProfile(offset) {
    currentIndex = (currentIndex + offset + counterparties.length) % counterparties.length;
    renderProfile();
  }

  // ── Star interaction ─────────────────────────────────────────────────────────

  function onStarHover(e) {
    // Ignore if stars are locked (already rated)
    const starsEl = document.getElementById('starContainer');
    if (starsEl && starsEl.classList.contains('rm-stars--locked')) return;
    const val = parseInt(e.currentTarget.querySelector('i').dataset.value, 10);
    highlightStars(val);
  }

  function onStarLeave() {
    const starsEl = document.getElementById('starContainer');
    if (starsEl && starsEl.classList.contains('rm-stars--locked')) return;
    highlightStars(selectedRating);
  }

  function onStarClick(e) {
    const starsEl = document.getElementById('starContainer');
    if (starsEl && starsEl.classList.contains('rm-stars--locked')) return;

    selectedRating = parseInt(e.currentTarget.querySelector('i').dataset.value, 10);
    document.getElementById('ratingInput').value = selectedRating;
    highlightStars(selectedRating);
    const submitBtn = document.querySelector('#ratingForm .submit-btn');
    if (submitBtn) submitBtn.disabled = false;
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
    window.animatedModalClose(ratingsModal, function() {
      ratingsModal.style.display = 'none';
    });

    // Restore standard elements
    const divider = ratingsModal.querySelector('.rm-divider');
    const form    = document.getElementById('ratingForm');
    if (divider) divider.style.display = '';
    if (form)    form.style.display    = '';

    // Hide all special panels
    const confirmEl      = document.getElementById('rmConfirm');
    const alreadyPanel   = document.getElementById('rmAlreadyRated');
    const ratedIndicator = document.getElementById('rmRatedIndicator');
    if (confirmEl)      confirmEl.style.display      = 'none';
    if (alreadyPanel)   alreadyPanel.style.display   = 'none';
    if (ratedIndicator) ratedIndicator.style.display = 'none';

    // Remove per-session state modifiers
    const userCard = document.getElementById('rmUserCard');
    if (userCard) userCard.classList.remove('rm-user-card--rated');

    const starsEl = document.getElementById('starContainer');
    if (starsEl) starsEl.classList.remove('rm-stars--locked');

    const submitBtn = document.querySelector('#ratingForm .submit-btn');
    if (submitBtn) submitBtn.classList.remove('rm-submit-btn--submitted');
  }

  function showConfirmation() {
    // Mark current party as rated in local state (persists across arrow navigation this session)
    if (counterparties[currentIndex]) {
      counterparties[currentIndex].already_rated   = true;
      counterparties[currentIndex].existing_rating = selectedRating;
    }

    // Hide body, show success panel
    const divider        = ratingsModal.querySelector('.rm-divider');
    const form           = document.getElementById('ratingForm');
    const itemCard       = document.getElementById('rmItemCard');
    const alreadyPanel   = document.getElementById('rmAlreadyRated');
    const ratedIndicator = document.getElementById('rmRatedIndicator');
    const leftArrow      = ratingsModal.querySelector('.nav-arrow.left');
    const rightArrow     = ratingsModal.querySelector('.nav-arrow.right');

    if (divider)        divider.style.display        = 'none';
    if (form)           form.style.display            = 'none';
    if (itemCard)       itemCard.style.display        = 'none';
    if (alreadyPanel)   alreadyPanel.style.display    = 'none';
    if (ratedIndicator) ratedIndicator.style.display  = 'none';
    if (leftArrow)      leftArrow.style.display       = 'none';
    if (rightArrow)     rightArrow.style.display      = 'none';

    const confirmEl = document.getElementById('rmConfirm');
    if (confirmEl) confirmEl.style.display = 'flex';

    // Update the triggering Rate button in the DOM immediately
    if (currentOrderId) {
      const ratedCount = counterparties.filter(p => p.already_rated).length;
      const totalCount = counterparties.length;

      document.querySelectorAll('button[onclick]').forEach(btn => {
        const oc = btn.getAttribute('onclick');
        if (!oc || !oc.includes(`openRateModal(${currentOrderId}`)) return;

        // Progress bar button (single or multi-seller) — update fill, label, and complete state
        const pct = totalCount > 0 ? Math.round(ratedCount / totalCount * 100) : 0;
        const allRated = ratedCount >= totalCount;

        const fill = btn.querySelector('.rating-progress-bar-fill');
        if (fill) fill.style.width = pct + '%';

        const label = btn.querySelector('.rating-progress-label');
        if (label) label.textContent = ratedCount + ' of ' + totalCount + ' rated';

        const top = btn.querySelector('.rating-progress-top');
        if (top) {
          const icon = top.querySelector('i');
          if (icon) icon.className = allRated ? 'fa-solid fa-star' : 'fa-regular fa-star';
          top.childNodes.forEach(n => {
            if (n.nodeType === 3 && n.textContent.trim()) {
              n.textContent = ' ' + (allRated ? 'Rated' : 'Rate');
            }
          });
        }

        btn.classList.toggle('order-rating-progress--complete', allRated);
      });
    }

    setTimeout(() => {
      const nextIdx = counterparties.findIndex(p => !p.already_rated);
      if (nextIdx >= 0) {
        // More people to rate — advance automatically
        currentIndex = nextIdx;
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

    // Cancel/Close buttons — delegated
    ratingsModal.addEventListener('click', e => {
      if (e.target.classList.contains('cancel-btn')) closeModal();
      if (e.target === ratingsModal) closeModal();
    });

    // Star events (each handler guards against locked state internally)
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

      // Safety guard: never submit for an already-rated counterparty
      if (counterparties[currentIndex] && counterparties[currentIndex].already_rated) return;

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
