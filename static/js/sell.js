function toggleGradingService() {
    const graded = document.getElementById("graded");
    const serviceDiv = document.getElementById("grading-service-section");
    if (!graded || !serviceDiv) return;

    const value = graded.value;
    serviceDiv.style.display = value === "1" ? "block" : "none";
}

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
            'grade': 'grade'
        };

        // Pre-populate each field if it has a value
        Object.entries(fieldMapping).forEach(([fieldId, prefillKey]) => {
            const value = prefill[prefillKey];
            if (value && value.trim() !== '') {
                const field = document.getElementById(fieldId);
                if (field) {
                    field.value = value;
                }
            }
        });
    }

    // Initialize grading service visibility + change handler
    toggleGradingService();
    const gradedSelect = document.getElementById("graded");
    if (gradedSelect) {
        gradedSelect.addEventListener("change", toggleGradingService);
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

        if (isStatic) {
            // Show static price, hide premium fields
            staticGroup.style.display = 'block';
            premiumFields.style.display = 'none';

            // Set required fields
            pricePerCoin.required = true;
            if (spotPremium) spotPremium.required = false;
            if (floorPrice) floorPrice.required = false;
        } else {
            // Hide static price, show premium fields
            staticGroup.style.display = 'none';
            premiumFields.style.display = 'block';

            // Set required fields
            pricePerCoin.required = false;
            if (spotPremium) spotPremium.required = true;
            if (floorPrice) floorPrice.required = true;

            // Load spot prices for preview
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
    if (!window.spotPrices) return;

    const weightInput = document.getElementById('weight');
    const metalInput = document.getElementById('metal');
    const pricingMetalInput = document.getElementById('pricing_metal');
    const spotPremiumInput = document.getElementById('spot_premium');
    const floorPriceInput = document.getElementById('floor_price');
    const previewDiv = document.getElementById('price_preview');
    const previewAmountSpan = document.querySelector('.preview-amount');
    const spotPriceSpan = document.querySelector('.spot-price');

    if (!previewDiv || !previewAmountSpan || !spotPriceSpan) return;

    // Get pricing metal (use override if set, otherwise category metal)
    const pricingMetal = pricingMetalInput?.value || metalInput?.value || '';
    const metalKey = pricingMetal.toLowerCase();

    // Parse weight (assume in oz, extract numeric value from strings like "1 oz")
    const weightStr = weightInput?.value || '1';
    const weightMatch = weightStr.match(/[\d.]+/);
    const weight = weightMatch ? parseFloat(weightMatch[0]) : 1.0;

    // Parse premium and floor
    const premium = parseFloat(spotPremiumInput?.value) || 0;
    const floor = parseFloat(floorPriceInput?.value) || 0;

    // Get spot price for the metal
    const spotPrice = window.spotPrices[metalKey];

    if (spotPrice && weight > 0) {
        // Calculate effective price
        const computedPrice = (spotPrice * weight) + premium;
        const effectivePrice = Math.max(computedPrice, floor);

        // Display preview
        previewAmountSpan.textContent = `$${effectivePrice.toFixed(2)}`;
        spotPriceSpan.textContent = `$${spotPrice.toFixed(2)}`;
        previewDiv.style.display = 'block';
    } else {
        previewDiv.style.display = 'none';
    }
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
    [weightInput, metalInput, pricingMetalInput].forEach(input => {
        if (input) {
            input.addEventListener('input', updatePricePreview);
            input.addEventListener('change', updatePricePreview);
        }
    });

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
