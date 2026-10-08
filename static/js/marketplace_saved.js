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
  let onlySaved = false;
  const showSaved = document.querySelector('#lp-show-saved');
  const saveSearch = document.querySelector('#lp-save-search');
  const current = new URL(location.href);
  const search = current.searchParams.get('search') || '';
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
    document.querySelector('#lp-saved-count').textContent = Object.keys(state.products).length;
    showSaved.setAttribute('aria-pressed', String(onlySaved));
    cards.forEach(card => {
      const saved = state.products[card.dataset.bucket];
      card.hidden = onlySaved && !saved;
      const button = card.querySelector('.lp-save-product');
      button.textContent = saved ? 'Saved · remove' : 'Save product';
      button.setAttribute('aria-pressed', String(Boolean(saved)));
      const target = card.querySelector('.lp-target-price');
      target.parentElement.hidden = !saved;
      if (document.activeElement !== target) target.value = saved?.target ? (saved.target / 100).toFixed(2) : '';
    });
    if (onlySaved && !cards.some(card => !card.hidden)) status.textContent = 'No saved products match this page. View all bullion to find your saved items.';
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
  document.querySelector('.lp-saved-tools').hidden = false;
  saveSearch.hidden = !search;
  saveSearch.addEventListener('click', () => {
    const url = `${current.pathname}${current.search}#listings`;
    if (!state.searches.some(s => s.url === url)) state.searches.unshift({label:search,url});
    state.searches = state.searches.slice(0, 12);
    if (persist()) { renderSearches(); status.textContent = 'Search saved on this browser. Reopen it to check new listings.'; }
  });
  showSaved.addEventListener('click', () => { onlySaved = !onlySaved; status.textContent = ''; render(); });
  function renderSearches() {
    const box = document.querySelector('#lp-returning');
    box.replaceChildren();
    if (!state.searches.length) { box.hidden = true; return; }
    box.hidden = false;
    const label = document.createElement('strong'); label.textContent = 'Your saved searches'; box.append(label, document.createElement('br'));
    state.searches.forEach(saved => {
      if (!saved || typeof saved.url !== 'string') return;
      const url = new URL(saved.url, location.origin);
      if (url.origin !== location.origin || url.pathname !== '/buy') return;
      const link = document.createElement('a'); link.href = url.href; link.textContent = saved.label; box.append(link);
    });
    const clear = document.createElement('button'); clear.type = 'button'; clear.textContent = 'Clear saved searches';
    clear.addEventListener('click', () => { state.searches = []; persist(); renderSearches(); }); box.append(clear);
  }
  status.textContent = 'Saved on this browser. Check back for price and availability changes.';
  persist(); renderSearches(); render();
})();
