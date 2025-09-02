// 1) Remove any existing modal(s) to avoid stacking
// 2) Fetch & inject the HTML, wire up toggle & submit
function openEditListingModal(listingId) {
  // remove prior modals
  document
    .querySelectorAll(`[id^="editListingModalWrapper-"]`)
    .forEach(el => el.remove());

  fetch(`/listings/edit_listing/${listingId}`, {
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
  .then(r => r.text())
  .then(html => {
    // inject
    const wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    document.body.appendChild(wrapper);

    // 3) Wire up the grading toggle
    toggleGradingService(listingId);
    const gradedSel = document.getElementById(`gradedSelect-${listingId}`);
    gradedSel.addEventListener('change', () => toggleGradingService(listingId));

    // 4) Handle submit via AJAX
    const form = document.getElementById(`editListingForm-${listingId}`);
    form.addEventListener('submit', e => {
      e.preventDefault();
      const data = new FormData(form);
      fetch(`/listings/edit_listing/${listingId}`, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: data
      })
      .then(resp => {
        if (resp.ok) return location.reload();
        throw new Error('Save failed');
      })
      .catch(err => {
        console.error(err);
        alert('Error saving listing.');
      });
    });
  });
}

function closeEditListingModal(listingId) {
  const wrapper = document.getElementById(`editListingModalWrapper-${listingId}`);
  if (wrapper) wrapper.remove();
}

function toggleGradingService(listingId) {
  const sel = document.getElementById(`gradedSelect-${listingId}`);
  const svc = document.getElementById(`gradingServiceContainer-${listingId}`);
  svc.style.display = sel.value === 'yes' ? 'block' : 'none';
}
