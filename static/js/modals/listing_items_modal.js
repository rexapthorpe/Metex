// listing_items_modal.js - Shows item details for listings on the Listings tab

// =============================================================================
// STATE
// =============================================================================

let listingData = null;
let setItems = [];
let currentSetItemIndex = 0;

// =============================================================================
// MODAL OPEN / CLOSE
// =============================================================================

function openListingItemsModal(listingId) {
  const modal = document.getElementById('listingItemsModal');
  if (!modal) return;

  modal.style.display = 'flex';
  modal.addEventListener('click', listingItemsOutsideClick);
  document.addEventListener('keydown', listingItemsKeyHandler);

  // Load listing data
  loadListingDetails(listingId);
}

function closeListingItemsModal() {
  const modal = document.getElementById('listingItemsModal');
  if (!modal) return;

  modal.style.display = 'none';
  modal.removeEventListener('click', listingItemsOutsideClick);
  document.removeEventListener('keydown', listingItemsKeyHandler);

  // Reset state
  listingData = null;
  setItems = [];
  currentSetItemIndex = 0;
}

function listingItemsOutsideClick(e) {
  if (e.target && e.target.id === 'listingItemsModal') {
    closeListingItemsModal();
  }
}

function listingItemsKeyHandler(e) {
  if (e.key === 'Escape') closeListingItemsModal();
  else if (e.key === 'ArrowLeft') prevSetItem();
  else if (e.key === 'ArrowRight') nextSetItem();
}

// =============================================================================
// LOAD LISTING DETAILS
// =============================================================================

function loadListingDetails(listingId) {
  const body = document.getElementById('listingItemsModalContent');
  const footer = document.getElementById('listingItemsModalFooter');
  const subtitle = document.getElementById('listingItemsModalSubtitle');

  if (body) body.innerHTML = '<div class="lim-loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading details...</div>';
  if (footer) footer.innerHTML = '';
  if (subtitle) subtitle.textContent = 'Loading...';

  fetch(`/api/listings/${listingId}/details`)
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then(data => {
      listingData = data;
      setItems = data.set_items || [];
      currentSetItemIndex = 0;

      if (setItems.length > 0) {
        // This is a set listing - render with navigation
        renderSetListing();
      } else {
        // Standard or one-of-a-kind listing
        renderListingDetails(data);
      }
    })
    .catch(err => {
      showListingItemsError(err?.message || 'Unexpected error.');
      console.error('listing details fetch error:', err);
    });
}

// =============================================================================
// SET ITEM NAVIGATION
// =============================================================================

function prevSetItem() {
  if (setItems.length > 0 && currentSetItemIndex > 0) {
    currentSetItemIndex--;
    renderSetListing();
  }
}

function nextSetItem() {
  if (setItems.length > 0 && currentSetItemIndex < setItems.length - 1) {
    currentSetItemIndex++;
    renderSetListing();
  }
}

function goToSetItem(index) {
  if (index >= 0 && index < setItems.length) {
    currentSetItemIndex = index;
    renderSetListing();
  }
}

// =============================================================================
// ERROR STATE
// =============================================================================

function showListingItemsError(message) {
  const body = document.getElementById('listingItemsModalContent');
  const footer = document.getElementById('listingItemsModalFooter');
  if (body) {
    body.innerHTML = `
      <div class="lim-error">
        <div class="lim-error-icon"><i class="fa-solid fa-circle-exclamation"></i></div>
        <div class="lim-error-title">Couldn't load details</div>
        <div class="lim-error-msg">${message ? String(message) : 'Please try again.'}</div>
      </div>
    `;
  }
  if (footer) footer.innerHTML = '';
}

// =============================================================================
// RENDER SET LISTING WITH NAVIGATION
// =============================================================================

function renderSetListing() {
  const body = document.getElementById('listingItemsModalContent');
  const footer = document.getElementById('listingItemsModalFooter');
  const subtitle = document.getElementById('listingItemsModalSubtitle');

  if (!body || !footer || !listingData) return;

  const item = setItems[currentSetItemIndex];
  if (!item) {
    showListingItemsError('No items in this set.');
    return;
  }

  // Update subtitle
  if (subtitle) {
    subtitle.textContent = `Set with ${setItems.length} items`;
  }

  // Helpers
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c])
  );
  const showMoney = v =>
    (v === null || v === undefined || v === '' || Number.isNaN(Number(v)))
      ? '--'
      : '$' + Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  // Build navigation tabs
  const navTabsHTML = setItems.map((setItem, idx) => {
    const isActive = idx === currentSetItemIndex;
    const itemLabel = setItem.item_title || `Item ${idx + 1}`;
    return `
      <button class="lim-set-nav-tab ${isActive ? 'active' : ''}"
              onclick="goToSetItem(${idx})"
              title="${esc(itemLabel)}">
        ${esc(itemLabel)}
      </button>
    `;
  }).join('');

  // Item details from the current set item
  const metal = item.metal ?? listingData.metal ?? null;
  const productLine = item.product_line ?? listingData.product_line ?? null;
  const productType = item.product_type ?? listingData.product_type ?? null;
  const weightDisplay = item.weight ?? listingData.weight ?? null;
  const year = item.year ?? listingData.year ?? null;
  const mint = item.mint ?? listingData.mint ?? null;
  const purityRaw = item.purity ?? listingData.purity ?? null;
  const finish = item.finish ?? listingData.finish ?? null;
  const grade = item.grade ?? listingData.grade ?? null;
  const coinSeries = item.coin_series ?? null;
  const specialDesignation = item.special_designation ?? null;

  // Grading
  let certification = null;
  if (item.graded === 1 || item.graded === '1' || item.graded === true) {
    certification = item.grading_service ?? 'Yes';
  }

  // Purity formatting
  const purity = (() => {
    if (purityRaw == null || purityRaw === '') return null;
    const n = Number(purityRaw);
    if (Number.isNaN(n)) return purityRaw;
    return '.' + String(n).replace('0.', '').replace('.', '');
  })();

  // Item quantity and pricing
  const qty = item.quantity ?? 1;
  const priceEach = listingData.effective_price ?? listingData.price_per_coin ?? null;
  const totalVal = priceEach != null ? Number(priceEach) : null;

  // Title for item
  const title = item.item_title || [
    year ? String(year) : '',
    metal || '',
    productLine || productType || ''
  ].filter(Boolean).join(' ').trim() +
    (weightDisplay ? ` ${weightDisplay}` : '');

  // Image source
  const imgSrc = (() => {
    console.log('[Set Item Photo] item.photo_path:', item.photo_path);
    if (item.photo_path) {
      const path = item.photo_path;
      let url;
      if (path.startsWith('/')) {
        url = path;
      } else if (path.startsWith('static/')) {
        url = '/' + path;
      } else {
        url = '/static/' + path;
      }
      console.log('[Set Item Photo] Constructed URL:', url);
      return url;
    }
    console.log('[Set Item Photo] No photo_path, using fallback');
    const svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400'><rect width='400' height='400' fill='%23f3f4f6'/><text x='200' y='205' text-anchor='middle' font-family='Arial,Helvetica,sans-serif' font-size='28' fill='%239ca3af'>No Image</text></svg>";
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
  })();

  // Build specifications grid
  const specs = [];

  if (metal) specs.push({ icon: 'fa-globe', label: 'Metal', value: metal });
  if (year) specs.push({ icon: 'fa-calendar', label: 'Year', value: year });
  if (productLine) specs.push({ icon: 'fa-tags', label: 'Product line', value: productLine });
  if (mint) specs.push({ icon: 'fa-building-columns', label: 'Mint', value: mint });
  if (productType) specs.push({ icon: 'fa-tag', label: 'Product type', value: productType });
  if (purity) specs.push({ icon: 'fa-layer-group', label: 'Purity', value: purity });
  if (weightDisplay) specs.push({ icon: 'fa-scale-balanced', label: 'Weight', value: weightDisplay });
  if (finish) specs.push({ icon: 'fa-wand-magic-sparkles', label: 'Finish', value: finish });
  if (grade) specs.push({ icon: 'fa-award', label: 'Grade', value: grade });
  if (coinSeries) specs.push({ icon: 'fa-star', label: 'Coin series', value: coinSeries });
  if (specialDesignation) specs.push({ icon: 'fa-gem', label: 'Designation', value: specialDesignation });
  if (certification) specs.push({ icon: 'fa-certificate', label: 'Certification', value: certification });

  // Packaging info for set items
  if (item.packaging_type) {
    specs.push({ icon: 'fa-box', label: 'Packaging', value: item.packaging_type.replace(/_/g, ' ') });
  }
  if (item.packaging_notes) {
    specs.push({ icon: 'fa-clipboard', label: 'Packaging notes', value: item.packaging_notes });
  }
  if (item.edition_number && item.edition_total) {
    specs.push({ icon: 'fa-hashtag', label: 'Edition', value: `#${item.edition_number} of ${item.edition_total}` });
  }
  if (item.condition_notes) {
    specs.push({ icon: 'fa-info-circle', label: 'Condition', value: item.condition_notes });
  }

  const specsHTML = specs.map(s => `
    <div class="lim-spec-item">
      <div class="lim-spec-icon"><i class="fa-solid ${s.icon}"></i></div>
      <span class="lim-spec-label">${s.label}</span>
      <span class="lim-spec-value">${esc(s.value)}</span>
    </div>
  `).join('');

  // Body content with nav bar
  body.innerHTML = `
    <div class="lim-set-nav">
      <div class="lim-set-nav-tabs">
        ${navTabsHTML}
      </div>
    </div>

    <div class="lim-item-card">
      <div class="lim-item-image">
        <img src="${imgSrc}" alt="${esc(title)}">
      </div>
      <div class="lim-item-details">
        <h4 class="lim-item-title">${esc(title) || 'Item'}</h4>
        <div class="lim-item-meta">
          <span class="lim-qty-badge">Qty: ${qty}</span>
          <span class="lim-price-each">@ ${showMoney(priceEach)} each</span>
        </div>
      </div>
      <div class="lim-item-total">
        <span class="lim-item-total-price">${showMoney(totalVal)}</span>
      </div>
    </div>

    ${specs.length > 0 ? `
    <div class="lim-specs-section">
      <div class="lim-specs-header">
        <span>Specifications</span>
        <span class="lim-listing-type-badge lim-badge-set"><i class="fa-solid fa-layer-group"></i> Set Item ${currentSetItemIndex + 1}/${setItems.length}</span>
      </div>
      <div class="lim-specs-grid">
        ${specsHTML}
      </div>
    </div>
    ` : ''}
  `;

  // Footer with pricing summary for entire set
  const pricingMode = listingData.pricing_mode;
  let pricingInfo = '';

  if (pricingMode === 'premium_to_spot') {
    pricingInfo = `
      <div class="lim-footer-row">
        <span class="lim-footer-label">Pricing Mode</span>
        <span class="lim-footer-value"><i class="fa-solid fa-chart-line"></i> Variable</span>
      </div>
      <div class="lim-footer-row">
        <span class="lim-footer-label">Spot Premium</span>
        <span class="lim-footer-value">+${showMoney(listingData.spot_premium)}</span>
      </div>
      <div class="lim-footer-row">
        <span class="lim-footer-label">Floor Price</span>
        <span class="lim-footer-value">${showMoney(listingData.floor_price)}</span>
      </div>
    `;
  } else {
    pricingInfo = `
      <div class="lim-footer-row">
        <span class="lim-footer-label">Pricing Mode</span>
        <span class="lim-footer-value"><i class="fa-solid fa-lock"></i> Fixed</span>
      </div>
    `;
  }

  const setQty = listingData.quantity ?? 1;
  const setTotalVal = (setQty != null && priceEach != null) ? Number(setQty) * Number(priceEach) : null;

  footer.innerHTML = `
    ${pricingInfo}
    <div class="lim-footer-row total">
      <span class="lim-footer-label">Set Total (${setQty} ${setQty === 1 ? 'set' : 'sets'})</span>
      <span class="lim-footer-value">${showMoney(setTotalVal)}</span>
    </div>
  `;
}

// =============================================================================
// RENDER STANDARD/ONE-OF-A-KIND LISTING DETAILS
// =============================================================================

function renderListingDetails(entry) {
  const body = document.getElementById('listingItemsModalContent');
  const footer = document.getElementById('listingItemsModalFooter');
  const subtitle = document.getElementById('listingItemsModalSubtitle');

  if (!body || !footer) return;

  // Helpers
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c])
  );
  const showMoney = v =>
    (v === null || v === undefined || v === '' || Number.isNaN(Number(v)))
      ? '--'
      : '$' + Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  // Normalize fields
  const metal = entry.metal ?? null;
  const productLine = entry.product_line ?? null;
  const productType = entry.product_type ?? null;
  const seriesVariant = entry.series_variant ?? null;
  const coinSeries = entry.coin_series ?? null;

  // Weight
  let weightDisplay = null;
  if (entry.weight != null) {
    weightDisplay = String(entry.weight);
  }

  const year = entry.year ?? null;
  const mint = entry.mint ?? null;
  const purityRaw = entry.purity ?? null;
  const finish = entry.finish ?? null;
  const grade = entry.grade ?? null;

  // Isolated listing fields
  const isIsolated = entry.is_isolated === 1 || entry.is_isolated === '1' || entry.is_isolated === true;
  const isolatedType = entry.isolated_type ?? null;
  const packagingType = entry.packaging_type ?? null;
  const packagingNotes = entry.packaging_notes ?? null;
  const editionNumber = entry.edition_number ?? null;
  const editionTotal = entry.edition_total ?? null;
  const conditionNotes = entry.condition_notes ?? null;

  // Grading service
  let certification = null;
  const gradedFlag = entry.graded;
  if (gradedFlag === 1 || gradedFlag === '1' || gradedFlag === true) {
    certification = entry.grading_service ?? 'Yes';
  }

  // Purity formatting
  const purity = (() => {
    if (purityRaw == null || purityRaw === '') return null;
    const n = Number(purityRaw);
    if (Number.isNaN(n)) return purityRaw;
    return '.' + String(n).replace('0.', '').replace('.', '');
  })();

  // Determine listing type for badge
  let listingTypeBadge = '';
  if (isIsolated) {
    if (isolatedType === 'set') {
      listingTypeBadge = '<span class="lim-listing-type-badge lim-badge-set"><i class="fa-solid fa-layer-group"></i> Set</span>';
    } else {
      listingTypeBadge = '<span class="lim-listing-type-badge lim-badge-oneofakind"><i class="fa-solid fa-gem"></i> One-of-a-Kind</span>';
    }
  } else {
    listingTypeBadge = '<span class="lim-listing-type-badge lim-badge-standard"><i class="fa-solid fa-coins"></i> Standard</span>';
  }

  // Quantity and pricing
  const qty = entry.quantity ?? 1;
  const priceEach = entry.effective_price ?? entry.price_per_coin ?? null;
  const totalVal = (qty != null && priceEach != null && !Number.isNaN(Number(qty)) && !Number.isNaN(Number(priceEach)))
    ? Number(qty) * Number(priceEach)
    : null;

  // Title
  const title = [
    year ? String(year) : '',
    metal ? `${metal}` : '',
    productLine || productType || ''
  ].filter(Boolean).join(' ').trim() +
    (weightDisplay ? ` ${weightDisplay}` : '');

  // Update subtitle
  if (subtitle) {
    subtitle.textContent = `${qty} ${qty === 1 ? 'item' : 'items'} in listing`;
  }

  // Image source
  const imgSrc = (() => {
    if (entry.photo_path) {
      const path = entry.photo_path;
      if (path.startsWith('/')) return path;
      if (path.startsWith('static/')) return '/' + path;
      return '/static/' + path;
    }
    const svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400'><rect width='400' height='400' fill='%23f3f4f6'/><text x='200' y='205' text-anchor='middle' font-family='Arial,Helvetica,sans-serif' font-size='28' fill='%239ca3af'>No Image</text></svg>";
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
  })();

  // Build specifications grid (matching bucket page format)
  const specs = [];

  // Row 1: Metal, Year
  if (metal) specs.push({ icon: 'fa-globe', label: 'Metal', value: metal });
  if (year) specs.push({ icon: 'fa-calendar', label: 'Year', value: year });

  // Row 2: Product line, Mint
  if (productLine) specs.push({ icon: 'fa-tags', label: 'Product line', value: productLine });
  if (mint) specs.push({ icon: 'fa-building-columns', label: 'Mint', value: mint });

  // Row 3: Product type, Purity
  if (productType) specs.push({ icon: 'fa-tag', label: 'Product type', value: productType });
  if (purity) specs.push({ icon: 'fa-layer-group', label: 'Purity', value: purity });

  // Row 4: Weight, Finish
  if (weightDisplay) specs.push({ icon: 'fa-scale-balanced', label: 'Weight', value: weightDisplay });
  if (finish) specs.push({ icon: 'fa-wand-magic-sparkles', label: 'Finish', value: finish });

  // Row 5: Series variant (if available)
  if (seriesVariant && seriesVariant !== 'None') {
    specs.push({ icon: 'fa-star', label: 'Series variant', value: seriesVariant.replace(/_/g, ' ') });
  }

  // For one-of-a-kind listings (not sets), add packaging and edition info
  if (isIsolated && isolatedType !== 'set') {
    if (packagingType) {
      specs.push({ icon: 'fa-box', label: 'Packaging', value: packagingType.replace(/_/g, ' ') });
    }
    if (packagingNotes) {
      specs.push({ icon: 'fa-clipboard', label: 'Packaging notes', value: packagingNotes });
    }
    if (editionNumber && editionTotal) {
      specs.push({ icon: 'fa-hashtag', label: 'Edition', value: `#${editionNumber} of ${editionTotal}` });
    }
    if (conditionNotes) {
      specs.push({ icon: 'fa-info-circle', label: 'Condition notes', value: conditionNotes });
    }
  }

  // Grading info
  if (certification) specs.push({ icon: 'fa-certificate', label: 'Certification', value: certification });

  const specsHTML = specs.map(s => `
    <div class="lim-spec-item">
      <div class="lim-spec-icon"><i class="fa-solid ${s.icon}"></i></div>
      <span class="lim-spec-label">${s.label}</span>
      <span class="lim-spec-value">${esc(s.value)}</span>
    </div>
  `).join('');

  // Body content
  body.innerHTML = `
    <div class="lim-item-card">
      <div class="lim-item-image">
        <img src="${imgSrc}" alt="${esc(title)}">
      </div>
      <div class="lim-item-details">
        <h4 class="lim-item-title">${esc(title) || 'Item'}</h4>
        <div class="lim-item-meta">
          <span class="lim-qty-badge">Qty: ${qty}</span>
          <span class="lim-price-each">@ ${showMoney(priceEach)} each</span>
        </div>
      </div>
      <div class="lim-item-total">
        <span class="lim-item-total-price">${showMoney(totalVal)}</span>
      </div>
    </div>

    ${specs.length > 0 ? `
    <div class="lim-specs-section">
      <div class="lim-specs-header">
        <span>Specifications</span>
        ${listingTypeBadge}
      </div>
      <div class="lim-specs-grid">
        ${specsHTML}
      </div>
    </div>
    ` : ''}
  `;

  // Footer with pricing summary
  const pricingMode = entry.pricing_mode;
  let pricingInfo = '';

  if (pricingMode === 'premium_to_spot') {
    pricingInfo = `
      <div class="lim-footer-row">
        <span class="lim-footer-label">Pricing Mode</span>
        <span class="lim-footer-value"><i class="fa-solid fa-chart-line"></i> Variable</span>
      </div>
      <div class="lim-footer-row">
        <span class="lim-footer-label">Spot Premium</span>
        <span class="lim-footer-value">+${showMoney(entry.spot_premium)}</span>
      </div>
      <div class="lim-footer-row">
        <span class="lim-footer-label">Floor Price</span>
        <span class="lim-footer-value">${showMoney(entry.floor_price)}</span>
      </div>
    `;
  } else {
    pricingInfo = `
      <div class="lim-footer-row">
        <span class="lim-footer-label">Pricing Mode</span>
        <span class="lim-footer-value"><i class="fa-solid fa-lock"></i> Fixed</span>
      </div>
    `;
  }

  footer.innerHTML = `
    ${pricingInfo}
    <div class="lim-footer-row total">
      <span class="lim-footer-label">Total Value (${qty} ${qty === 1 ? 'item' : 'items'})</span>
      <span class="lim-footer-value">${showMoney(totalVal)}</span>
    </div>
  `;
}

// =============================================================================
// EXPOSE GLOBALS
// =============================================================================

window.openListingItemsModal = openListingItemsModal;
window.closeListingItemsModal = closeListingItemsModal;
window.prevSetItem = prevSetItem;
window.nextSetItem = nextSetItem;
window.goToSetItem = goToSetItem;
