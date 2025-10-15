// static/js/modals/edit_bid_modal.js
'use strict';

// ---------- Modal open/close ----------
function openEditBidModal(bidId) {
  const modal = document.getElementById('editBidModal');
  const content = document.getElementById('editBidModalContent');
  if (!modal || !content) return console.error('Modal container missing');

  content.innerHTML = '';

  fetch(`/bids/edit_form/${bidId}`, { cache: 'no-store' })
    .then(resp => {
      if (!resp.ok) throw new Error(resp.statusText);
      return resp.text();
    })
    .then(html => {
      content.innerHTML = html;
      modal.style.display = 'flex';
      modal.classList.add('active');
      initEditBidForm();   // wire up handlers for the new single-box dropdown
    })
    .catch(err => {
      console.error('❌ Fetch error:', err);
      content.innerHTML = '<p class="error-msg">Error loading form. Please try again.</p>';
      modal.style.display = 'flex';
    });
}

function closeEditBidModal() {
  const modal = document.getElementById('editBidModal');
  const content = document.getElementById('editBidModalContent');
  if (modal) {
    modal.style.display = 'none';
    modal.classList.remove('active');
  }
  if (content) content.innerHTML = '';
  if (typeof showTab === 'function') showTab('bids');
}
window.openEditBidModal = openEditBidModal;
window.closeEditBidModal = closeEditBidModal;

// Close on overlay click
window.addEventListener('click', (e) => {
  const modal = document.getElementById('editBidModal');
  if (e.target === modal) closeEditBidModal();
});

// ---------- Form behavior ----------
function initEditBidForm() {
  const grid = document.getElementById('eb-grid');

  // Single-box grading dropdown pieces
  const grading       = document.getElementById('eb-grading');
  const box           = document.getElementById('eb-grading-box');
  const headerBtn     = document.getElementById('eb-grading-header');
  const chev          = document.getElementById('eb-grading-chev');
  const menu          = document.getElementById('eb-grading-menu');

  const requiresGrading = document.getElementById('requires_grading');
  const preferredHidden = document.getElementById('preferred_grader');

  // Switches
  const swAny  = document.getElementById('grader_any');
  const swPCGS = document.getElementById('grader_pcgs');
  const swNGC  = document.getElementById('grader_ngc');

  // Other fields
  const addressInput = document.getElementById('address-input');
  const addressHint  = document.getElementById('address-hint');
  const priceInput   = document.getElementById('bid-price-input');
  const priceHint    = document.getElementById('price-hint');
  const qtyInput     = document.getElementById('qty-input');
  const qtyHint      = document.getElementById('qty-hint');
  const confirmBtn   = document.getElementById('eb-confirm');
  const bestPill     = document.getElementById('best-bid-pill');

  // Toggle the dropdown — box EXPANDS, content remains inside the same rounded box
  headerBtn?.addEventListener('click', () => {
    const open = !grid.classList.contains('grading-open');
    grid.classList.toggle('grading-open', open);
    grading.setAttribute('aria-expanded', open ? 'true' : 'false');
    menu.setAttribute('aria-hidden', open ? 'false' : 'true');
    headerBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    chev.textContent = open ? '▴' : '▾';
  });

  function updatePrefAndFlags() {
    // exclusivity rules
    if (swAny.checked) {
      swPCGS.checked = false; swPCGS.disabled = true;
      swNGC.checked  = false; swNGC.disabled  = true;
      preferredHidden.value = 'Any';
    } else {
      swPCGS.disabled = false;
      swNGC.disabled  = false;
      if (swPCGS.checked && swNGC.checked) {
        // allow only one; prefer last change but default PCGS if both happen
        swNGC.checked = false;
      }
      if (swPCGS.checked) preferredHidden.value = 'PCGS';
      else if (swNGC.checked) preferredHidden.value = 'NGC';
      else preferredHidden.value = '';
    }

    const hasChoice = !!preferredHidden.value;
    requiresGrading.value = hasChoice ? 'yes' : 'no';

    // address required only if grading is on
    if (hasChoice) addressInput?.setAttribute('required','required');
    else addressInput?.removeAttribute('required');

    validateAll();
  }

  swAny?.addEventListener('change', updatePrefAndFlags);
  swPCGS?.addEventListener('change', updatePrefAndFlags);
  swNGC?.addEventListener('change', updatePrefAndFlags);
  updatePrefAndFlags(); // apply on load

  // Best pill -> fill price
  bestPill?.addEventListener('click', () => {
    const v = bestPill.getAttribute('data-price');
    if (v && priceInput) {
      priceInput.value = (+v).toFixed(2);
      validateAll();
    }
  });

  // Round to tick (0.01) on blur
  priceInput?.addEventListener('blur', () => {
    const n = Number(priceInput.value);
    if (!isFinite(n) || n <= 0) {
      priceHint.textContent = 'Enter a positive price.';
    } else {
      priceInput.value = (Math.round(n * 100) / 100).toFixed(2);
      priceHint.textContent = '';
    }
    validateAll();
  });

  qtyInput?.addEventListener('input', validateAll);
  addressInput?.addEventListener('input', validateAll);

  function validateAll() {
    // price
    const p = Number(priceInput?.value);
    const priceOk = isFinite(p) && p >= 0.01;
    priceHint.textContent = priceOk ? '' : 'Price must be at least $0.01';

    // qty
    const q = Number(qtyInput?.value);
    const qtyOk = Number.isInteger(q) && q >= 1;
    qtyHint.textContent = qtyOk ? '' : 'Quantity must be at least 1';

    // address (required if grading is on)
    const gradingOn = (requiresGrading.value === 'yes');
    const addrOk = !gradingOn || (addressInput && addressInput.value.trim().length > 0);
    if (!addrOk && gradingOn) addressHint.textContent = 'Address is required when grading is selected.';
    else addressHint.textContent = '';

    confirmBtn.disabled = !(priceOk && qtyOk && addrOk);
  }
  validateAll();

  // Intercept submission inside modal
  document.addEventListener('submit', function onSubmit(e) {
    const form = e.target;
    if (form.id !== 'bid-form' || !form.closest('#editBidModal')) return;
    e.preventDefault();

    // Ensure flags are consistent
    updatePrefAndFlags();
    validateAll();
    if (confirmBtn.disabled) return;

    // clear old errors
    document.querySelectorAll('.error-msg').forEach(el => el.remove());

    const formData = new FormData(form);
    fetch(form.action, { method: 'POST', body: formData })
      .then(res => res.json())
      .then(data => {
        if (!data.success) {
          if (data.errors) {
            Object.entries(data.errors).forEach(([name, msg]) => {
              const input = form.querySelector(`[name="${name}"]`);
              if (input) {
                const err = document.createElement('p');
                err.className = 'error-msg';
                err.textContent = msg;
                input.insertAdjacentElement('afterend', err);
              }
            });
          } else {
            alert(data.message || 'Something went wrong.');
          }
          return;
        }
        alert('✅ ' + data.message);
        closeEditBidModal();
        location.reload();
      })
      .catch(err => {
        console.error('Form submission failed:', err);
        alert('Server error occurred.');
      });
  }, { once: true });
}
