// NOTE: Datalist validation is now handled by field_validation_modal.js
// This function is no longer used but kept for reference
// function validateDatalistInputs(event) {
//     const form = event.target;
//     const inputs = form.querySelectorAll(".validated-datalist");
//
//     for (const input of inputs) {
//         const listId = input.dataset.listId;
//         const listEl = document.getElementById(listId);
//         if (!listEl) continue;
//
//         const value = (input.value || "").trim();
//         if (value === "") {
//             alert(`Please select a value for "${input.name}".`);
//             input.focus();
//             event.preventDefault();
//             return;
//         }
//
//         // Collect allowed values from the datalist
//         const allowed = Array.from(listEl.options).map(opt => (opt.value || "").trim());
//
//         // Require exact match (case-sensitive)
//         const isValid = allowed.includes(value);
//
//         if (!isValid) {
//             alert(`"${value}" is not a valid option for "${input.name}". Please choose from the dropdown list.`);
//             input.focus();
//             event.preventDefault();
//             return;
//         }
//     }
// }

/**
 * Build a custom dropdown for an input, using the associated <datalist> options.
 * This replaces the browser's native datalist popup so we can control width/position.
 */
function setupCustomDropdown(input) {
    const listId = input.dataset.listId;
    const dataList = document.getElementById(listId);
    if (!dataList) return;

    const options = Array.from(dataList.options)
        .map(opt => (opt.value || "").trim())
        .filter(v => v !== "");

    const wrapper = input.closest(".input-group") || input.parentElement;

    // Create the dropdown menu container
    const menu = document.createElement("div");
    menu.className = "custom-dropdown-menu";
    wrapper.appendChild(menu);

    function hideMenu() {
        menu.style.display = "none";
    }

    function showMenu() {
        if (menu.children.length > 0) {
            menu.style.display = "block";
        } else {
            menu.style.display = "none";
        }
    }

    function renderSuggestions(filterText) {
        const term = (filterText || "").toLowerCase();
        menu.innerHTML = "";

        const filtered = options.filter(value =>
            value.toLowerCase().includes(term)
        );

        if (filtered.length === 0) {
            hideMenu();
            return;
        }

        filtered.forEach(value => {
            const item = document.createElement("div");
            item.className = "custom-dropdown-item";
            item.textContent = value;

            // Use mousedown so it fires before input loses focus
            item.addEventListener("mousedown", (e) => {
                e.preventDefault();
                input.value = value;
                hideMenu();
                // Dispatch change so any listeners (e.g. price preview) update
                input.dispatchEvent(new Event('change', { bubbles: true }));
            });

            menu.appendChild(item);
        });

        showMenu();
    }

    // Show suggestions when the input gains focus
    input.addEventListener("focus", () => {
        renderSuggestions(input.value);
    });

    // Filter suggestions as user types
    input.addEventListener("input", () => {
        renderSuggestions(input.value);
    });

    // Hide menu shortly after blur (so clicks still register)
    input.addEventListener("blur", () => {
        setTimeout(hideMenu, 150);
    });

    // Optional: down-arrow to open menu when empty
    input.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown") {
            renderSuggestions(input.value);
            menu.focus?.();
        }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    // Debug: output prefill state so we can see what data was received
    console.log('[SELL PREFILL] sellPrefillData:', window.sellPrefillData, '| sellEditMode:', window.sellEditMode);

    // Pre-populate form fields from URL parameters (if coming from bucket page)
    if (window.sellPrefillData) {
        const prefill = window.sellPrefillData;

        // Map of form field IDs to prefill data keys
        const fieldMapping = {
            'metal': 'metal',
            'product_line': 'product_line',
            'product_type': 'product_type',
            'weight': 'weight',
            'purity': 'purity',
            'mint': 'mint',
            'year': 'year',
            'finish': 'finish',
            'condition_category': 'condition_category',
            'series_variant': 'series_variant'
        };

        // Pre-populate each field if it has a value
        Object.entries(fieldMapping).forEach(([fieldId, prefillKey]) => {
            const value = prefill[prefillKey];
            if (value && String(value).trim() !== '') {
                const field = document.getElementById(fieldId);
                if (field) {
                    field.value = value;
                    console.log('[SELL PREFILL] Set', fieldId, '=', value);
                } else {
                    console.warn('[SELL PREFILL] Element not found:', fieldId);
                }
            }
        });

        // Helper to set a field by ID if value is non-null/non-empty
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el && val != null && String(val).trim() !== '') el.value = val;
        };

        // ── Edit mode: set listing type radio ──
        if (window.sellEditMode) {
            const isIsolated = prefill.is_isolated == 1;
            const isolatedType = prefill.isolated_type;
            if (isIsolated && isolatedType === 'set') {
                const modeSet = document.getElementById('modeSet');
                if (modeSet) { modeSet.checked = true; modeSet.dispatchEvent(new Event('change')); }
            } else if (isIsolated) {
                const modeIsolated = document.getElementById('modeIsolated');
                if (modeIsolated) { modeIsolated.checked = true; modeIsolated.dispatchEvent(new Event('change')); }
            }
            // Standard mode is already selected by default
        }

        // ── Non-category listing fields ──
        setVal('listing_title', prefill.listing_title);
        setVal('listing_description', prefill.listing_description);
        setVal('quantity', prefill.quantity);
        setVal('condition_notes', prefill.condition_notes);
        setVal('actual_year', prefill.actual_year);
        setVal('packaging_type', prefill.packaging_type);
        setVal('packaging_notes', prefill.packaging_notes);
        setVal('item_packaging_type', prefill.packaging_type);
        setVal('item_packaging_notes', prefill.packaging_notes);
        setVal('edition_number', prefill.edition_number);
        setVal('edition_total', prefill.edition_total);

        // ── Pricing mode ──
        if (prefill.pricing_mode === 'premium_to_spot') {
            const premEl = document.getElementById('pricing_mode_premium');
            if (premEl) { premEl.checked = true; premEl.dispatchEvent(new Event('change')); }
            setVal('spot_premium', prefill.spot_premium);
            setVal('floor_price', prefill.floor_price);
            setVal('pricing_metal', prefill.pricing_metal);
        } else if (prefill.price_per_coin) {
            setVal('price_per_coin', parseFloat(prefill.price_per_coin).toFixed(2));
        }

        // ── Existing photos (edit mode only) ──
        if (window.sellEditMode && prefill.existing_photos && prefill.existing_photos.length) {
            const keepPhotoIds = document.getElementById('keepPhotoIds');
            const ids = prefill.existing_photos.map(p => p.id);
            if (keepPhotoIds) keepPhotoIds.value = ids.join(',');

            const boxIds     = ['standardPhotoBox1', 'standardPhotoBox2', 'standardPhotoBox3'];
            const previewIds = ['standardPhotoPreview1', 'standardPhotoPreview2', 'standardPhotoPreview3'];
            const clearIds   = ['standardPhotoClear1', 'standardPhotoClear2', 'standardPhotoClear3'];

            const isSet = prefill.is_isolated == 1 && prefill.isolated_type === 'set';
            const isOOK = prefill.is_isolated == 1 && prefill.isolated_type !== 'set';

            if (isSet) {
                // Set listings: cover photo goes to coverPhotoUploadBox
                const coverPhoto = prefill.existing_photos[0];
                if (coverPhoto) {
                    const coverBox      = document.getElementById('coverPhotoUploadBox');
                    const coverPreview  = document.getElementById('coverPhotoPreview');
                    const coverClearBtn = document.getElementById('coverPhotoClearBtn');
                    if (coverBox && coverPreview) {
                        coverPreview.src = coverPhoto.url;
                        coverPreview.style.display = 'block';
                        if (coverClearBtn) coverClearBtn.style.display = 'flex';
                        coverBox.classList.add('has-image');
                        coverBox.dataset.existingPhotoId = coverPhoto.id;
                    }
                }
            } else if (isOOK) {
                // OOK listings: first photo is the cover photo
                const coverPhoto = prefill.existing_photos[0];
                if (coverPhoto) {
                    const coverBox     = document.getElementById('coverPhotoUploadBox');
                    const coverPreview = document.getElementById('coverPhotoPreview');
                    const coverClearBtn = document.getElementById('coverPhotoClearBtn');
                    if (coverBox && coverPreview) {
                        coverPreview.src = coverPhoto.url;
                        coverPreview.style.display = 'block';
                        if (coverClearBtn) coverClearBtn.style.display = 'flex';
                        coverBox.classList.add('has-image');
                        coverBox.dataset.existingPhotoId = coverPhoto.id;
                    }
                }
                // Any additional photos go into the standard photo boxes
                prefill.existing_photos.slice(1, 4).forEach(function(photo, i) {
                    const box     = document.getElementById(boxIds[i]);
                    const preview = document.getElementById(previewIds[i]);
                    const clearBtn = document.getElementById(clearIds[i]);
                    if (box && preview) {
                        preview.src = photo.url;
                        preview.style.display = 'block';
                        if (clearBtn) clearBtn.style.display = 'flex';
                        box.classList.add('has-image');
                        box.dataset.existingPhotoId = photo.id;
                    }
                });
            } else {
                // Standard listings: populate photo boxes 1-3
                prefill.existing_photos.slice(0, 3).forEach(function(photo, i) {
                    const box     = document.getElementById(boxIds[i]);
                    const preview = document.getElementById(previewIds[i]);
                    const clearBtn = document.getElementById(clearIds[i]);
                    if (box && preview) {
                        preview.src = photo.url;
                        preview.style.display = 'block';
                        if (clearBtn) clearBtn.style.display = 'flex';
                        box.classList.add('has-image');
                        box.dataset.existingPhotoId = photo.id;
                    }
                });
            }
        }

        // ── Set listing edit: restore existing items as display tiles ──
        if (window.sellEditMode && prefill.isolated_type === 'set' &&
                Array.isArray(prefill.set_items) && prefill.set_items.length > 0) {
            prefill.set_items.forEach(function(item) {
                var restoredItem = {
                    metal:          item.metal          || '',
                    product_line:   item.product_line   || '',
                    product_type:   item.product_type   || '',
                    weight:         item.weight         || '',
                    purity:         item.purity         || '',
                    mint:           item.mint           || '',
                    year:           item.year           || '',
                    finish:         item.finish         || '',
                    grade:          item.grade          || '',
                    item_title:     item.item_title     || '',
                    packaging_type: item.packaging_type || '',
                    packaging_notes: item.packaging_notes || '',
                    condition_notes: item.condition_notes || '',
                    edition_number: item.edition_number || '',
                    edition_total:  item.edition_total  || '',
                    quantity:       item.quantity       || 1,
                    // No File object — existing photo tracked by URL only
                    photo:    null,
                    photoURL: item.first_photo_path ? '/static/' + item.first_photo_path : ''
                };
                window.setItems.push(restoredItem);
            });
            // Render tiles (renderSetItems is patched by sidebar_controller to also update sidebar)
            if (typeof window.renderSetItems === 'function') window.renderSetItems();
        }

        // Refresh sidebar after all prefill values are set
        if (typeof window.updateChecklist === 'function') window.updateChecklist();
        if (typeof window.updateSidebarSummary === 'function') window.updateSidebarSummary();
    }

    // NOTE: Form validation is now handled by field_validation_modal.js
    // which is called from sell_listing_modals.js before showing confirmation

    // Set up custom dropdowns for all searchable fields
    const dropdownInputs = document.querySelectorAll(".custom-dropdown-input");
    dropdownInputs.forEach(setupCustomDropdown);

    // Set up photo upload box functionality
    setupPhotoUpload();

    // Set up price and quantity input formatting
    setupPriceInput();
    setupQuantityInput();

    // Set up pricing mode toggle
    setupPricingModeToggle();

    // Set up premium-to-spot price inputs formatting
    setupPremiumInputs();

    // Eagerly load spot prices so they're ready when the user switches to premium mode
    loadSpotPricesForPreview();
});

/**
 * Set up the photo upload box to:
 * 1. Open file chooser when clicked
 * 2. Show preview when image is selected
 * 3. Show X button to clear image
 */
function setupPhotoUpload() {
    const photoBox = document.getElementById('photoUploadBox');
    const photoInput = document.getElementById('item_photo');
    const photoPreview = document.getElementById('photoPreview');
    const clearBtn = document.getElementById('photoClearBtn');

    if (!photoBox || !photoInput || !photoPreview || !clearBtn) return;

    // Click on box triggers file input (only when no image)
    photoBox.addEventListener('click', (e) => {
        // Don't open file chooser if clicking clear button or if image is shown
        if (e.target.closest('.photo-clear-btn')) {
            return;
        }
        // Only open file chooser if no image is currently displayed
        if (!photoBox.classList.contains('has-image')) {
            photoInput.click();
        }
    });

    // Handle file selection
    photoInput.addEventListener('change', (e) => {
        const file = e.target.files[0];

        if (file) {
            // Validate it's an image
            if (!file.type.startsWith('image/')) {
                alert('Please select an image file (JPG, PNG, etc.)');
                photoInput.value = '';
                return;
            }

            // Create preview
            const reader = new FileReader();
            reader.onload = (event) => {
                photoPreview.src = event.target.result;
                photoPreview.style.display = 'block';
                clearBtn.style.display = 'flex';
                photoBox.classList.add('has-image');
            };
            reader.readAsDataURL(file);
        } else {
            // No file selected, reset to default state
            clearImage();
        }
    });

    // Clear button functionality
    clearBtn.addEventListener('click', (e) => {
        e.stopPropagation(); // Prevent triggering photoBox click
        clearImage();
    });

    // Helper function to clear the image and reset to default state
    function clearImage() {
        photoPreview.style.display = 'none';
        photoPreview.src = '';
        clearBtn.style.display = 'none';
        photoBox.classList.remove('has-image');
        photoInput.value = ''; // Clear the file input
    }
}

/**
 * Set up Price input formatting:
 * - Format to always show exactly two decimal places
 * - Example: 10 → 10.00, 10.5 → 10.50, 10.123 → 10.12
 */
function setupPriceInput() {
    const priceInput = document.getElementById('price_per_coin');
    if (!priceInput) return;

    // Format on blur (when user leaves the field)
    priceInput.addEventListener('blur', () => {
        formatPriceValue();
    });

    // Allow only numbers and decimal point during typing
    priceInput.addEventListener('input', (e) => {
        let value = e.target.value;

        // Remove any non-numeric characters except decimal point
        value = value.replace(/[^\d.]/g, '');

        // Allow only one decimal point
        const parts = value.split('.');
        if (parts.length > 2) {
            value = parts[0] + '.' + parts.slice(1).join('');
        }

        // Limit to 2 decimal places
        if (parts[1] && parts[1].length > 2) {
            value = parts[0] + '.' + parts[1].substring(0, 2);
        }

        e.target.value = value;
    });

    // Format on form submit
    const form = priceInput.closest('form');
    if (form) {
        form.addEventListener('submit', (e) => {
            formatPriceValue();
        });
    }

    function formatPriceValue() {
        let value = priceInput.value.trim();

        if (value === '') return;

        // Parse the value as a float
        const numValue = parseFloat(value);

        // Check if it's a valid number
        if (!isNaN(numValue) && numValue >= 0) {
            // Format to exactly 2 decimal places
            priceInput.value = numValue.toFixed(2);
        } else {
            // Invalid input, clear it
            priceInput.value = '';
        }
    }
}

/**
 * Set up Quantity input validation:
 * - Only allow whole numbers (integers)
 * - No decimals, no non-numeric characters
 */
function setupQuantityInput() {
    const quantityInput = document.getElementById('quantity');
    if (!quantityInput) return;

    // Prevent typing non-numeric characters
    quantityInput.addEventListener('input', (e) => {
        let value = e.target.value;

        // Remove any non-numeric characters
        value = value.replace(/[^\d]/g, '');

        // Ensure it's a positive integer (remove leading zeros)
        if (value.length > 0) {
            value = String(parseInt(value, 10));
        }

        e.target.value = value;
    });

    // Validate on blur
    quantityInput.addEventListener('blur', () => {
        let value = quantityInput.value.trim();

        if (value === '' || value === '0') {
            quantityInput.value = '1'; // Default to 1 if empty or zero
        } else {
            const numValue = parseInt(value, 10);
            if (isNaN(numValue) || numValue < 1) {
                quantityInput.value = '1';
            } else {
                quantityInput.value = String(numValue);
            }
        }
    });

    // Also enforce on form submit
    const form = quantityInput.closest('form');
    if (form) {
        form.addEventListener('submit', (e) => {
            let value = quantityInput.value.trim();
            const numValue = parseInt(value, 10);

            if (isNaN(numValue) || numValue < 1) {
                e.preventDefault();
                alert('Please enter a valid quantity (whole numbers only, minimum 1).');
                quantityInput.focus();
                return false;
            }

            quantityInput.value = String(numValue);
        });
    }
}

/**
 * Set up pricing mode toggle between static and premium-to-spot
 */
function setupPricingModeToggle() {
    const staticRadio = document.getElementById('pricing_mode_static');
    const premiumRadio = document.getElementById('pricing_mode_premium');
    const staticGroup = document.getElementById('static_price_group');
    const premiumFields = document.getElementById('premium_to_spot_fields');
    const pricePerCoin = document.getElementById('price_per_coin');
    const spotPremium = document.getElementById('spot_premium');
    const floorPrice = document.getElementById('floor_price');

    if (!staticRadio || !premiumRadio || !staticGroup || !premiumFields) return;

    // Handle pricing mode changes
    function handlePricingModeChange() {
        const isStatic = staticRadio.checked;

        const setSpotMetalGroup = document.getElementById('set_spot_metal_group');
        if (isStatic) {
            // Show static price, hide premium fields
            staticGroup.style.display = 'block';
            premiumFields.style.display = 'none';

            // Set required fields
            pricePerCoin.required = true;
            if (spotPremium) spotPremium.required = false;
            if (floorPrice) floorPrice.required = false;

            // Hide spot metal selector
            if (setSpotMetalGroup) setSpotMetalGroup.style.display = 'none';
        } else {
            // Hide static price, show premium fields
            staticGroup.style.display = 'none';
            premiumFields.style.display = 'block';

            // Set required fields
            pricePerCoin.required = false;
            if (spotPremium) spotPremium.required = true;
            if (floorPrice) floorPrice.required = true;

            // Show spot metal selector only in set mode
            if (setSpotMetalGroup) {
                setSpotMetalGroup.style.display = (window.currentMode === 'set') ? 'block' : 'none';
            }

            // Update preview immediately (prices eagerly loaded at page init)
            updatePricePreview();
            // Also refresh spot prices in the background
            loadSpotPricesForPreview();
        }
    }

    // Attach event listeners
    staticRadio.addEventListener('change', handlePricingModeChange);
    premiumRadio.addEventListener('change', handlePricingModeChange);

    // Initialize on page load
    handlePricingModeChange();
}

/**
 * Load spot prices from API and enable price preview
 */
async function loadSpotPricesForPreview() {
    try {
        const response = await fetch('/api/spot-prices');
        const data = await response.json();

        if (data.success) {
            // Store spot prices globally for preview calculations
            window.spotPrices = data.prices;
            updatePricePreview();
        } else {
            console.error('Failed to load spot prices:', data.message);
        }
    } catch (error) {
        console.error('Error loading spot prices:', error);
    }
}

/**
 * Update price preview when premium-to-spot inputs change
 */
function updatePricePreview() {
    const previewDiv = document.getElementById('price_preview');
    if (!previewDiv) return;

    const loadedDiv = document.getElementById('price_preview_loaded');
    const noMetalDiv = document.getElementById('price_preview_no_metal');

    // Only show the preview container when premium mode is active
    const premiumFields = document.getElementById('premium_to_spot_fields');
    if (!premiumFields || premiumFields.style.display === 'none') return;

    // Always make the preview container visible once premium mode is on
    previewDiv.style.display = 'block';

    if (!window.spotPrices) {
        // Spot prices not yet loaded — show loading state
        if (loadedDiv) loadedDiv.style.display = 'none';
        if (noMetalDiv) { noMetalDiv.style.display = 'block'; noMetalDiv.querySelector('small').textContent = 'Loading spot prices…'; }
        return;
    }

    const weightInput = document.getElementById('weight');
    const metalInput = document.getElementById('metal');
    const pricingMetalInput = document.getElementById('pricing_metal');
    const spotPremiumInput = document.getElementById('spot_premium');
    const floorPriceInput = document.getElementById('floor_price');

    // In set mode use the explicit spot-metal selector; otherwise auto-derive from metal field
    const setSpotMetalSelect = document.getElementById('set_spot_metal_select');
    const pricingMetal = (window.currentMode === 'set' && setSpotMetalSelect)
        ? (setSpotMetalSelect.value || '')
        : (metalInput?.value || '');
    const metalKey = pricingMetal.toLowerCase();

    // Sync hidden pricing_metal field
    if (pricingMetalInput) pricingMetalInput.value = pricingMetal;

    // Get spot price for the metal
    const spotPrice = window.spotPrices[metalKey];

    if (!spotPrice) {
        // Metal not filled in or not recognized — prompt user
        if (loadedDiv) loadedDiv.style.display = 'none';
        if (noMetalDiv) { noMetalDiv.style.display = 'block'; noMetalDiv.querySelector('small').textContent = 'Select a metal above to see the estimated price.'; }
        return;
    }

    // Metal found — show the full calculation
    if (loadedDiv) loadedDiv.style.display = 'block';
    if (noMetalDiv) noMetalDiv.style.display = 'none';

    const previewAmountSpan = loadedDiv.querySelector('.preview-amount');
    const spotPriceSpan = loadedDiv.querySelector('.spot-price');
    const spotMetalNameSpan = loadedDiv.querySelector('.spot-metal-name');

    // Parse weight
    const weightStr = weightInput?.value || '1';
    const weightMatch = weightStr.match(/[\d.]+/);
    const weight = weightMatch ? parseFloat(weightMatch[0]) : 1.0;

    // Parse premium and floor
    const premium = parseFloat(spotPremiumInput?.value) || 0;
    const floor = parseFloat(floorPriceInput?.value) || 0;

    const computedPrice = (spotPrice * weight) + premium;
    const effectivePrice = Math.max(computedPrice, floor);

    if (previewAmountSpan) previewAmountSpan.textContent = formatPrice(effectivePrice);
    if (spotPriceSpan) spotPriceSpan.textContent = formatPrice(spotPrice);
    if (spotMetalNameSpan) spotMetalNameSpan.textContent = pricingMetal.charAt(0).toUpperCase() + pricingMetal.slice(1).toLowerCase();
}

/**
 * Set up premium-to-spot price input formatting
 */
function setupPremiumInputs() {
    const spotPremiumInput = document.getElementById('spot_premium');
    const floorPriceInput = document.getElementById('floor_price');
    const weightInput = document.getElementById('weight');
    const metalInput = document.getElementById('metal');
    const pricingMetalInput = document.getElementById('pricing_metal');

    // Format premium and floor inputs
    [spotPremiumInput, floorPriceInput].forEach(input => {
        if (!input) return;

        // Format on blur
        input.addEventListener('blur', () => {
            formatPremiumValue(input);
            updatePricePreview();
        });

        // Allow only numbers and decimal during typing
        input.addEventListener('input', (e) => {
            let value = e.target.value;
            value = value.replace(/[^\d.]/g, '');
            const parts = value.split('.');
            if (parts.length > 2) {
                value = parts[0] + '.' + parts.slice(1).join('');
            }
            if (parts[1] && parts[1].length > 2) {
                value = parts[0] + '.' + parts[1].substring(0, 2);
            }
            e.target.value = value;
            updatePricePreview();
        });
    });

    // Update preview when relevant fields change
    [weightInput, metalInput].forEach(input => {
        if (input) {
            input.addEventListener('input', updatePricePreview);
            input.addEventListener('change', updatePricePreview);
        }
    });

    // Set mode: update preview when the explicit spot-metal dropdown changes
    const setSpotMetalSelectEl = document.getElementById('set_spot_metal_select');
    if (setSpotMetalSelectEl) {
        setSpotMetalSelectEl.addEventListener('change', updatePricePreview);
    }

    function formatPremiumValue(input) {
        let value = input.value.trim();
        if (value === '') return;

        const numValue = parseFloat(value);
        if (!isNaN(numValue) && numValue >= 0) {
            input.value = numValue.toFixed(2);
        } else {
            input.value = '';
        }
    }
}

// ── Sidebar: fixed until footer, then scroll away ──
(function() {
    const SIDEBAR_TOP = 80; // matches CSS top: 80px
    const GAP = 12;         // px gap to keep between sidebar bottom and footer top

    function updateSidebarTop() {
        const sidebar = document.querySelector('.sell-sticky-sidebar');
        const footer = document.getElementById('siteFooter');
        if (!sidebar || !footer) return;

        const footerViewportTop = footer.getBoundingClientRect().top;
        const sidebarHeight = sidebar.offsetHeight;
        const threshold = SIDEBAR_TOP + sidebarHeight + GAP;

        if (footerViewportTop < threshold) {
            // Footer is encroaching — push sidebar upward (top can go negative;
            // the header clips anything above 0 and the effect looks natural)
            sidebar.style.top = (footerViewportTop - sidebarHeight - GAP) + 'px';
        } else {
            // Normal: pin to fixed position
            sidebar.style.top = SIDEBAR_TOP + 'px';
        }
    }

    window.addEventListener('scroll', updateSidebarTop, { passive: true });
    window.addEventListener('resize', updateSidebarTop, { passive: true });
    document.addEventListener('DOMContentLoaded', updateSidebarTop);
}());
