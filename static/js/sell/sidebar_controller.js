/**
 * Sell Page Sidebar Controller
 *
 * Handles sticky sidebar functionality, checklist updates,
 * summary display, set item rendering in sidebar, and CTA button state.
 *
 * Extracted from templates/sell.html inline script during refactor.
 * NO BEHAVIOR CHANGES - structure only.
 */
// ========== STICKY SIDEBAR FUNCTIONALITY ==========
(function() {
  'use strict';

  console.log('[SELL SIDEBAR] Script loaded v3', new Date().toISOString());

  // Sidebar elements
  const sidebarSubmitBtn = document.getElementById('sidebarSubmitBtn');
  const sidebarAddSetItemBtn = document.getElementById('sidebarAddSetItemBtn');
  const sidebarSetItemsList = document.getElementById('sidebarSetItemsList');

  // Sidebar sections (for show/hide by mode)
  const sidebarChecklistStandard = document.getElementById('sidebarChecklistStandard');
  const sidebarCurrentItemSection = document.getElementById('sidebarCurrentItemSection');
  const sidebarSetListingSection = document.getElementById('sidebarSetListingSection');

  console.log('[SELL SIDEBAR] Elements queried', {
    sidebarSubmitBtn: !!sidebarSubmitBtn,
    sidebarChecklistStandard: !!sidebarChecklistStandard,
    sidebarCurrentItemSection: !!sidebarCurrentItemSection,
    sidebarSetListingSection: !!sidebarSetListingSection
  });

  // Summary elements
  const summaryItem = document.getElementById('summaryItem');
  const summaryMetal = document.getElementById('summaryMetal');
  const summaryPrice = document.getElementById('summaryPrice');
  const summaryQuantity = document.getElementById('summaryQuantity');
  const summaryQuantityRow = document.getElementById('summaryQuantityRow');

  // Standard checklist elements (for Standard & One-of-a-Kind modes)
  const checkProductSpecs = document.getElementById('checkProductSpecs');
  const checkPackaging = document.getElementById('checkPackaging');
  const checkItemPhoto = document.getElementById('checkItemPhoto');
  const checkCoverPhoto = document.getElementById('checkCoverPhoto');
  const checkPricing = document.getElementById('checkPricing');
  const checkQuantity = document.getElementById('checkQuantity');

  // Current Item checklist elements (for Set mode)
  const checkCurrentSpecs = document.getElementById('checkCurrentSpecs');
  const checkCurrentPhoto = document.getElementById('checkCurrentPhoto');

  console.log('[SELL SIDEBAR] CRITICAL - Checklist elements found?', {
    checkProductSpecs: !!checkProductSpecs,
    checkPackaging: !!checkPackaging,
    checkItemPhoto: !!checkItemPhoto,
    checkCoverPhoto: !!checkCoverPhoto,
    checkPricing: !!checkPricing,
    checkQuantity: !!checkQuantity,
    checkCurrentSpecs: !!checkCurrentSpecs,
    checkCurrentPhoto: !!checkCurrentPhoto
  });

  // Set Listing checklist elements (for Set mode)
  const checkSetItems = document.getElementById('checkSetItems');
  const checkSetCoverPhoto = document.getElementById('checkSetCoverPhoto');
  const checkSetTitle = document.getElementById('checkSetTitle');
  const checkSetPrice = document.getElementById('checkSetPrice');

  // Form inputs
  const productLineInput = document.getElementById('product_line');
  const metalInput = document.getElementById('metal');
  const packagingInput = document.getElementById('packaging_type');
  const pricePerCoinInput = document.getElementById('price_per_coin');
  const spotPremiumInput = document.getElementById('spot_premium');
  const floorPriceInput = document.getElementById('floor_price');
  const quantityInput = document.getElementById('quantity');
  const itemPhotoInput = document.getElementById('item_photo');
  const coverPhotoInput = document.getElementById('cover_photo');
  const listingTitleInput = document.getElementById('listing_title');

  // Note: currentMode is defined as window.currentMode in main script (no need for duplicate declaration)

  // ========== UPDATE SIDEBAR SUMMARY ==========
  function updateSidebarSummary() {
    // Update Item
    const productLine = productLineInput?.value?.trim();
    if (productLine) {
      summaryItem.textContent = productLine;
      summaryItem.classList.remove('empty');
    } else {
      summaryItem.textContent = 'Not specified';
      summaryItem.classList.add('empty');
    }

    // Update Metal
    const metal = metalInput?.value?.trim();
    if (metal) {
      summaryMetal.textContent = metal;
      summaryMetal.classList.remove('empty');
    } else {
      summaryMetal.textContent = '—';
      summaryMetal.classList.add('empty');
    }

    // Update Price
    let priceText = '—';
    const pricingMode = document.querySelector('input[name="pricing_mode"]:checked')?.value;

    if (pricingMode === 'static') {
      const price = pricePerCoinInput?.value?.trim();
      if (price && parseFloat(price) > 0) {
        priceText = formatPrice(parseFloat(price));
      }
    } else if (pricingMode === 'premium_to_spot') {
      const premium = spotPremiumInput?.value?.trim();
      const floor = floorPriceInput?.value?.trim();
      if (premium || floor) {
        priceText = 'Premium to Spot';
      }
    }

    summaryPrice.textContent = priceText;
    if (priceText === '—') {
      summaryPrice.classList.add('empty');
    } else {
      summaryPrice.classList.remove('empty');
    }

    // Update Quantity (hide for isolated/set modes)
    if (window.currentMode === 'isolated' || window.currentMode === 'set') {
      summaryQuantityRow.style.display = 'none';
    } else {
      summaryQuantityRow.style.display = 'flex';
      const qty = quantityInput?.value?.trim();
      if (qty && parseInt(qty) > 0) {
        summaryQuantity.textContent = qty;
        summaryQuantity.classList.remove('empty');
      } else {
        summaryQuantity.textContent = '—';
        summaryQuantity.classList.add('empty');
      }
    }
  }

  // ========== TOGGLE REQUIRED ATTRIBUTES ON CURRENT ITEM FIELDS ==========
  // Make this a window-level function so it can be called from both script blocks
  window.toggleCurrentItemRequiredAttributes = function() {
    // List of all current-item product spec field IDs that have required constraints
    const requiredFieldIds = [
      'metal', 'product_line', 'product_type', 'weight',
      'purity', 'mint', 'year', 'finish'
    ];

    // In Set mode with 2+ items, current-item fields should NOT be required for final submission
    // (They ARE still required when adding items via "Add Item to Set" button, but that uses JS validation)
    const shouldBeOptional = (window.currentMode === 'set' && (window.setItems || []).length >= 2);

    requiredFieldIds.forEach(fieldId => {
      const field = document.getElementById(fieldId);
      if (field) {
        if (shouldBeOptional) {
          // Remove required constraint (makes field optional for form submission)
          field.removeAttribute('required');
        } else {
          // Add required constraint (enforces validation on form submission)
          field.setAttribute('required', '');
        }
      }
    });
  };

  // ========== UPDATE CURRENT ITEM CHECKLIST (Set mode) ==========
  function updateCurrentItemChecklist() {
    if (window.currentMode !== 'set') return;

    // Show/hide "Optional" note based on whether 2+ items already exist
    const items = window.setItems || [];
    const currentItemOptionalNote = document.getElementById('currentItemOptionalNote');
    const currentItemChecklist = document.getElementById('sidebarCurrentItemChecklist');
    const currentItemTitle = document.getElementById('sidebarCurrentItemTitle');
    const isOptional = items.length >= 2;

    if (currentItemOptionalNote) {
      currentItemOptionalNote.style.display = isOptional ? 'block' : 'none';
    }

    // Visually deemphasize current item section when optional (2+ items exist)
    if (currentItemChecklist) {
      currentItemChecklist.style.opacity = isOptional ? '0.5' : '1';
    }
    if (currentItemTitle) {
      currentItemTitle.style.opacity = isOptional ? '0.6' : '1';
    }

    // Toggle required attributes based on set items count
    if (window.toggleCurrentItemRequiredAttributes) {
      window.toggleCurrentItemRequiredAttributes();
    }

    // Current Item Specs Complete (check ALL required spec fields)
    const productType = document.getElementById('product_type')?.value?.trim();
    const weight = document.getElementById('weight')?.value?.trim();
    const purity = document.getElementById('purity')?.value?.trim();
    const mint = document.getElementById('mint')?.value?.trim();
    const year = document.getElementById('year')?.value?.trim();
    const finish = document.getElementById('finish')?.value?.trim();
    const seriesVariant = document.getElementById('series_variant')?.value?.trim();

    const allSpecsComplete = !!(
      productLineInput?.value?.trim() &&
      metalInput?.value?.trim() &&
      productType &&
      weight &&
      purity &&
      mint &&
      year &&
      finish &&
      seriesVariant
    );
    toggleChecklistItem(checkCurrentSpecs, allSpecsComplete);

    // Current Item Photo Uploaded (use currentItemPhotos array for Set mode multi-photo)
    const currentPhotos = window.currentItemPhotos || [];
    const hasPhoto = currentPhotos.length > 0;
    toggleChecklistItem(checkCurrentPhoto, hasPhoto);

    // Update "Add Item to Set" button state
    updateAddItemButtonState();
  }

  // ========== UPDATE SET LEVEL CHECKLIST (Set mode) ==========
  function updateSetLevelChecklist() {
    if (window.currentMode !== 'set') return;

    const items = window.setItems || [];

    // 2+ set items added
    toggleChecklistItem(checkSetItems, items.length >= 2);

    // Set cover photo uploaded
    const setCoverPhotoBox = document.getElementById('coverPhotoUploadBox');
    const hasCoverPhoto =
      coverPhotoInput?.files?.length > 0 ||
      setCoverPhotoBox?.classList.contains('has-image');
    toggleChecklistItem(checkSetCoverPhoto, hasCoverPhoto);

    // Listing title provided
    toggleChecklistItem(checkSetTitle, listingTitleInput?.value?.trim());

    // Price configured
    const pricingMode = document.querySelector('input[name="pricing_mode"]:checked')?.value;
    let priceConfigured = false;
    if (pricingMode === 'static') {
      priceConfigured = pricePerCoinInput?.value?.trim() && parseFloat(pricePerCoinInput.value) > 0;
    } else if (pricingMode === 'premium_to_spot') {
      const premium = spotPremiumInput?.value?.trim();
      const floor = floorPriceInput?.value?.trim();
      priceConfigured = (premium || floor);
    }
    toggleChecklistItem(checkSetPrice, priceConfigured);

    // Update "Create Set Listing" button state
    updateCTAButton();
  }

  // ========== UPDATE CHECKLIST (Main function - delegates by mode) ==========
  function updateChecklist() {
    console.log('[SELL SIDEBAR] updateChecklist fired', {
      currentMode: window.currentMode,
      timestamp: new Date().toISOString()
    });

    if (window.currentMode === 'set') {
      // Set mode: update both checklists
      console.log('[SELL SIDEBAR] Updating Set mode checklists');
      updateCurrentItemChecklist();
      updateSetLevelChecklist();
    } else if (window.currentMode === 'standard') {
      console.log('[SELL SIDEBAR] Updating Standard mode checklist');
      // Standard mode
      // 1. Product Specs Complete (all required product spec fields filled)
      const productType = document.getElementById('product_type')?.value?.trim();
      const weight = document.getElementById('weight')?.value?.trim();
      const purity = document.getElementById('purity')?.value?.trim();
      const mint = document.getElementById('mint')?.value?.trim();
      const year = document.getElementById('year')?.value?.trim();
      const finish = document.getElementById('finish')?.value?.trim();
      const seriesVariant = document.getElementById('series_variant')?.value?.trim();

      const productSpecsComplete = !!(
        productLineInput?.value?.trim() &&
        metalInput?.value?.trim() &&
        productType &&
        weight &&
        purity &&
        mint &&
        year &&
        finish &&
        seriesVariant
      );
      console.log('[SELL SIDEBAR] Standard - Specs check:', {
        productLine: productLineInput?.value,
        metal: metalInput?.value,
        productType,
        weight,
        complete: productSpecsComplete,
        checkProductSpecs: !!checkProductSpecs
      });
      toggleChecklistItem(checkProductSpecs, productSpecsComplete);

      // 2. Packaging Selected (optional in edit mode if listing had no packaging)
      const packagingOk = window.sellEditMode
        ? true
        : packagingInput?.value?.trim();
      toggleChecklistItem(checkPackaging, packagingOk);

      // 3. Item Photo Uploaded (>=1 PNG) - Standard mode uses file inputs
      // Check if any of the standard photo inputs have files OR boxes have images
      const photo1Input = document.getElementById('item_photo_1');
      const photo2Input = document.getElementById('item_photo_2');
      const photo3Input = document.getElementById('item_photo_3');
      const photoBox1 = document.getElementById('standardPhotoBox1');
      const photoBox2 = document.getElementById('standardPhotoBox2');
      const photoBox3 = document.getElementById('standardPhotoBox3');

      // In edit mode, existing photos (tracked by keep_photo_ids) count as uploaded
      const hasExistingPhotos = window.sellEditMode &&
        (document.getElementById('keepPhotoIds')?.value?.length > 0 ||
         (window.sellPrefillData?.existing_photos?.length > 0));
      const itemPhotoUploaded =
        hasExistingPhotos ||
        (photo1Input?.files?.length > 0) ||
        (photo2Input?.files?.length > 0) ||
        (photo3Input?.files?.length > 0) ||
        photoBox1?.classList.contains('has-image') ||
        photoBox2?.classList.contains('has-image') ||
        photoBox3?.classList.contains('has-image');
      toggleChecklistItem(checkItemPhoto, itemPhotoUploaded);

      // 4. Cover Photo - hide in standard mode
      checkCoverPhoto.style.display = 'none';

      // 5. Pricing Complete (mode-aware: fixed OR premium fields valid)
      const pricingMode = document.querySelector('input[name="pricing_mode"]:checked')?.value;
      let pricingComplete = false;
      if (pricingMode === 'static') {
        pricingComplete = pricePerCoinInput?.value?.trim() && parseFloat(pricePerCoinInput.value) > 0;
      } else if (pricingMode === 'premium_to_spot') {
        const premium = spotPremiumInput?.value?.trim();
        const floor = floorPriceInput?.value?.trim();
        pricingComplete = (premium && floor);
      }
      toggleChecklistItem(checkPricing, pricingComplete);

      // 6. Quantity Set (positive integer)
      const qty = quantityInput?.value?.trim();
      toggleChecklistItem(checkQuantity, qty && parseInt(qty) > 0);

      // Update CTA button
      updateCTAButton();
    } else if (window.currentMode === 'isolated') {
      // One-of-a-Kind mode
      // 1. Product Specs Complete
      const productType = document.getElementById('product_type')?.value?.trim();
      const weight = document.getElementById('weight')?.value?.trim();
      const purity = document.getElementById('purity')?.value?.trim();
      const mint = document.getElementById('mint')?.value?.trim();
      const year = document.getElementById('year')?.value?.trim();
      const finish = document.getElementById('finish')?.value?.trim();
      const seriesVariant = document.getElementById('series_variant')?.value?.trim();

      const productSpecsComplete = !!(
        productLineInput?.value?.trim() &&
        metalInput?.value?.trim() &&
        productType &&
        weight &&
        purity &&
        mint &&
        year &&
        finish &&
        seriesVariant
      );
      toggleChecklistItem(checkProductSpecs, productSpecsComplete);

      // 2. Packaging Selected (use item_packaging_type for one-of-a-kind mode; optional in edit mode)
      const itemPackagingInput = document.getElementById('item_packaging_type');
      const itemPackagingOk = window.sellEditMode
        ? true
        : itemPackagingInput?.value?.trim();
      toggleChecklistItem(checkPackaging, itemPackagingOk);

      // 3. Item Photo Uploaded (>=1 PNG) - One-of-a-kind uses same photo boxes as standard
      const photo1Input = document.getElementById('item_photo_1');
      const photo2Input = document.getElementById('item_photo_2');
      const photo3Input = document.getElementById('item_photo_3');
      const photoBox1 = document.getElementById('standardPhotoBox1');
      const photoBox2 = document.getElementById('standardPhotoBox2');
      const photoBox3 = document.getElementById('standardPhotoBox3');

      // In edit mode, existing photos (tracked by keep_photo_ids) count as uploaded
      const hasExistingPhotosIsolated = window.sellEditMode &&
        (document.getElementById('keepPhotoIds')?.value?.length > 0 ||
         (window.sellPrefillData?.existing_photos?.length > 0));
      const itemPhotoUploaded =
        hasExistingPhotosIsolated ||
        (photo1Input?.files?.length > 0) ||
        (photo2Input?.files?.length > 0) ||
        (photo3Input?.files?.length > 0) ||
        photoBox1?.classList.contains('has-image') ||
        photoBox2?.classList.contains('has-image') ||
        photoBox3?.classList.contains('has-image');
      toggleChecklistItem(checkItemPhoto, itemPhotoUploaded);

      // 4. Cover Photo Uploaded (PNG required in one-of-a-kind mode)
      checkCoverPhoto.style.display = 'flex';
      const coverPhotoBox = document.getElementById('coverPhotoUploadBox');
      const coverPhotoUploaded =
        coverPhotoInput?.files?.length > 0 ||
        coverPhotoBox?.classList.contains('has-image');
      toggleChecklistItem(checkCoverPhoto, coverPhotoUploaded);

      // 5. Pricing Complete
      const pricingMode = document.querySelector('input[name="pricing_mode"]:checked')?.value;
      let pricingComplete = false;
      if (pricingMode === 'static') {
        pricingComplete = pricePerCoinInput?.value?.trim() && parseFloat(pricePerCoinInput.value) > 0;
      } else if (pricingMode === 'premium_to_spot') {
        const premium = spotPremiumInput?.value?.trim();
        const floor = floorPriceInput?.value?.trim();
        pricingComplete = (premium && floor);
      }
      toggleChecklistItem(checkPricing, pricingComplete);

      // 6. Quantity - hide in one-of-a-kind mode (spec says no quantity unless input exists)
      checkQuantity.style.display = 'none';

      // Update CTA button
      updateCTAButton();
    }
  }

  function toggleChecklistItem(element, isComplete) {
    if (!element) {
      console.warn('[SELL SIDEBAR] toggleChecklistItem called with NULL element!');
      return;
    }

    const icon = element.querySelector('.checklist-icon');
    if (!icon) {
      console.warn('[SELL SIDEBAR] No .checklist-icon found inside element:', element.id);
      return;
    }

    if (isComplete) {
      icon.classList.remove('incomplete');
      icon.classList.add('complete');
      element.classList.add('complete');
      console.log('[SELL SIDEBAR] ✓ Checked:', element.id);
    } else {
      icon.classList.add('incomplete');
      icon.classList.remove('complete');
      element.classList.remove('complete');
      console.log('[SELL SIDEBAR] ✗ Unchecked:', element.id);
    }
  }

  // ========== UPDATE CTA BUTTON ==========
  function updateCTAButton() {
    let allRequirementsMet = false;

    if (window.currentMode === 'standard') {
      // Standard: Product Specs Complete, Packaging Selected, Item Photo, Pricing Complete, Quantity Set
      const productType = document.getElementById('product_type')?.value?.trim();
      const weight = document.getElementById('weight')?.value?.trim();
      const purity = document.getElementById('purity')?.value?.trim();
      const mint = document.getElementById('mint')?.value?.trim();
      const year = document.getElementById('year')?.value?.trim();
      const finish = document.getElementById('finish')?.value?.trim();
      const seriesVariant = document.getElementById('series_variant')?.value?.trim();

      const productSpecsComplete = !!(
        productLineInput?.value?.trim() &&
        metalInput?.value?.trim() &&
        productType &&
        weight &&
        purity &&
        mint &&
        year &&
        finish &&
        seriesVariant
      );

      // In edit mode, packaging is optional
      const packagingSelected = window.sellEditMode ? true : packagingInput?.value?.trim();
      // Standard mode uses file inputs (item_photo_1, item_photo_2, item_photo_3)
      const photo1Input = document.getElementById('item_photo_1');
      const photo2Input = document.getElementById('item_photo_2');
      const photo3Input = document.getElementById('item_photo_3');
      const photoBox1 = document.getElementById('standardPhotoBox1');
      const photoBox2 = document.getElementById('standardPhotoBox2');
      const photoBox3 = document.getElementById('standardPhotoBox3');

      // In edit mode, existing photos count as uploaded
      const hasExistingPhotos = window.sellEditMode &&
        (document.getElementById('keepPhotoIds')?.value?.length > 0 ||
         (window.sellPrefillData?.existing_photos?.length > 0));
      const itemPhotoUploaded =
        hasExistingPhotos ||
        (photo1Input?.files?.length > 0) ||
        (photo2Input?.files?.length > 0) ||
        (photo3Input?.files?.length > 0) ||
        photoBox1?.classList.contains('has-image') ||
        photoBox2?.classList.contains('has-image') ||
        photoBox3?.classList.contains('has-image');

      const pricingMode = document.querySelector('input[name="pricing_mode"]:checked')?.value;
      let pricingComplete = false;
      if (pricingMode === 'static') {
        pricingComplete = pricePerCoinInput?.value?.trim() && parseFloat(pricePerCoinInput.value) > 0;
      } else if (pricingMode === 'premium_to_spot') {
        const premium = spotPremiumInput?.value?.trim();
        const floor = floorPriceInput?.value?.trim();
        pricingComplete = (premium && floor);
      }

      const quantitySet = quantityInput?.value?.trim() && parseInt(quantityInput.value) > 0;

      console.log('[CTA DEBUG - Standard]', {
        productSpecsComplete,
        packagingSelected: !!packagingSelected,
        itemPhotoUploaded,
        pricingComplete,
        quantitySet,
        pricingMode,
        details: {
          productLine: productLineInput?.value,
          metal: metalInput?.value,
          productType, weight, purity, mint, year, finish, seriesVariant,
          packaging: packagingInput?.value,
          photo1Files: photo1Input?.files?.length,
          photo1HasImage: photoBox1?.classList.contains('has-image'),
          pricePerCoin: pricePerCoinInput?.value,
          spotPremium: spotPremiumInput?.value,
          floorPrice: floorPriceInput?.value,
          quantity: quantityInput?.value
        }
      });

      allRequirementsMet = productSpecsComplete && packagingSelected && itemPhotoUploaded && pricingComplete && quantitySet;
    } else if (window.currentMode === 'isolated') {
      // One-of-a-Kind: Product Specs Complete, Packaging Selected, Item Photo, Cover Photo, Pricing Complete
      const productType = document.getElementById('product_type')?.value?.trim();
      const weight = document.getElementById('weight')?.value?.trim();
      const purity = document.getElementById('purity')?.value?.trim();
      const mint = document.getElementById('mint')?.value?.trim();
      const year = document.getElementById('year')?.value?.trim();
      const finish = document.getElementById('finish')?.value?.trim();
      const seriesVariant = document.getElementById('series_variant')?.value?.trim();

      const productSpecsComplete = !!(
        productLineInput?.value?.trim() &&
        metalInput?.value?.trim() &&
        productType &&
        weight &&
        purity &&
        mint &&
        year &&
        finish &&
        seriesVariant
      );

      // One-of-a-kind mode uses item_packaging_type (product specs); optional in edit mode
      const itemPackagingInput = document.getElementById('item_packaging_type');
      const packagingSelected = window.sellEditMode ? true : itemPackagingInput?.value?.trim();

      // One-of-a-kind uses same photo boxes as standard mode
      const photo1Input = document.getElementById('item_photo_1');
      const photo2Input = document.getElementById('item_photo_2');
      const photo3Input = document.getElementById('item_photo_3');
      const photoBox1 = document.getElementById('standardPhotoBox1');
      const photoBox2 = document.getElementById('standardPhotoBox2');
      const photoBox3 = document.getElementById('standardPhotoBox3');

      // In edit mode, existing photos count as uploaded
      const hasExistingPhotosIsolated = window.sellEditMode &&
        (document.getElementById('keepPhotoIds')?.value?.length > 0 ||
         (window.sellPrefillData?.existing_photos?.length > 0));
      const itemPhotoUploaded =
        hasExistingPhotosIsolated ||
        (photo1Input?.files?.length > 0) ||
        (photo2Input?.files?.length > 0) ||
        (photo3Input?.files?.length > 0) ||
        photoBox1?.classList.contains('has-image') ||
        photoBox2?.classList.contains('has-image') ||
        photoBox3?.classList.contains('has-image');
      // In edit mode, cover photo is optional (existing listing already has photos)
      const coverPhotoUploaded = window.sellEditMode ? true : (coverPhotoInput?.files?.length > 0);

      const pricingMode = document.querySelector('input[name="pricing_mode"]:checked')?.value;
      let pricingComplete = false;
      if (pricingMode === 'static') {
        pricingComplete = pricePerCoinInput?.value?.trim() && parseFloat(pricePerCoinInput.value) > 0;
      } else if (pricingMode === 'premium_to_spot') {
        const premium = spotPremiumInput?.value?.trim();
        const floor = floorPriceInput?.value?.trim();
        pricingComplete = (premium && floor);
      }

      console.log('[CTA DEBUG - Isolated]', {
        productSpecsComplete,
        packagingSelected: !!packagingSelected,
        itemPhotoUploaded,
        coverPhotoUploaded,
        pricingComplete,
        pricingMode,
        details: {
          photo1Files: photo1Input?.files?.length,
          photo1HasImage: photoBox1?.classList.contains('has-image'),
          coverPhotoFiles: coverPhotoInput?.files?.length
        }
      });

      allRequirementsMet = productSpecsComplete && packagingSelected && itemPhotoUploaded && coverPhotoUploaded && pricingComplete;
    } else if (window.currentMode === 'set') {
      // Set: 2+ items added, Listing Title, Set Cover Photo, Pricing Complete
      const items = window.setItems || [];
      const allItemsHavePhotos = items.length >= 2 && items.every(item => {
        // Handle both photo arrays (new multi-photo) and single photos
        if (Array.isArray(item.photo)) {
          return item.photo.length > 0;
        }
        return item.photo || item.photoURL;
      });

      const pricingMode = document.querySelector('input[name="pricing_mode"]:checked')?.value;
      let pricingComplete = false;
      if (pricingMode === 'static') {
        pricingComplete = pricePerCoinInput?.value?.trim() && parseFloat(pricePerCoinInput.value) > 0;
      } else if (pricingMode === 'premium_to_spot') {
        const premium = spotPremiumInput?.value?.trim();
        const floor = floorPriceInput?.value?.trim();
        pricingComplete = (premium && floor);
      }

      const setCoverPhotoBoxCTA = document.getElementById('coverPhotoUploadBox');
      const hasCoverPhotoCTA =
        coverPhotoInput?.files?.length > 0 ||
        setCoverPhotoBoxCTA?.classList.contains('has-image');

      allRequirementsMet = (
        allItemsHavePhotos &&
        listingTitleInput?.value?.trim() &&
        hasCoverPhotoCTA &&
        pricingComplete
      );
    }

    if (sidebarSubmitBtn) {
      // Keep disabled if a submission is in flight (prevents re-submit during redirect)
      sidebarSubmitBtn.disabled = !allRequirementsMet || (window._sellSubmitting === true);
    }

    // Update button text based on mode (edit mode overrides all)
    if (sidebarSubmitBtn) {
      if (window.sellEditMode) {
        sidebarSubmitBtn.textContent = 'Update Listing';
      } else if (window.currentMode === 'set') {
        sidebarSubmitBtn.textContent = 'Create Set Listing';
      } else if (window.currentMode === 'isolated') {
        sidebarSubmitBtn.textContent = 'Create Listing';
      } else {
        sidebarSubmitBtn.textContent = 'List Item';
      }
    }
  }

  // ========== RENDER SET ITEMS IN SIDEBAR ==========
  function renderSidebarSetItems() {
    if (!sidebarSetItemsList) return;

    sidebarSetItemsList.innerHTML = '';

    // Access setItems from window scope
    const items = window.setItems || [];

    if (items.length === 0) {
      return;
    }

    items.forEach((item, index) => {
      const tile = document.createElement('div');
      tile.className = 'sidebar-set-tile';

      const photoURL = item.photoURL || '';
      const metalText = item.metal || '—';
      const productText = item.product_line || '—';
      const yearText = item.year || '—';
      const weightText = item.weight || '';

      const sidebarItemTitle = item.item_title || `Set Item #${index + 1}`;
      tile.innerHTML = `
        <img src="${photoURL}" class="sidebar-set-tile-thumb" alt="Set item ${index + 1}" style="display: ${photoURL ? 'block' : 'none'};">
        <div class="sidebar-set-tile-info">
          <p class="sidebar-set-tile-label">${sidebarItemTitle}</p>
          <p class="sidebar-set-tile-summary">${weightText} ${metalText} • ${productText} • ${yearText}</p>
        </div>
        <div class="sidebar-set-tile-controls">
          <button type="button" class="sidebar-set-tile-btn remove" data-index="${index}" title="Remove">×</button>
        </div>
      `;

      sidebarSetItemsList.appendChild(tile);
    });

    // Add event listeners for remove buttons
    sidebarSetItemsList.querySelectorAll('.sidebar-set-tile-btn.remove').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const index = parseInt(e.target.dataset.index);
        window.setItems.splice(index, 1);
        renderSidebarSetItems();

        // IMPORTANT: Also update hidden inputs for form submission
        if (typeof renderSetItems === 'function') {
          renderSetItems();
        }

        // Update the "Set Item #" label to show next item number
        const setItemLabel = document.getElementById('setItemLabel');
        if (setItemLabel) {
          setItemLabel.textContent = `Set Item #${window.setItems.length + 1}`;
        }

        updateChecklist();
      });
    });

    updateChecklist();
  }

  // ========== FUNCTION TO CHECK IF ADD ITEM BUTTON SHOULD BE ENABLED ==========
  function updateAddItemButtonState() {
    if (window.currentMode !== 'set') return;

    const specs = captureSpecValues();

    // All set items require: all specs + photo
    const hasAllSpecs = !!(specs.metal && specs.product_line && specs.product_type &&
                           specs.weight && specs.purity && specs.mint && specs.year &&
                           specs.finish && specs.series_variant);
    // Handle both photo arrays (multi-photo) and single photos
    const hasPhoto = Array.isArray(specs.photo) ? specs.photo.length > 0 : !!specs.photo;

    const canAdd = hasAllSpecs && hasPhoto;

    if (sidebarAddSetItemBtn) {
      sidebarAddSetItemBtn.disabled = !canAdd;
      sidebarAddSetItemBtn.classList.toggle('set-item-ready', canAdd);
    }

    const addItemBtn = document.getElementById('addSetItemBtn');
    if (addItemBtn) {
      addItemBtn.disabled = !canAdd;
      addItemBtn.classList.toggle('set-item-ready', canAdd);
    }
  }

  // ========== WIRE UP SIDEBAR SET BUTTON TO EXISTING LOGIC ==========
  if (sidebarAddSetItemBtn) {
    sidebarAddSetItemBtn.addEventListener('click', () => {
      console.log('[Add Item] Button clicked');

      // Validate current fields
      const specs = captureSpecValues();
      console.log('[Add Item] Captured specs:', specs);

      // All set items require: all specs + photo
      if (!specs.metal || !specs.product_line || !specs.product_type || !specs.weight ||
          !specs.purity || !specs.mint || !specs.year || !specs.finish || !specs.series_variant) {
        showFieldValidationModal(['All Product Specification fields (including Series Variant) must be filled to add this item to the set.']);
        return;
      }

      // Handle both photo arrays (multi-photo) and single photos
      const hasPhoto = Array.isArray(specs.photo) ? specs.photo.length > 0 : !!specs.photo;
      if (!hasPhoto) {
        showFieldValidationModal(['Please upload at least one photo for this item before adding it to the set.']);
        return;
      }

      console.log('[Add Item] Validation passed, adding item to set');

      // For multi-photo (array), create data URL for first photo only (for sidebar display)
      // Store the full photo array in the specs object
      if (Array.isArray(specs.photo) && specs.photo.length > 0) {
        // Multi-photo case (Set mode)
        const firstPhoto = specs.photo[0];
        const reader = new FileReader();
        reader.onload = (e) => {
          specs.photoURL = e.target.result; // Data URL of first photo for display

          // Add to array
          setItems.push(specs);
          console.log('[Add Item] Item added to setItems. Total items:', setItems.length);

          // Render tiles in sidebar
          renderSidebarSetItems();

          // IMPORTANT: Also render hidden inputs for form submission
          if (typeof renderSetItems === 'function') {
            renderSetItems();
          }

          // Update the "Set Item #" label to show next item number
          const setItemLabel = document.getElementById('setItemLabel');
          if (setItemLabel) {
            setItemLabel.textContent = `Set Item #${setItems.length + 1}`;
          }

          // Clear fields for next item
          clearSpecFields();

          // Scroll to item specification section top
          const itemSpecSection = document.querySelector('.content-section');
          if (itemSpecSection) {
            itemSpecSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }

          // Focus first field
          setTimeout(() => {
            const metalField = document.getElementById('metal');
            if (metalField) metalField.focus();
          }, 300);

          // Update checklist and button state
          updateChecklist();
          updateAddItemButtonState();
        };
        reader.readAsDataURL(firstPhoto);
      } else if (specs.photo && specs.photo instanceof File) {
        // Single photo case (for backwards compatibility)
        const reader = new FileReader();
        reader.onload = (e) => {
          specs.photoURL = e.target.result;

          // Add to array
          setItems.push(specs);
          console.log('[Add Item] Item added to setItems. Total items:', setItems.length);

          // Render tiles in sidebar
          renderSidebarSetItems();

          // IMPORTANT: Also render hidden inputs for form submission
          if (typeof renderSetItems === 'function') {
            renderSetItems();
          }

          // Update the "Set Item #" label to show next item number
          const setItemLabel = document.getElementById('setItemLabel');
          if (setItemLabel) {
            setItemLabel.textContent = `Set Item #${setItems.length + 1}`;
          }

          // Clear fields for next item
          clearSpecFields();

          // Scroll to item specification section top
          const itemSpecSection = document.querySelector('.content-section');
          if (itemSpecSection) {
            itemSpecSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }

          // Focus first field
          setTimeout(() => {
            const metalField = document.getElementById('metal');
            if (metalField) metalField.focus();
          }, 300);

          // Update checklist and button state
          updateChecklist();
          updateAddItemButtonState();
        };
        reader.readAsDataURL(specs.photo);
      }
    });
  }

  // ========== INITIALIZE SIDEBAR ON PAGE LOAD ==========
  // Initialize sidebar based on selected mode (after page load or draft restore)
  // Note: Mode change event listeners are in main script (updateUIForMode)
  const modeStandard = document.getElementById('modeStandard');
  const modeIsolated = document.getElementById('modeIsolated');
  const modeSet = document.getElementById('modeSet');

  // Note: window.currentMode is already set by the main script
  // We don't re-initialize it here to avoid overwriting the actual state

  // ========== SHOW/HIDE CHECKLIST SECTIONS BASED ON MODE ==========
  function updateChecklistVisibility() {
    console.log('[SELL SIDEBAR] updateChecklistVisibility called', {
      currentMode: window.currentMode
    });

    if (window.currentMode === 'set') {
      // Set mode: show split checklists, hide standard
      console.log('[SELL SIDEBAR] Switching to SET mode layout');
      sidebarChecklistStandard.style.display = 'none';
      sidebarCurrentItemSection.style.display = 'block';
      sidebarSetListingSection.style.display = 'block';
    } else {
      // Standard or One-of-a-Kind: show standard checklist, hide split
      console.log('[SELL SIDEBAR] Switching to STANDARD/ISOLATED mode layout');
      sidebarChecklistStandard.style.display = 'block';
      sidebarCurrentItemSection.style.display = 'none';
      sidebarSetListingSection.style.display = 'none';
    }
  }

  // Expose globally so mode change can trigger it
  window.updateChecklistVisibility = updateChecklistVisibility;

  // Initialize checklist visibility
  updateChecklistVisibility();

  // Update sidebar to reflect current state
  updateSidebarSummary();
  updateChecklist();

  // ========== ADD EVENT LISTENERS FOR LIVE UPDATES ==========
  // Debounce helper
  function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  // Debounced update for text inputs
  const debouncedUpdate = debounce(() => {
    updateSidebarSummary();
    updateChecklist();
    updateAddItemButtonState();  // Also update button state on text input
  }, 100);

  const formInputs = document.querySelectorAll('#sellForm input, #sellForm select, #sellForm textarea');
  console.log('[SELL SIDEBAR] Attaching listeners to', formInputs.length, 'form inputs');

  formInputs.forEach(input => {
    // Use debounced update for text inputs
    if (input.type === 'text' || input.type === 'textarea') {
      input.addEventListener('input', debouncedUpdate);
    } else {
      // Immediate update for other inputs
      input.addEventListener('input', () => {
        console.log('[SELL SIDEBAR] Input event fired on', input.name || input.id);
        updateSidebarSummary();
        updateChecklist();
        updateAddItemButtonState();
      });
    }

    // Always update on change (non-debounced)
    input.addEventListener('change', () => {
      console.log('[SELL SIDEBAR] Change event fired on', input.name || input.id);
      updateSidebarSummary();
      updateChecklist();
      updateAddItemButtonState();
    });
  });

  console.log('[SELL SIDEBAR] Listeners attached successfully');

  // Add specific listeners for pricing mode radios (ensure they trigger checklist updates)
  const pricingModeRadios = document.querySelectorAll('input[name="pricing_mode"]');
  pricingModeRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      updateSidebarSummary();
      updateChecklist();
      updateAddItemButtonState();
    });
  });

  // Add specific listeners for photo uploads
  if (itemPhotoInput) {
    itemPhotoInput.addEventListener('change', () => {
      updateChecklist();
      updateAddItemButtonState();
    });
  }

  if (coverPhotoInput) {
    coverPhotoInput.addEventListener('change', () => {
      updateChecklist();
    });
  }

  // Add listeners for photo clear buttons
  const photoClearBtn = document.getElementById('photoClearBtn');
  const coverPhotoClearBtn = document.getElementById('coverPhotoClearBtn');

  if (photoClearBtn) {
    photoClearBtn.addEventListener('click', () => {
      setTimeout(() => {
        updateChecklist();
        updateAddItemButtonState();
      }, 50);
    });
  }

  if (coverPhotoClearBtn) {
    coverPhotoClearBtn.addEventListener('click', () => {
      setTimeout(() => {
        updateChecklist();
      }, 50);
    });
  }

  // Hook into set item additions
  const originalRenderSetItems = window.renderSetItems;
  if (typeof originalRenderSetItems === 'function') {
    window.renderSetItems = function() {
      originalRenderSetItems();
      renderSidebarSetItems();
    };
  }

  // Initial render - delay slightly to ensure DOM is ready
  setTimeout(() => {
    updateSidebarSummary();
    updateChecklist();
    if (window.currentMode === 'set') {
      renderSidebarSetItems();
    }
  }, 100);

  // Export functions for external use
  window.updateSidebarSummary = updateSidebarSummary;
  window.updateSidebarChecklist = updateChecklist;
  window.updateChecklist = updateChecklist; // Also export as updateChecklist for consistency
  window.updateAddItemButtonState = updateAddItemButtonState;
  window.renderSidebarSetItems = renderSidebarSetItems;

})();
