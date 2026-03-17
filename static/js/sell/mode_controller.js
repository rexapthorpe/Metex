/**
 * Sell Page Mode Controller
 *
 * Handles listing mode switching (Standard, One-of-a-Kind, Set),
 * cover photo upload, quantity stepper, multi-photo management,
 * set item building, and form submission validation.
 *
 * Extracted from templates/sell.html inline script during refactor.
 * NO BEHAVIOR CHANGES - structure only.
 */
(function() {
  'use strict';

  console.log('[MAIN SCRIPT] Main sell script loaded v3', new Date().toISOString());

  // ========== DOM ELEMENTS ==========
  const modeStandard = document.getElementById('modeStandard');
  const modeIsolated = document.getElementById('modeIsolated');
  const modeSet = document.getElementById('modeSet');
  const isIsolatedHidden = document.getElementById('isIsolatedHidden');
  const isSetHidden = document.getElementById('isSetHidden');
  const isolatedWarning = document.getElementById('isolatedWarning');
  const titleDescriptionContainer = document.getElementById('titleDescriptionContainer');
  const listingTitleInput = document.getElementById('listing_title');
  const quantityGroup = document.getElementById('quantityGroup');
  const quantityInput = document.getElementById('quantity');
  const itemPhotoInput = document.getElementById('item_photo');
  const coverPhotoGroup = document.getElementById('coverPhotoGroup');
  const coverPhotoLabel = document.getElementById('coverPhotoLabel');
  const coverPhotoInput = document.getElementById('cover_photo');
  const coverPhotoBox = document.getElementById('coverPhotoUploadBox');
  const coverPhotoPreview = document.getElementById('coverPhotoPreview');
  const coverPhotoClearBtn = document.getElementById('coverPhotoClearBtn');
  const addSetItemBtnContainer = document.getElementById('addSetItemBtnContainer');
  const addSetItemBtn = document.getElementById('addSetItemBtn');
  const setContentsDisplay = document.getElementById('setContentsDisplay');
  const setItemsList = document.getElementById('setItemsList');
  const sellForm = document.getElementById('sellForm');
  const mainItemHeader = document.getElementById('mainItemHeader');
  const setItemLabel = document.getElementById('setItemLabel');

  let setItems = []; // Array to store set items
  let setItemCount = 0;
  window.currentMode = 'standard'; // Track current mode (window-level for sidebar access)

  // ========== AUTOSAVE DRAFT ==========
  const DRAFT_KEY = 'metex_sell_draft_v1';
  const AUTOSAVE_DEBOUNCE_MS = 1000;
  let autosaveTimeout = null;

  // Setup cover photo upload functionality
  if (coverPhotoBox && coverPhotoInput && coverPhotoPreview && coverPhotoClearBtn) {
    coverPhotoBox.addEventListener('click', (e) => {
      if (!e.target.closest('.close-button') && !coverPhotoBox.classList.contains('has-image')) {
        coverPhotoInput.click();
      }
    });

    coverPhotoInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        if (!file.type.startsWith('image/')) {
          alert('Please select an image file (JPG, PNG, etc.)');
          coverPhotoInput.value = '';
          return;
        }
        const reader = new FileReader();
        reader.onload = (event) => {
          coverPhotoPreview.src = event.target.result;
          coverPhotoPreview.style.display = 'block';
          coverPhotoClearBtn.style.display = 'flex';
          coverPhotoBox.classList.add('has-image');
        };
        reader.readAsDataURL(file);
      } else {
        clearCoverPhoto();
      }
    });

    coverPhotoClearBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      clearCoverPhoto();
    });
  }

  function clearCoverPhoto() {
    // In edit mode, remove the existing photo ID from keepPhotoIds so the backend deletes it
    if (window.sellEditMode && coverPhotoBox && coverPhotoBox.dataset.existingPhotoId) {
      const keepEl = document.getElementById('keepPhotoIds');
      if (keepEl) {
        const photoId = coverPhotoBox.dataset.existingPhotoId.toString();
        const ids = keepEl.value.split(',').filter(id => id.trim() !== '' && id.trim() !== photoId);
        keepEl.value = ids.join(',');
      }
      delete coverPhotoBox.dataset.existingPhotoId;
    }
    coverPhotoPreview.style.display = 'none';
    coverPhotoPreview.src = '';
    coverPhotoClearBtn.style.display = 'none';
    coverPhotoBox.classList.remove('has-image');
    coverPhotoInput.value = '';
  }

  // ========== QUANTITY STEPPER SETUP ==========
  function setupQuantityStepper() {
    const stepper = document.querySelector('.quantity-stepper');
    if (!stepper) return;

    const qtyInput = stepper.querySelector('input[type="number"]');
    const decreaseBtn = stepper.querySelector('[data-action="decrease"]');
    const increaseBtn = stepper.querySelector('[data-action="increase"]');

    if (!qtyInput || !decreaseBtn || !increaseBtn) return;

    decreaseBtn.addEventListener('click', (e) => {
      e.preventDefault();
      let currentValue = parseInt(qtyInput.value) || 1;
      if (currentValue > 1) {
        qtyInput.value = currentValue - 1;
        qtyInput.dispatchEvent(new Event('input', { bubbles: true }));
      }
    });

    increaseBtn.addEventListener('click', (e) => {
      e.preventDefault();
      let currentValue = parseInt(qtyInput.value) || 0;
      qtyInput.value = currentValue + 1;
      qtyInput.dispatchEvent(new Event('input', { bubbles: true }));
    });

    // Ensure value is at least 1 when user manually types
    qtyInput.addEventListener('blur', () => {
      let val = parseInt(qtyInput.value);
      if (isNaN(val) || val < 1) {
        qtyInput.value = 1;
      }
    });

    // Initialize to 1 on page load
    if (!qtyInput.value || parseInt(qtyInput.value) < 1) {
      qtyInput.value = 1;
    }
  }

  // Initialize quantity stepper
  setupQuantityStepper();

  // ========== MODE SWITCHING LOGIC ==========
  function updateUIForMode(mode) {
    console.log('[MODE SWITCH] updateUIForMode called with mode:', mode);
    window.currentMode = mode;

    // Update hidden inputs for backend
    isIsolatedHidden.value = (mode === 'isolated' || mode === 'set') ? '1' : '0';
    isSetHidden.value = (mode === 'set') ? '1' : '0';

    // Update warning banner
    isolatedWarning.style.display = (mode === 'isolated' || mode === 'set') ? 'block' : 'none';

    // Update Title/Description section
    const needsTitleDesc = (mode === 'isolated' || mode === 'set');
    titleDescriptionContainer.style.display = needsTitleDesc ? 'block' : 'none';
    if (needsTitleDesc) {
      listingTitleInput.setAttribute('required', 'required');
    } else {
      listingTitleInput.removeAttribute('required');
    }

    // Update Quantity field visibility
    if (mode === 'isolated' || mode === 'set') {
      // One-of-a-Kind and Set: hide quantity (always 1)
      quantityGroup.style.display = 'none';
      quantityInput.removeAttribute('required');
      quantityInput.value = '1'; // Set to 1 implicitly
    } else {
      // Standard: show quantity (number of items)
      quantityGroup.style.display = 'block';
      quantityInput.setAttribute('required', 'required');
      const qtyLabel = quantityGroup.querySelector('label');
      if (qtyLabel) qtyLabel.innerHTML = 'Quantity <span class="required">*</span>';
      const qtyExample = quantityGroup.querySelector('.example-text');
      if (qtyExample) qtyExample.textContent = 'Number of items (whole numbers only)';
    }

    // Update Cover Photo visibility and label
    const needsCoverPhoto = (mode === 'isolated' || mode === 'set');
    if (needsCoverPhoto) {
      coverPhotoGroup.style.display = 'block';
      if (mode === 'set') {
        coverPhotoLabel.textContent = 'Set Cover Photo';
      } else {
        coverPhotoLabel.textContent = 'Cover Photo';
      }
    } else {
      coverPhotoGroup.style.display = 'none';
      clearCoverPhoto();
    }

    // Update Edition Numbering visibility (show for one-of-a-kind and set, hide for standard)
    const editionNumberingGroup = document.getElementById('editionNumberingGroup');
    if (mode === 'isolated' || mode === 'set') {
      if (editionNumberingGroup) editionNumberingGroup.style.display = 'block';
    } else {
      if (editionNumberingGroup) editionNumberingGroup.style.display = 'none';
      // Clear edition fields when switching to standard mode
      document.getElementById('edition_number').value = '';
      document.getElementById('edition_total').value = '';
    }

    // Update Packaging and Condition Notes visibility based on mode
    // Standard: packaging in Listing Specifications only
    // One-of-a-Kind & Set: packaging and condition notes in Product Specifications
    const itemPackagingTypeGroup = document.getElementById('itemPackagingTypeGroup');
    const itemPackagingNotesGroup = document.getElementById('itemPackagingNotesGroup');
    const itemConditionNotesGroup = document.getElementById('itemConditionNotesGroup');
    const listingPackagingTypeGroup = document.getElementById('listingPackagingTypeGroup');
    const listingPackagingNotesGroup = document.getElementById('listingPackagingNotesGroup');

    if (mode === 'standard') {
      // Standard mode: hide product specs packaging/condition, show listing specs packaging
      if (itemPackagingTypeGroup) itemPackagingTypeGroup.style.display = 'none';
      if (itemPackagingNotesGroup) itemPackagingNotesGroup.style.display = 'none';
      if (itemConditionNotesGroup) itemConditionNotesGroup.style.display = 'none';
      if (listingPackagingTypeGroup) listingPackagingTypeGroup.style.display = 'block';
      if (listingPackagingNotesGroup) listingPackagingNotesGroup.style.display = 'block';
    } else {
      // One-of-a-Kind & Set modes: show product specs packaging/condition, hide listing specs packaging
      if (itemPackagingTypeGroup) itemPackagingTypeGroup.style.display = 'block';
      if (itemPackagingNotesGroup) itemPackagingNotesGroup.style.display = 'block';
      if (itemConditionNotesGroup) itemConditionNotesGroup.style.display = 'block';
      if (listingPackagingTypeGroup) listingPackagingTypeGroup.style.display = 'none';
      if (listingPackagingNotesGroup) listingPackagingNotesGroup.style.display = 'none';
    }

    // Update Set Builder visibility

    if (mode === 'set') {
      addSetItemBtnContainer.style.display = 'block';
      setItemLabel.style.display = 'block';
      // Update label to show correct item number based on current setItems count
      setItemLabel.textContent = `Set Item #${setItems.length + 1}`;
      mainItemHeader.textContent = 'Product Specifications';
    } else {
      addSetItemBtnContainer.style.display = 'none';
      setContentsDisplay.style.display = 'none';
      setItemLabel.style.display = 'none';
      mainItemHeader.textContent = 'Item Specifications';
      // Note: We preserve setItems array when switching modes
    }

    // Update Photo Container (Standard/Isolated vs Set mode)
    const standardPhotoContainer = document.getElementById('standardPhotoContainer');
    const multiPhotoContainer = document.getElementById('multiPhotoContainer');
    const multiPhotoLabel = multiPhotoContainer ? multiPhotoContainer.querySelector('label') : null;

    if (mode === 'set') {
      // Set mode: Hide standard photo grid, show set photo boxes
      if (standardPhotoContainer) standardPhotoContainer.style.display = 'none';
      if (multiPhotoContainer) multiPhotoContainer.style.display = 'block';
    } else {
      // Standard or Isolated: Show standard photo grid (supports up to 3 photos)
      if (standardPhotoContainer) standardPhotoContainer.style.display = 'block';
      if (multiPhotoContainer) multiPhotoContainer.style.display = 'none';
      clearMultiPhotos();
    }

    // Update sidebar checklist visibility based on mode
    console.log('[MODE SWITCH] Checking for sidebar functions', {
      hasUpdateChecklistVisibility: typeof window.updateChecklistVisibility === 'function',
      hasUpdateSidebarSummary: typeof window.updateSidebarSummary === 'function',
      hasUpdateChecklist: typeof window.updateChecklist === 'function'
    });

    if (typeof window.updateChecklistVisibility === 'function') {
      console.log('[MODE SWITCH] Calling window.updateChecklistVisibility()');
      window.updateChecklistVisibility();
    } else {
      console.warn('[MODE SWITCH] window.updateChecklistVisibility is NOT a function!');
    }

    // Trigger sidebar updates (if functions are available)
    if (typeof window.updateSidebarSummary === 'function') {
      console.log('[MODE SWITCH] Calling window.updateSidebarSummary()');
      window.updateSidebarSummary();
    }
    if (typeof window.updateChecklist === 'function') {
      console.log('[MODE SWITCH] Calling window.updateChecklist()');
      window.updateChecklist();
    } else {
      console.warn('[MODE SWITCH] window.updateChecklist is NOT a function!');
    }

    // Toggle required attributes for current-item fields (Set mode only)
    if (typeof window.toggleCurrentItemRequiredAttributes === 'function') {
      window.toggleCurrentItemRequiredAttributes();
    }

    // Show/hide the spot-metal selector (set mode + premium-to-spot only)
    const setSpotMetalGroup = document.getElementById('set_spot_metal_group');
    if (setSpotMetalGroup) {
      const pricingMode = document.querySelector('input[name="pricing_mode"]:checked')?.value;
      setSpotMetalGroup.style.display = (mode === 'set' && pricingMode === 'premium_to_spot') ? 'block' : 'none';
    }

    // Autosave disabled - no longer saving drafts on mode change
    // scheduleAutosave();
  }

  // Mode radio change handlers
  modeStandard.addEventListener('change', () => {
    if (modeStandard.checked) updateUIForMode('standard');
  });
  modeIsolated.addEventListener('change', () => {
    if (modeIsolated.checked) updateUIForMode('isolated');
  });
  modeSet.addEventListener('change', () => {
    if (modeSet.checked) updateUIForMode('set');
  });

  // Initialize Lucide icons on page load
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  // Re-initialize Lucide icons when mode changes (for any dynamic content)
  const reinitializeLucide = () => {
    setTimeout(() => {
      if (typeof lucide !== 'undefined') {
        lucide.createIcons();
      }
    }, 50);
  };

  modeStandard.addEventListener('change', reinitializeLucide);
  modeIsolated.addEventListener('change', reinitializeLucide);
  modeSet.addEventListener('change', reinitializeLucide);

  // ========== MULTI-PHOTO MANAGEMENT (Set Items — 3 static boxes) ==========
  let currentItemPhotos = []; // Array of File objects (max 3)

  // Rebuild currentItemPhotos from the 3 static set photo inputs
  function updateCurrentItemPhotos() {
    currentItemPhotos = [];
    ['setPhotoInput1', 'setPhotoInput2', 'setPhotoInput3'].forEach(function(id) {
      const input = document.getElementById(id);
      if (input && input.files.length > 0) currentItemPhotos.push(input.files[0]);
    });
    window.currentItemPhotos = currentItemPhotos;
  }

  function setupSetPhotoBox(boxId, inputId, previewId, clearId) {
    const box = document.getElementById(boxId);
    const input = document.getElementById(inputId);
    const preview = document.getElementById(previewId);
    const clearBtn = document.getElementById(clearId);
    if (!box || !input) return;

    box.addEventListener('click', function(e) {
      if (!e.target.closest('.close-button') && !box.classList.contains('has-image')) {
        input.click();
      }
    });

    input.addEventListener('change', function(e) {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function(ev) {
        if (preview) { preview.src = ev.target.result; preview.style.display = 'block'; }
        if (clearBtn) clearBtn.style.display = 'flex';
        box.classList.add('has-image');
      };
      reader.readAsDataURL(file);
      updateCurrentItemPhotos();
      if (typeof window.updateChecklist === 'function') window.updateChecklist();
      if (typeof window.updateAddItemButtonState === 'function') window.updateAddItemButtonState();
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        input.value = '';
        if (preview) { preview.style.display = 'none'; preview.src = ''; }
        clearBtn.style.display = 'none';
        box.classList.remove('has-image');
        updateCurrentItemPhotos();
        if (typeof window.updateChecklist === 'function') window.updateChecklist();
        if (typeof window.updateAddItemButtonState === 'function') window.updateAddItemButtonState();
      });
    }
  }

  function clearMultiPhotos() {
    ['1', '2', '3'].forEach(function(n) {
      const box = document.getElementById('setPhotoBox' + n);
      const preview = document.getElementById('setPhotoPreview' + n);
      const clearBtn = document.getElementById('setPhotoClear' + n);
      const input = document.getElementById('setPhotoInput' + n);
      if (box) box.classList.remove('has-image');
      if (preview) { preview.style.display = 'none'; preview.src = ''; }
      if (clearBtn) clearBtn.style.display = 'none';
      if (input) input.value = '';
    });
    currentItemPhotos = [];
    window.currentItemPhotos = currentItemPhotos;
    if (typeof window.updateChecklist === 'function') window.updateChecklist();
  }

  // Initialize set photo box handlers
  setupSetPhotoBox('setPhotoBox1', 'setPhotoInput1', 'setPhotoPreview1', 'setPhotoClear1');
  setupSetPhotoBox('setPhotoBox2', 'setPhotoInput2', 'setPhotoPreview2', 'setPhotoClear2');
  setupSetPhotoBox('setPhotoBox3', 'setPhotoInput3', 'setPhotoPreview3', 'setPhotoClear3');

  // Capture current spec values from the form
  function captureSpecValues() {
    // For set and standard mode: use multi-photo array
    // For isolated: use single photo
    let photoData;
    if (window.currentMode === 'set' || window.currentMode === 'standard') {
      // Set/Standard mode: return array of photos (1-3)
      photoData = currentItemPhotos.length > 0 ? currentItemPhotos : null;
    } else {
      // Isolated: single photo
      const photoInput = document.getElementById('item_photo');
      photoData = photoInput && photoInput.files.length > 0 ? photoInput.files[0] : null;
    }

    return {
      item_title: document.getElementById('item_title')?.value?.trim() || '',
      metal: document.getElementById('metal').value.trim(),
      product_line: document.getElementById('product_line').value.trim(),
      product_type: document.getElementById('product_type').value.trim(),
      weight: document.getElementById('weight').value.trim(),
      purity: document.getElementById('purity').value.trim(),
      mint: document.getElementById('mint').value.trim(),
      year: document.getElementById('year').value.trim(),
      finish: document.getElementById('finish').value.trim(),
      series_variant: document.getElementById('series_variant').value.trim(),
      packaging_type: document.getElementById('item_packaging_type').value.trim(),
      packaging_notes: document.getElementById('item_packaging_notes').value.trim(),
      condition_notes: document.getElementById('item_condition_notes')?.value?.trim() || '',
      photo: photoData, // Can be File or Array<File>
      quantity: document.getElementById('quantity').value.trim(),
      edition_number: document.getElementById('edition_number').value.trim(),
      edition_total: document.getElementById('edition_total').value.trim()
    };
  }

  // Clear Product Specification fields
  function clearSpecFields() {
    const itemTitleInput = document.getElementById('item_title');
    if (itemTitleInput) itemTitleInput.value = '';
    document.getElementById('metal').value = '';
    document.getElementById('product_line').value = '';
    document.getElementById('product_type').value = '';
    document.getElementById('weight').value = '';
    document.getElementById('purity').value = '';
    document.getElementById('mint').value = '';
    document.getElementById('year').value = '';
    document.getElementById('finish').value = '';
    document.getElementById('series_variant').value = '';
    document.getElementById('item_packaging_type').value = '';
    document.getElementById('item_packaging_notes').value = '';
    if (document.getElementById('item_condition_notes')) {
      document.getElementById('item_condition_notes').value = '';
    }
    document.getElementById('quantity').value = '';
    document.getElementById('edition_number').value = '';
    document.getElementById('edition_total').value = '';

    // Clear photo (single or multi depending on mode)
    if (window.currentMode === 'set') {
      // Clear multi-photo array
      clearMultiPhotos();
    } else {
      // Clear single photo
      const photoInput = document.getElementById('item_photo');
      const photoPreview = document.getElementById('photoPreview');
      const photoClearBtn = document.getElementById('photoClearBtn');
      const photoBox = document.getElementById('photoUploadBox');

      if (photoInput) photoInput.value = '';
      if (photoPreview) {
        photoPreview.style.display = 'none';
        photoPreview.src = '';
      }
      if (photoClearBtn) photoClearBtn.style.display = 'none';
      if (photoBox) photoBox.classList.remove('has-image');
    }

    // Trigger checklist update
    if (typeof window.updateSidebarChecklist === 'function') {
      window.updateSidebarChecklist();
    }
  }

  // Export for use in sidebar script
  window.captureSpecValues = captureSpecValues;
  window.clearSpecFields = clearSpecFields;
  window.setItems = setItems;

  // Render set items list
  function renderSetItems() {
    setItemsList.innerHTML = '';

    if (setItems.length === 0) {
      setContentsDisplay.style.display = 'none';
      return;
    }

    setContentsDisplay.style.display = 'block';

    setItems.forEach((item, index) => {
      const itemDiv = document.createElement('div');
      itemDiv.style.cssText = 'background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; position: relative;';

      const summary = `${item.weight || '?'} ${item.metal || '?'} ${item.product_line || '?'} ${item.year || '?'}`;

      // Create thumbnail from photoURL (string URL or data URL) or photo (File object)
      let thumbnailHTML = '';
      let primaryPhoto = null;
      const directPhotoURL = item.photoURL || null;

      if (directPhotoURL) {
        // Existing items (restored from DB) or sidebar-added items have a URL/data-URL ready
        thumbnailHTML = `<img class="item-thumbnail" src="${directPhotoURL}" style="width: 60px; height: 60px; object-fit: cover; border-radius: 4px; margin-right: 12px;" alt="Item photo">`;
      } else if (item.photo) {
        // Newly added items carry File objects — use FileReader to generate preview
        primaryPhoto = Array.isArray(item.photo) ? item.photo[0] : item.photo;
        if (primaryPhoto) {
          thumbnailHTML = '<img class="item-thumbnail" style="width: 60px; height: 60px; object-fit: cover; border-radius: 4px; margin-right: 12px;" alt="Item photo">';
        }
      }

      const itemTitle = item.item_title || `Item #${index + 1}`;
      itemDiv.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          ${thumbnailHTML}
          <div style="flex: 1;">
            <div style="font-weight: 600; margin-bottom: 4px; color: #1976d2;">${itemTitle}</div>
            <div style="font-size: 14px; color: #4b5563;">${summary}</div>
            <div style="font-size: 12px; color: #6b7280; margin-top: 4px;">
              ${item.mint || ''} • ${item.finish || ''}${item.quantity ? ' • Qty: ' + item.quantity : ''}
            </div>
          </div>
          <button type="button" class="remove-set-item-btn" data-index="${index}"
                  style="color: #ef4444; background: none; border: none; cursor: pointer; font-size: 20px; padding: 4px 8px; line-height: 1;">
            ×
          </button>
        </div>
      `;

      // For File-based photos: read asynchronously and populate thumbnail + cache as photoURL
      if (primaryPhoto) {
        const capturedItem = item; // Closure capture for async callback
        const reader = new FileReader();
        reader.onload = (e) => {
          capturedItem.photoURL = e.target.result; // Cache so future re-renders use URL directly
          const thumb = itemDiv.querySelector('.item-thumbnail');
          if (thumb) thumb.src = e.target.result;
        };
        reader.readAsDataURL(primaryPhoto);
      }

      // Add hidden inputs for backend submission (exclude photo and photoURL — both are
      // display-only; actual photo files are appended to FormData directly at submit time)
      Object.keys(item).forEach(key => {
        if (key !== 'photo' && key !== 'photoURL') {
          const hiddenInput = document.createElement('input');
          hiddenInput.type = 'hidden';
          hiddenInput.name = `set_items[${index + 1}][${key}]`;
          hiddenInput.value = item[key] || '';
          itemDiv.appendChild(hiddenInput);
        }
      });

      setItemsList.appendChild(itemDiv);
    });

    // Update item count label
    if (setItems.length > 0) {
      setItemLabel.textContent = `Set Item #${setItems.length + 1}`;
    } else {
      setItemLabel.textContent = 'Set Item #1';
    }
  }

  // Export renderSetItems for use in sidebar script
  window.renderSetItems = renderSetItems;

  // Add set item button handler
  addSetItemBtn.addEventListener('click', function() {
    // Validate current fields
    const specs = captureSpecValues();
    const itemNumber = setItems.length + 1; // Current item being added

    // Validation rules based on item number
    if (itemNumber <= 2) {
      // First 2 items: ALL dropdowns + photo + quantity required
      if (!specs.metal || !specs.product_line || !specs.product_type || !specs.weight ||
          !specs.purity || !specs.mint || !specs.year || !specs.finish) {
        alert('First two items require ALL Product Specification fields to be filled.');
        return;
      }

      if (!specs.photo) {
        alert('First two items require a photo to be uploaded.');
        return;
      }
    } else {
      // Items 3+: Only photo required, dropdowns optional
      if (!specs.photo) {
        alert('Please upload a photo for this item.');
        return;
      }
    }

    // Add to array
    setItems.push(specs);
    setItemCount++;

    // Render updated list (use window.renderSetItems so sidebar hook fires)
    window.renderSetItems();

    // Clear fields for next item
    clearSpecFields();

    // Update checklist so toggleCurrentItemRequiredAttributes fires immediately
    // (ensures HTML required attributes are removed from spec fields when 2+ items exist)
    if (typeof window.updateChecklist === 'function') {
      window.updateChecklist();
    }

    // Focus first field
    document.getElementById('metal').focus();
  });

  // Remove set item handler (event delegation)
  setItemsList.addEventListener('click', function(e) {
    if (e.target.classList.contains('remove-set-item-btn')) {
      const index = parseInt(e.target.getAttribute('data-index'));
      setItems.splice(index, 1);
      setItemCount--;
      window.renderSetItems();

      // Update checklist immediately to reflect removed item
      if (typeof window.updateChecklist === 'function') {
        window.updateChecklist();
      }
    }
  });

  // ========== AUTOSAVE DRAFT FUNCTIONS ==========
  function scheduleAutosave() {
    if (autosaveTimeout) clearTimeout(autosaveTimeout);
    autosaveTimeout = setTimeout(saveDraft, AUTOSAVE_DEBOUNCE_MS);
  }

  function saveDraft() {
    const draft = {
      mode: window.currentMode,
      metal: document.getElementById('metal').value,
      product_line: document.getElementById('product_line').value,
      product_type: document.getElementById('product_type').value,
      weight: document.getElementById('weight').value,
      purity: document.getElementById('purity').value,
      mint: document.getElementById('mint').value,
      year: document.getElementById('year').value,
      finish: document.getElementById('finish').value,
      series_variant: document.getElementById('series_variant').value,
      condition_notes: document.getElementById('condition_notes').value,
      listing_title: listingTitleInput.value,
      listing_description: document.getElementById('listing_description').value,
      packaging_type: document.getElementById('packaging_type').value,
      packaging_notes: document.getElementById('packaging_notes').value,
      quantity: quantityInput.value,
      pricing_mode: document.querySelector('input[name="pricing_mode"]:checked')?.value || 'static',
      price_per_coin: document.getElementById('price_per_coin').value,
      spot_premium: document.getElementById('spot_premium').value,
      floor_price: document.getElementById('floor_price').value,
      pricing_metal: document.getElementById('pricing_metal').value,
      setItems: setItems.map(item => ({
        ...item,
        photo: null // Can't store File objects in localStorage
      })),
      timestamp: Date.now()
    };

    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
      console.log('[Autosave] Draft saved');
    } catch (e) {
      console.error('[Autosave] Failed to save draft:', e);
    }
  }

  function loadDraft() {
    try {
      const draftStr = localStorage.getItem(DRAFT_KEY);
      if (!draftStr) return false;

      const draft = JSON.parse(draftStr);

      // Restore mode
      if (draft.mode === 'standard') modeStandard.checked = true;
      else if (draft.mode === 'isolated') modeIsolated.checked = true;
      else if (draft.mode === 'set') modeSet.checked = true;
      updateUIForMode(draft.mode);

      // Restore form fields
      if (draft.metal) document.getElementById('metal').value = draft.metal;
      if (draft.product_line) document.getElementById('product_line').value = draft.product_line;
      if (draft.product_type) document.getElementById('product_type').value = draft.product_type;
      if (draft.weight) document.getElementById('weight').value = draft.weight;
      if (draft.purity) document.getElementById('purity').value = draft.purity;
      if (draft.mint) document.getElementById('mint').value = draft.mint;
      if (draft.year) document.getElementById('year').value = draft.year;
      if (draft.finish) document.getElementById('finish').value = draft.finish;
      if (draft.series_variant) document.getElementById('series_variant').value = draft.series_variant;
      if (draft.condition_notes) document.getElementById('condition_notes').value = draft.condition_notes;
      if (draft.listing_title) listingTitleInput.value = draft.listing_title;
      if (draft.listing_description) document.getElementById('listing_description').value = draft.listing_description;
      if (draft.packaging_type) document.getElementById('packaging_type').value = draft.packaging_type;
      if (draft.packaging_notes) document.getElementById('packaging_notes').value = draft.packaging_notes;
      if (draft.quantity) quantityInput.value = draft.quantity;

      // Restore pricing
      if (draft.pricing_mode) {
        const pricingModeRadio = document.getElementById(draft.pricing_mode === 'static' ? 'pricing_mode_static' : 'pricing_mode_premium');
        if (pricingModeRadio) pricingModeRadio.checked = true;
      }
      if (draft.price_per_coin) document.getElementById('price_per_coin').value = draft.price_per_coin;
      if (draft.spot_premium) document.getElementById('spot_premium').value = draft.spot_premium;
      if (draft.floor_price) document.getElementById('floor_price').value = draft.floor_price;
      if (draft.pricing_metal) document.getElementById('pricing_metal').value = draft.pricing_metal;

      // Restore set items (without photos)
      if (draft.setItems && draft.setItems.length > 0) {
        setItems = draft.setItems;
        window.renderSetItems();
        // Update the label to reflect restored items
        if (setItemLabel) {
          setItemLabel.textContent = `Set Item #${setItems.length + 1}`;
        }
      }

      console.log('[Autosave] Draft loaded');
      return true;
    } catch (e) {
      console.error('[Autosave] Failed to load draft:', e);
      return false;
    }
  }

  function clearDraft() {
    if (confirm('Clear saved draft? This will remove all autosaved data.')) {
      localStorage.removeItem(DRAFT_KEY);
      console.log('[Autosave] Draft cleared');
      location.reload();
    }
  }

  // Autosave listeners DISABLED - form should not persist on reload
  // const formInputs = sellForm.querySelectorAll('input, textarea, select');
  // formInputs.forEach(input => {
  //   input.addEventListener('input', scheduleAutosave);
  //   input.addEventListener('change', scheduleAutosave);
  // });

  // Clear any saved draft on page load (autosave disabled)
  window.addEventListener('DOMContentLoaded', () => {
    // Clear any previously saved draft - we don't want form persistence on reload
    localStorage.removeItem(DRAFT_KEY);
    console.log('[Autosave] Draft cleared on page load - autosave disabled');

    // Ensure sidebar visibility matches current mode
    if (typeof window.updateChecklistVisibility === 'function') {
      window.updateChecklistVisibility();
    }

    // Update checklist and summary
    if (typeof window.updateSidebarSummary === 'function') {
      window.updateSidebarSummary();
    }
    if (typeof window.updateSidebarChecklist === 'function') {
      window.updateSidebarChecklist();
    }
  });

  // Clear draft button removed (previously shown in bottom right)

  // Form validation before submit
  sellForm.addEventListener('submit', function(e) {
    const isSet = (window.currentMode === 'set');

    // Validate photo file sizes before submission
    const maxFileSize = 20 * 1024 * 1024; // 20MB per file
    const maxTotalSize = 100 * 1024 * 1024; // 100MB total
    let totalSize = 0;
    const allPhotos = [];

    // Check cover photo (for set/isolated listings)
    if (coverPhotoInput && coverPhotoInput.files.length > 0) {
      const file = coverPhotoInput.files[0];
      if (file.size > maxFileSize) {
        e.preventDefault();
        const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
        alert(`Cover photo is too large (${sizeMB}MB). Maximum size per photo is 20MB. Please resize or compress the image.`);
        return false;
      }
      allPhotos.push(file);
      totalSize += file.size;
    }

    // Check item photos (for standard listings - now uses multi-photo)
    if (window.currentMode === 'standard') {
      const standardPhotos = window.currentItemPhotos || [];
      for (let i = 0; i < standardPhotos.length; i++) {
        const file = standardPhotos[i];
        if (file.size > maxFileSize) {
          e.preventDefault();
          const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
          alert(`Item photo #${i + 1} is too large (${sizeMB}MB). Maximum size per photo is 20MB. Please resize or compress the image.`);
          return false;
        }
        allPhotos.push(file);
        totalSize += file.size;
      }
    } else if (itemPhotoInput && itemPhotoInput.files.length > 0) {
      // Isolated mode: single photo
      const file = itemPhotoInput.files[0];
      if (file.size > maxFileSize) {
        e.preventDefault();
        const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
        alert(`Item photo is too large (${sizeMB}MB). Maximum size per photo is 20MB. Please resize or compress the image.`);
        return false;
      }
      allPhotos.push(file);
      totalSize += file.size;
    }

    // Check set item photos
    if (isSet && setItems.length > 0) {
      for (let i = 0; i < setItems.length; i++) {
        const item = setItems[i];
        if (item.photo) {
          const photos = Array.isArray(item.photo) ? item.photo : [item.photo];
          for (let j = 0; j < photos.length; j++) {
            const file = photos[j];
            if (file.size > maxFileSize) {
              e.preventDefault();
              const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
              alert(`Set item #${i + 1} photo #${j + 1} is too large (${sizeMB}MB). Maximum size per photo is 20MB. Please resize or compress the image.`);
              return false;
            }
            allPhotos.push(file);
            totalSize += file.size;
          }
        }
      }
    }

    // Check total payload size
    if (totalSize > maxTotalSize) {
      e.preventDefault();
      const totalMB = (totalSize / (1024 * 1024)).toFixed(1);
      alert(`Total photo size is too large (${totalMB}MB). Maximum total size is 100MB. Please use fewer photos or compress them.`);
      return false;
    }

    // Validate set has at least 2 items committed to the array
    if (isSet && setItems.length < 2) {
      e.preventDefault();
      alert('A set listing must contain at least 2 items. Please add at least 2 items to the set before submitting.');
      return false;
    }

    // Validate cover photo for One-of-a-Kind and Set listings
    // Recognises both a newly selected file AND an already-attached existing photo
    // (tracked by the has-image class or dataset.existingPhotoId set during edit-mode prefill).
    const needsCoverPhoto = (window.currentMode === 'isolated' || window.currentMode === 'set');
    if (needsCoverPhoto) {
      const hasCoverPhoto = (coverPhotoInput && coverPhotoInput.files.length > 0) ||
                            (coverPhotoBox && coverPhotoBox.classList.contains('has-image')) ||
                            (coverPhotoBox && coverPhotoBox.dataset.existingPhotoId);
      if (!hasCoverPhoto) {
        e.preventDefault();
        const modeLabel = window.currentMode === 'set' ? 'set' : 'one-of-a-kind';
        alert(`Please upload a cover photo for your ${modeLabel} listing.`);
        coverPhotoInput.focus();
        return false;
      }
    }

    // Validate listing title for One-of-a-Kind and Set listings
    if (needsCoverPhoto && !listingTitleInput.value.trim()) {
      e.preventDefault();
      alert('Please provide a listing title for this type of listing.');
      listingTitleInput.focus();
      return false;
    }

    // NOTE: Photo attachment for set items is now handled by window.attachSetItemPhotos()
    // which is called explicitly from sell_listing_modals.js BEFORE creating FormData.
    // This ensures correct execution order.

    // For set listings, ensure main quantity is always 1 (one set per listing)
    if (isSet) {
      quantityInput.value = '1';
    }

    // DEBUG: Log form data size before submission
    console.log('=== FORM SUBMISSION DEBUG ===');
    console.log('Form action:', sellForm.action);
    console.log('Form method:', sellForm.method);
    console.log('Form enctype:', sellForm.enctype);

    const formData = new FormData(sellForm);
    let debugTotalSize = 0;
    let fileCount = 0;

    for (let [name, value] of formData.entries()) {
      if (value instanceof File) {
        console.log(`File: ${name} = ${value.name} (${(value.size / 1024).toFixed(1)}KB)`);
        debugTotalSize += value.size;
        fileCount++;
      } else if (typeof value === 'string' && value.length > 100) {
        console.log(`Field: ${name} = [${value.length} chars]`);
      } else {
        console.log(`Field: ${name} = ${value}`);
      }
    }

    console.log(`Total files: ${fileCount}`);
    console.log(`Total file size: ${(debugTotalSize / 1024).toFixed(1)}KB (${(debugTotalSize / (1024 * 1024)).toFixed(2)}MB)`);
    console.log('=== END DEBUG ===');
  });

  // Expose currentItemPhotos for checklist access
  window.currentItemPhotos = currentItemPhotos;

  /**
   * CRITICAL: Attach set item photos to form before submission
   * Must be called BEFORE creating FormData
   */
  window.attachSetItemPhotos = function() {
    const sellForm = document.getElementById('sellForm');
    const isSet = (window.currentMode === 'set');
    const setItems = window.setItems || [];

    if (!isSet || setItems.length === 0) {
      console.log('🔴 [ATTACH] Not a set or no items, skipping photo attachment');
      return;
    }

    console.log('🔴 [ATTACH] SET PHOTO ATTACHMENT CODE RUNNING');
    console.log('🔴 [ATTACH] isSet:', isSet, 'setItems.length:', setItems.length);
    console.log('🔴 [ATTACH] setItems array:', setItems);

    // DEBUG: Check what set_items hidden inputs exist in the form
    const setItemHiddenInputs = sellForm.querySelectorAll('input[name^="set_items["]');
    console.log(`🔴 [ATTACH] Found ${setItemHiddenInputs.length} set_items hidden inputs in form`);
    const uniqueIndices = new Set();
    setItemHiddenInputs.forEach(input => {
      const match = input.name.match(/set_items\[(\d+)\]/);
      if (match) uniqueIndices.add(match[1]);
    });
    console.log('🔴 [ATTACH] Unique set_items indices:', Array.from(uniqueIndices).sort());

    // Remove any previously appended set_item_photo_* inputs to prevent duplication
    const existingPhotoInputs = sellForm.querySelectorAll('input[name^="set_item_photo_"]');
    existingPhotoInputs.forEach(input => input.remove());
    console.log(`🔴 [ATTACH] Removed ${existingPhotoInputs.length} existing set photo inputs`);

    setItems.forEach((item, index) => {
      if (item.photo) {
        const photos = Array.isArray(item.photo) ? item.photo : [item.photo];

        // CRITICAL: Use 1-based indexing to match backend expectations
        // Backend expects set_item_photo_{1-based-index}_{photo-position}
        // to match form data naming: set_items[1], set_items[2], etc.
        const oneBasedIndex = index + 1;

        for (let photoIndex = 0; photoIndex < photos.length && photoIndex < 3; photoIndex++) {
          const photoFile = photos[photoIndex];
          if (photoFile) {
            const fileInput = document.createElement('input');
            fileInput.type = 'file';
            fileInput.name = `set_item_photo_${oneBasedIndex}_${photoIndex + 1}`;
            fileInput.style.display = 'none';
            fileInput.dataset.setHidden = '1';

            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(photoFile);
            fileInput.files = dataTransfer.files;

            sellForm.appendChild(fileInput);
            console.log(`🔴 [ATTACH] APPENDED: ${fileInput.name} (${(photoFile.size / 1024).toFixed(1)}KB)`);
          }
        }
      }
    });

    console.log('🔴 [ATTACH] Photo attachment complete');
  };

  /**
   * CRITICAL: Attach standard mode item photos to form before submission
   * Must be called BEFORE creating FormData
   */
  window.attachStandardItemPhotos = function() {
    const sellForm = document.getElementById('sellForm');
    const isStandard = (window.currentMode === 'standard');
    const standardPhotos = window.currentItemPhotos || [];

    if (!isStandard || standardPhotos.length === 0) {
      console.log('🔴 [ATTACH STANDARD] Not standard mode or no photos, skipping');
      return;
    }

    console.log('🔴 [ATTACH STANDARD] Attaching', standardPhotos.length, 'photos');

    // Remove any previously appended standard_item_photo_* inputs to prevent duplication
    const existingPhotoInputs = sellForm.querySelectorAll('input[name^="item_photo_"]');
    existingPhotoInputs.forEach(input => input.remove());

    standardPhotos.forEach((photoFile, index) => {
      if (photoFile) {
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.name = `item_photo_${index + 1}`;
        fileInput.style.display = 'none';
        fileInput.dataset.standardHidden = '1';

        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(photoFile);
        fileInput.files = dataTransfer.files;

        sellForm.appendChild(fileInput);
        console.log(`🔴 [ATTACH STANDARD] APPENDED: ${fileInput.name} (${(photoFile.size / 1024).toFixed(1)}KB)`);
      }
    });

    console.log('🔴 [ATTACH STANDARD] Photo attachment complete');
  };
})();
