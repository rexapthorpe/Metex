(function initSellersModal() {
  const modal = document.getElementById('sellersModal');
  const openBtn = document.getElementById('openSellersBtn');
  const closeBtn = document.getElementById('closeSellersBtn');
  const backdrop = modal ? modal.querySelector('.sellers-modal__backdrop') : null;

  if (!modal || !openBtn) return;

  function open() {
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    setTimeout(() => { closeBtn && closeBtn.focus(); }, 0);
  }
  function close() {
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    if (openBtn) openBtn.focus();
  }

  openBtn.addEventListener('click', open);
  closeBtn && closeBtn.addEventListener('click', close);
  backdrop && backdrop.addEventListener('click', close);
  document.addEventListener('keydown', (e) => {
    if (!modal.classList.contains('is-open')) return;
    if (e.key === 'Escape') close();
  });
})();
