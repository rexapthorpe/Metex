function syncQuantity(targetId) {
  const selectedQty = document.getElementById("quantityInput")?.value || "1";
  const target = document.getElementById(targetId);
  if (target) target.value = selectedQty;
}

/* =========================
   GALLERY (square, arrows, thumbs) with placeholder support
   ========================= */
(function initGallery() {
  const arr = Array.isArray(window.bucketImages) ? window.bucketImages : [];
  const imgs = (arr && arr.length > 0) ? arr : [];
  const mainImg = document.getElementById("mainImage");
  const placeholder = document.getElementById("mainImagePlaceholder");
  const prev = document.getElementById("galPrev");
  const next = document.getElementById("galNext");
  const dotsWrap = document.getElementById("galDots");

  if (!imgs.length) {
    if (prev) prev.disabled = true;
    if (next) next.disabled = true;
    return;
  }

  let idx = 0;

  function render() {
    if (placeholder) placeholder.style.display = "none";
    if (mainImg) mainImg.src = imgs[idx] || imgs[0];

    if (dotsWrap) {
      dotsWrap.querySelectorAll(".dot").forEach((d, i) => {
        d.classList.toggle("active", i === idx);
      });
    }
  }
  function go(n) {
    idx = (idx + n + imgs.length) % imgs.length;
    render();
  }

  if (prev) prev.addEventListener("click", () => go(-1));
  if (next) next.addEventListener("click", () => go(+1));

  document.querySelectorAll(".thumb[data-idx]").forEach(btn => {
    btn.addEventListener("click", () => {
      const i = parseInt(btn.dataset.idx || "0", 10) || 0;
      if (i < imgs.length) { idx = i; render(); }
    });
  });

  if (dotsWrap) {
    dotsWrap.querySelectorAll(".dot").forEach(dot => {
      dot.addEventListener("click", () => {
        const i = parseInt(dot.dataset.idx || "0", 10) || 0;
        idx = i; render();
      });
    });
  }

  render();
})();

/* =========================
   ACCEPT BEST BID (button morph + dial + price slide-down)
   ========================= */
(function initAcceptBestBid() {
  if (!window.bestBid || !window.bestBid.id) return;

  const actionBtn  = document.getElementById("bbActionBtn");
  const priceBox   = document.getElementById("bestBidPriceBox");
  const dial       = document.getElementById("acceptQtyDial");
  const minus      = document.getElementById("acceptQtyMinus");
  const plus       = document.getElementById("acceptQtyPlus");
  const valEl      = document.getElementById("acceptQtyValue");
  const closeBtn   = document.getElementById("bbCloseBtn");
  const r1Flex     = document.getElementById("bbR1Flex");
  const spacer     = document.getElementById("bbSpacer");   // <-- NEW

  let max = parseInt(dial?.dataset.max || "0", 10);
  let val = Math.min(1, Math.max(0, max)) || 1;
  let expanded = false;

  function updateDial() {
    if (!valEl) return;
    val = Math.max(1, Math.min(val, max || 1));
    valEl.textContent = String(val);
    if (minus) minus.disabled = (val <= 1);
    if (plus)  plus.disabled  = (max ? val >= max : false);
  }

  function setExpanded(on) {
  expanded = !!on;

  if (expanded) {
    actionBtn.textContent = "Confirm Quantity";
    actionBtn.setAttribute("aria-expanded", "true");

    if (dial) dial.hidden = false;
    if (closeBtn) closeBtn.hidden = false;

    requestAnimationFrame(() => {
      const dialHeight = dial ? dial.offsetHeight : 0;
      const gap = 12;
      const shift = dialHeight + gap;  // how far the price slides down
      const priceHeight = priceBox ? priceBox.offsetHeight : 0;

      if (priceBox) {
        priceBox.style.setProperty("--price-shift", `${shift}px`);
        priceBox.classList.add("moved");
      }
      // Grow spacer to account for the dial + price block + 4px buffer
      if (spacer) {
        spacer.style.height = `${shift + 4}px`;
      }
    });

    updateDial();
  } else {
    actionBtn.textContent = "Accept Bid";
    actionBtn.setAttribute("aria-expanded", "false");

    if (priceBox) {
      priceBox.classList.remove("moved");
    }
    if (dial) dial.hidden = true;
    if (closeBtn) closeBtn.hidden = true;
    if (spacer) spacer.style.height = "0px";   // collapse space
  }
}

  if (actionBtn) {
    actionBtn.addEventListener("click", () => {
      // If not expanded -> expand; if expanded -> confirm
      if (!expanded) {
        setExpanded(true);
      } else {
        // Submit accept for the best bid with selected quantity
        const form = document.createElement("form");
        form.method = "POST";
        form.action = `/bids/accept_bid/${window.bucketId}`;

        const sel = document.createElement("input");
        sel.type = "hidden";
        sel.name = "selected_bids";
        sel.value = String(window.bestBid.id);
        form.appendChild(sel);

        const qty = document.createElement("input");
        qty.type = "hidden";
        qty.name = `accept_qty[${window.bestBid.id}]`;
        qty.value = String(val);
        form.appendChild(qty);

        document.body.appendChild(form);
        form.submit();
      }
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", () => setExpanded(false));
  }

  if (minus) minus.addEventListener("click", () => { val -= 1; updateDial(); });
  if (plus)  plus.addEventListener("click", () => { val += 1; updateDial(); });

  // Esc to close when expanded
  document.addEventListener("keydown", (e) => {
    if (!expanded) return;
    if (e.key === "Escape") setExpanded(false);
  });

  // Init state collapsed
  setExpanded(false);
})();

/* =========================
   SEE ALL BIDS — smooth scroll
   ========================= */
(function initScrollToBids() {
  const link = document.getElementById("seeAllBidsLink");
  const target = document.getElementById("bidsSection");
  if (!link || !target) return;
  link.addEventListener("click", (e) => {
    e.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
})();

/* ===== Bid selection + dial logic (existing behavior preserved) ===== */
function setAcceptBarVisibility() {
  const button = document.getElementById('acceptBidsButton');
  if (!button) return;
  const anySelected = !!document.querySelector('.selected-checkbox:checked');
  button.disabled = !anySelected;
}

function updateDialVisual(rowEl, val, max) {
  const valueEl = rowEl.querySelector('.dial-value');
  const minusBtn = rowEl.querySelector('.dial-btn.minus');
  const plusBtn  = rowEl.querySelector('.dial-btn.plus');
  const hiddenInput = rowEl.querySelector('input[type="hidden"][id^="accept_qty_"]');
  if (!valueEl) return;

  const clamped = Math.max(0, Math.min(val, max));
  valueEl.textContent = String(clamped);
  if (hiddenInput) hiddenInput.value = clamped;

  if (minusBtn) minusBtn.disabled = (clamped <= 0);
  if (plusBtn)  plusBtn.disabled  = (clamped >= max);
}

function toggleRowSelection(rowEl) {
  const card = rowEl.querySelector('.bid-card-visual');
  const dialGroup = rowEl.querySelector('.dial-assembly');
  const hiddenCheckbox = rowEl.querySelector('.selected-checkbox');
  const max = parseInt(rowEl.dataset.max, 10) || 0;
  const selecting = !card.classList.contains('selected');

  if (selecting) {
    const currentWidthPx = Math.round(card.getBoundingClientRect().width);
    card.style.width = currentWidthPx + 'px';
    card.classList.add('selected');
    card.setAttribute('aria-pressed', 'true');
    if (dialGroup) dialGroup.style.display = 'flex';
    if (hiddenCheckbox) hiddenCheckbox.checked = true;
    updateDialVisual(rowEl, max, max);
  } else {
    card.classList.remove('selected');
    card.setAttribute('aria-pressed', 'false');
    if (dialGroup) dialGroup.style.display = 'none';
    if (hiddenCheckbox) hiddenCheckbox.checked = false;
    card.style.width = '';
    updateDialVisual(rowEl, 0, max);
  }
  setAcceptBarVisibility();
}

function handleDialAdjust(rowEl, delta) {
  const max = parseInt(rowEl.dataset.max, 10) || 0;
  const hiddenInput = rowEl.querySelector('input[type="hidden"][id^="accept_qty_"]');
  let val = 0;
  if (hiddenInput) val = parseInt(hiddenInput.value || '0', 10);
  val = Math.max(0, Math.min(max, val + delta));
  updateDialVisual(rowEl, val, max);
}

/* ===== Buy-box quantity pill ===== */
function setBuyQty(val, opts = {}) {
  const hidden = document.getElementById('quantityInput');
  const pill   = document.getElementById('buyQtyPill');
  const valueEl = document.getElementById('buyQtyValue');
  if (!pill || !valueEl || !hidden) return;

  const max = parseInt(pill.dataset.max || '0', 10) || 0;
  const clamped = (() => {
    if (max > 0) return Math.max(1, Math.min(val, max));
    return Math.max(1, val);
  })();

  valueEl.textContent = String(clamped);
  hidden.value = String(clamped);

  const minus = document.getElementById('buyQtyMinus');
  const plus  = document.getElementById('buyQtyPlus');
  if (minus) minus.disabled = (clamped <= 1);
  if (plus)  plus.disabled  = (max > 0 ? clamped >= max : false);

  if (opts.bump) {
    pill.style.transform = 'scale(1.03)';
    setTimeout(() => { pill.style.transform = ''; }, 120);
  }
}

/* ===== DOM Ready wiring ===== */
document.addEventListener('DOMContentLoaded', () => {
  /* Bid cards (select + dial adjust) */
  document.querySelectorAll('.bid-row').forEach(row => {
    const card  = row.querySelector('.bid-card-visual');
    const minus = row.querySelector('.dial-btn.minus');
    const plus  = row.querySelector('.dial-btn.plus');
    const pill  = row.querySelector('.dial-pill');

    if (card) {
      card.addEventListener('click', () => toggleRowSelection(row));
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleRowSelection(row); }
      });
    }
    if (pill) pill.addEventListener('click', (e) => e.stopPropagation());
    [minus, plus].forEach(btn => {
      if (!btn) return;
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        handleDialAdjust(row, btn.classList.contains('plus') ? +1 : -1);
      });
    });
  });
  setAcceptBarVisibility();

  /* Buy qty dial */
  const buyMinus = document.getElementById('buyQtyMinus');
  const buyPlus  = document.getElementById('buyQtyPlus');
  const hidden   = document.getElementById('quantityInput');
  if (hidden && (buyMinus || buyPlus)) {
    const startVal = parseInt(hidden.value || '1', 10) || 1;
    setBuyQty(startVal);
    if (buyMinus) buyMinus.addEventListener('click', () => {
      const current = parseInt(hidden.value || '1', 10) || 1;
      setBuyQty(current - 1, { bump: true });
    });
    if (buyPlus) buyPlus.addEventListener('click', () => {
      const current = parseInt(hidden.value || '1', 10) || 1;
      setBuyQty(current + 1, { bump: true });
    });
  }

  /* Flash messages */
  const messages = window.flashMessages || [];
  const container = document.getElementById('popup-message-container');
  if (container && messages.length) {
    messages.forEach(([category, message]) => {
      const popup = document.createElement('div');
      popup.className = 'popup-alert ' + category;
      popup.textContent = message;
      container.appendChild(popup);
      setTimeout(() => { popup.remove(); }, 5000);
    });
  }
});
