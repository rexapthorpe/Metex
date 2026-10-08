/* Browser-local follow tools: no background messages or account-sync claims. */
(() => {
  const key = 'metex.marketplace.saved.v1';
  const status = document.querySelector('#lp-save-status');
  const cards = [...document.querySelectorAll('.lp-market-card')];
  if (!status) return;
  let state;
  try {
    state = JSON.parse(localStorage.getItem(key) || '{"products":{},"searches":[]}');
    if (!state || typeof state.products !== 'object' || !state.products || !Array.isArray(state.searches)) throw Error();
    localStorage.setItem(key, JSON.stringify(state));
  } catch (_) { status.textContent = 'Saving is unavailable in this browser. You can still browse and search.'; return; }
  const cents = value => {
    if (value === '' || value == null) return null;
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? Math.round(number * 100) : null;
  };
  function persist() {
    try { localStorage.setItem(key, JSON.stringify(state)); return true; }
    catch (_) { status.textContent = 'Could not save. Browser storage may be full or disabled.'; return false; }
  }
  function render() {
    cards.forEach(card => {
      const saved = state.products[card.dataset.bucket];
      const button = card.querySelector('.lp-save-product');
      button.textContent = saved ? 'Saved · remove' : 'Save product';
      button.setAttribute('aria-pressed', String(Boolean(saved)));
      const target = card.querySelector('.lp-target-price');
      target.parentElement.hidden = !saved;
      if (document.activeElement !== target) target.value = saved?.target ? (saved.target / 100).toFixed(2) : '';
    });
  }
  cards.forEach(card => {
    card.querySelector('.lp-follow-controls').hidden = false;
    const id = card.dataset.bucket;
    const price = cents(card.dataset.price);
    const previous = state.products[id];
    const notice = card.querySelector('.lp-price-notice');
    if (previous && price && previous.target && price <= previous.target) notice.textContent = 'Current offer meets your target price.';
    else if (previous && price && previous.price && price < previous.price) notice.textContent = `Offer down $${((previous.price - price) / 100).toFixed(2)} since your last visit.`;
    else if (previous && price && !previous.price) notice.textContent = 'A current offer is now available.';
    else if (previous && !price) notice.textContent = 'No current offer on this page.';
    if (previous) { previous.price = price; previous.title = card.dataset.title; }
    card.querySelector('.lp-save-product').addEventListener('click', () => {
      if (state.products[id]) { delete state.products[id]; notice.textContent = ''; }
      else { state.products[id] = {title:card.dataset.title,price,target:null}; }
      if (persist()) status.textContent = 'Saved on this browser. Price notices appear when you return; no email or background alerts.';
      render();
    });
    card.querySelector('.lp-target-price').addEventListener('change', event => {
      const target = cents(event.target.value);
      if (!state.products[id]) return;
      state.products[id].target = target;
      notice.textContent = target && price && price <= target ? 'Current offer meets your target price.' : '';
      if (persist()) status.textContent = target ? 'Target saved. Check back for current offers; checkout confirms the final price.' : 'Target cleared.';
    });
  });
  persist(); render();
})();
