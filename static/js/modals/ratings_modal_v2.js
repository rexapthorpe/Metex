(function(window) {
  'use strict';

  // Scoped variables to avoid conflicts
  let ratingsModal;
  let counterparties = [];
  let currentIndex = 0;
  let currentOrderId;
  let selectedRating = 0;

  // Placeholder for missing profile image, injected in HTML
  const placeholderImage = window.PLACEHOLDER_IMAGE || '';

  /**
   * Opens the rating modal for a given order and role.
   */
  function openRateModal(orderId, role = 'seller') {
    currentOrderId = orderId;
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

  // Expose globally
  window.openRateModal = openRateModal;

  /**
   * Renders the currently selected counterparty into the modal.
   */
  function renderProfile() {
    if (!counterparties.length) return;
    const party = counterparties[currentIndex];
    document.getElementById('ratingProfileImage').src = party.image;
    document.getElementById('ratingUsername').textContent = party.username;

    const form = document.getElementById('ratingForm');
    form.action = `/rate/${currentOrderId}`;

    // ── Show or hide arrows ───────────────────────────────────
    const leftArrow  = ratingsModal.querySelector('.nav-arrow.left');
    const rightArrow = ratingsModal.querySelector('.nav-arrow.right');
    if (counterparties.length <= 1) {
      leftArrow.style.display  = 'none';
      rightArrow.style.display = 'none';
    } else {
      leftArrow.style.display  = '';
      rightArrow.style.display = '';
    }

    // Reset rating widget and textarea
    selectedRating = 0;
    highlightStars(0);
    document.getElementById('ratingInput').value = 0;
    form.querySelector('textarea').value = '';
  }

  /**
   * Navigate between counterparties.
   */
  function changeProfile(offset) {
    currentIndex = (currentIndex + offset + counterparties.length) % counterparties.length;
    renderProfile();
  }

  function onStarHover(e) {
    highlightStars(parseInt(e.target.dataset.value, 10));
  }

  function onStarLeave() {
    highlightStars(selectedRating);
  }

  function onStarClick(e) {
    selectedRating = parseInt(e.target.dataset.value, 10);
    document.getElementById('ratingInput').value = selectedRating;
    highlightStars(selectedRating);
  }

    // enable Submit now that a star is chosen
    document.querySelector('#ratingForm .submit-btn').disabled = false;

  function highlightStars(count) {
    document.querySelectorAll('#starContainer i').forEach(star => {
      const val = parseInt(star.dataset.value, 10);
      star.classList.toggle('filled', val <= count);
    });
  }

  /**
   * Close the modal.
   */
  function closeModal() {
    ratingsModal.style.display = 'none';
  }

  // Initialize once DOM is ready
  document.addEventListener('DOMContentLoaded', () => {
    ratingsModal = document.getElementById('ratingsModal');
    if (!ratingsModal) return;

    ratingsModal.querySelector('.nav-arrow.left')
      .addEventListener('click', () => changeProfile(-1));
    ratingsModal.querySelector('.nav-arrow.right')
      .addEventListener('click', () => changeProfile(1));
    ratingsModal.querySelector('.close-btn').addEventListener('click', closeModal);
    ratingsModal.querySelector('.cancel-btn').addEventListener('click', closeModal);

    document.querySelectorAll('#starContainer i').forEach(star => {
      star.addEventListener('mouseenter', onStarHover);
      star.addEventListener('mouseleave', onStarLeave);
      star.addEventListener('click', onStarClick);
    });
  });

})(window);
