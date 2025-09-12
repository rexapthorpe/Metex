// static/js/bucket_ID_sellers_modal.js
document.addEventListener('DOMContentLoaded', () => {
  const modal    = document.getElementById('sellersModal');
  const openBtn  = document.getElementById('openSellersBtn');
  const closeBtn = document.getElementById('closeSellersBtn');
  const backdrop = modal ? modal.querySelector('.sellers-modal__backdrop') : null;

  if (!modal || !openBtn) {
    // Optional: quick debug aid — open DevTools Console to see this if needed
    // console.warn('Sellers modal: required elements not found.');
    return;
  }

  function openModal() {
    // Ensure visible even if something set inline display:none earlier
    modal.style.display = 'block';
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    setTimeout(() => { closeBtn && closeBtn.focus(); }, 0);
  }

  function closeModal() {
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    modal.style.display = 'none';
    if (openBtn) openBtn.focus();
  }

  openBtn.addEventListener('click', (e) => {
    e.preventDefault();
    openModal();
  });

  closeBtn && closeBtn.addEventListener('click', closeModal);
  backdrop && backdrop.addEventListener('click', closeModal);

  document.addEventListener('keydown', (e) => {
    if (!modal.classList.contains('is-open')) return;
    if (e.key === 'Escape') closeModal();
  });
});
