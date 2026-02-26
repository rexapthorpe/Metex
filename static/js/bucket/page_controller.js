/**
 * Bucket/Item Detail Page Controller
 *
 * Handles page-level functionality for the bucket view page:
 * - Auth-checking wrapper for bid modal
 * - Isolated listing photo gallery
 * - TPG toggle handler
 * - Packaging filter panel and logic
 * - Random Year toggle handler
 * - View Seller button wiring
 * - Price chart initialization
 *
 * Extracted from templates/view_bucket.html inline script during refactor.
 * NO BEHAVIOR CHANGES - structure only.
 *
 * Requires window globals to be set before this script loads:
 * - window.bucketIsIsolated
 * - window.isUserLoggedIn
 * - window.actualBucketId
 */

// Auth-checking wrapper for bid modal - redirects to signup if not logged in
function requireAuthForBid(bucketId, bidId) {
  bidId = bidId || null;
  if (!window.isUserLoggedIn) {
    window.location.href = '/login?mode=signup';
    return;
  }
  openBidModal(bucketId, bidId);
}

// Sync quantity and TPG to form hidden inputs
function syncQuantityAndTPG(quantityTargetId, tpgTargetId) {
  const quantityValue = document.getElementById('buyQtyValue').textContent;
  // Read directly from the checkbox to avoid relying on the change event having fired
  const tpgToggle = document.getElementById('tpgToggle');
  const tpgValue = (tpgToggle && tpgToggle.checked) ? '1' : '0';

  document.getElementById(quantityTargetId).value = quantityValue;
  document.getElementById(tpgTargetId).value = tpgValue;
}

document.addEventListener('DOMContentLoaded', function() {
  // ========== ISOLATED LISTING PHOTO GALLERY ==========
  // Handle thumbnail clicks with swap (only for isolated listings)
  if (window.bucketIsIsolated) {
    const mainImage = document.getElementById('mainImage');
    const isolatedThumbs = document.querySelectorAll('.isolated-thumb');

    isolatedThumbs.forEach(function(thumb) {
      thumb.addEventListener('click', function() {
        const thumbPhotoUrl = this.getAttribute('data-photo');
        if (thumbPhotoUrl && mainImage) {
          // Swap: save current main image URL
          const currentMainUrl = mainImage.src;

          // Set thumbnail image as new main image
          mainImage.src = thumbPhotoUrl;

          // Optional: swap the previous main image into the clicked thumbnail's spot
          // This creates a true "swap" behavior like typical ecommerce galleries
          const thumbImg = this.querySelector('img');
          if (thumbImg) {
            thumbImg.src = currentMainUrl;
            this.setAttribute('data-photo', currentMainUrl);
          }

          // Update active state on thumbnails (visual feedback)
          isolatedThumbs.forEach(t => t.style.borderColor = '#ddd');
          this.style.borderColor = '#1976d2';
        }
      });
    });
  }

  // ========== TPG TOGGLE HANDLER ==========
  const tpgToggle = document.getElementById('tpgToggle');
  const tpgInput = document.getElementById('tpgInput');

  if (tpgToggle && tpgInput) {
    tpgToggle.addEventListener('change', function() {
      tpgInput.value = this.checked ? '1' : '0';
    });
  }

  // ========== PACKAGING FILTER PANEL TOGGLE ==========
  const packagingToggleBtn = document.getElementById('packagingToggleBtn');
  const packagingPanel = document.getElementById('packagingPanel');

  if (packagingToggleBtn && packagingPanel) {
    // Initialize panel state
    packagingPanel.setAttribute('aria-expanded', 'false');
    packagingPanel.style.height = '0px';
    packagingPanel.style.opacity = '0';

    packagingToggleBtn.addEventListener('click', function() {
      const isExpanded = packagingPanel.getAttribute('aria-expanded') === 'true';

      if (isExpanded) {
        // Collapse panel
        packagingPanel.style.height = '0px';
        packagingPanel.style.opacity = '0';
        packagingPanel.setAttribute('aria-expanded', 'false');
        packagingToggleBtn.setAttribute('aria-expanded', 'false');
        const chevron = packagingToggleBtn.querySelector('.chev');
        if (chevron) chevron.textContent = '▸';
      } else {
        // Expand panel
        packagingPanel.removeAttribute('hidden');
        packagingPanel.setAttribute('aria-expanded', 'true');

        // Measure the natural height
        packagingPanel.style.height = 'auto';
        packagingPanel.style.opacity = '0';
        const targetHeight = packagingPanel.scrollHeight + 'px';

        // Force reflow, then animate to target height
        packagingPanel.style.height = '0px';
        requestAnimationFrame(() => {
          packagingPanel.style.height = targetHeight;
          packagingPanel.style.opacity = '1';
        });

        packagingToggleBtn.setAttribute('aria-expanded', 'true');
        const chevron = packagingToggleBtn.querySelector('.chev');
        if (chevron) chevron.textContent = '▾';
      }
    });
  }

  // ========== PACKAGING FILTER LOGIC (Refactored for Professional UX) ==========
  const anyPackagingToggle = document.getElementById('anyPackagingToggle');
  const packagingTypeToggles = document.querySelectorAll('.packaging-type-toggle');
  const packagingToggleRows = document.querySelectorAll('.packaging-toggle-row');

  // Make packaging row labels clickable (toggle the switch when clicked)
  packagingToggleRows.forEach(row => {
    const toggle = row.querySelector('.packaging-type-toggle');
    const label = row.querySelector('.packaging-toggle-label');

    if (label && toggle) {
      label.addEventListener('click', function(e) {
        toggle.checked = !toggle.checked;
        toggle.dispatchEvent(new Event('change'));
      });
    }
  });

  // Helper: Check if all specific toggles are ON
  function allSpecificsAreOn() {
    return Array.from(packagingTypeToggles).every(toggle => toggle.checked);
  }

  // Helper: Set all specific toggles to a state
  function setAllSpecifics(checked) {
    packagingTypeToggles.forEach(toggle => {
      toggle.checked = checked;
    });
  }

  // Apply packaging filters with full page reload (matches repo standard pattern - see Random Year filter)
  function applyPackagingFilters() {
    const currentUrl = new URL(window.location.href);

    // Rule: If master is ON OR (master is OFF and no specifics are ON) → show all (no restriction)
    const masterIsOn = anyPackagingToggle && anyPackagingToggle.checked;
    const noSpecificsSelected = !Array.from(packagingTypeToggles).some(t => t.checked);

    if (masterIsOn || (!masterIsOn && noSpecificsSelected)) {
      // No packaging restriction - remove all packaging_styles parameters
      currentUrl.searchParams.delete('packaging_styles');
    } else {
      // Apply specific packaging filters
      const selectedTypes = [];
      packagingTypeToggles.forEach(toggle => {
        if (toggle.checked) {
          selectedTypes.push(toggle.value);
        }
      });

      // Remove old parameters and add new ones
      currentUrl.searchParams.delete('packaging_styles');
      selectedTypes.forEach(type => {
        currentUrl.searchParams.append('packaging_styles', type);
      });
    }

    // Reload page with updated URL (consistent with Random Year filter pattern)
    // This ensures ALL content (listings, sellers modal, availability) updates correctly
    window.location.href = currentUrl.toString();
  }

  // ========== "ANY PACKAGING STYLE" TOGGLE HANDLER ==========
  if (anyPackagingToggle) {
    anyPackagingToggle.addEventListener('change', function() {
      if (this.checked) {
        // RULE 1: Master ON → Set all specifics ON
        setAllSpecifics(true);
      } else {
        // RULE 2: Master OFF → Set all specifics OFF
        setAllSpecifics(false);
      }

      // Apply filters immediately (no reload)
      applyPackagingFilters();
    });
  }

  // ========== INDIVIDUAL PACKAGING TYPE TOGGLE HANDLERS ==========
  packagingTypeToggles.forEach(toggle => {
    toggle.addEventListener('change', function() {
      // RULE 3: If master is ON and user turns OFF any specific → Master turns OFF
      if (anyPackagingToggle && anyPackagingToggle.checked && !this.checked) {
        anyPackagingToggle.checked = false;
      }

      // RULE 4: If all specifics are now ON → Master turns ON automatically
      if (anyPackagingToggle && !anyPackagingToggle.checked && allSpecificsAreOn()) {
        anyPackagingToggle.checked = true;
      }

      // Apply filters immediately (no reload)
      applyPackagingFilters();
    });
  });

  // ========== INITIALIZE PACKAGING TOGGLE STATE ON PAGE LOAD ==========
  // Sync specific toggles with master toggle state
  if (anyPackagingToggle && anyPackagingToggle.checked) {
    // If master is ON on page load → set all specifics ON (RULE 1)
    setAllSpecifics(true);
  } else if (anyPackagingToggle && !anyPackagingToggle.checked) {
    // If master is OFF, check if all specifics are ON → should turn master ON (RULE 4)
    if (allSpecificsAreOn()) {
      anyPackagingToggle.checked = true;
    }
  }

  // ========== RANDOM YEAR TOGGLE HANDLER ==========
  const randomYearToggle = document.getElementById('randomYearToggle');
  const randomYearInput = document.getElementById('randomYearInput');

  if (randomYearToggle && randomYearInput) {
    randomYearToggle.addEventListener('change', function() {
      randomYearInput.value = this.checked ? '1' : '0';
      // Trigger page reload with random_year parameter
      const currentUrl = new URL(window.location.href);
      if (this.checked) {
        currentUrl.searchParams.set('random_year', '1');
      } else {
        currentUrl.searchParams.delete('random_year');
      }
      window.location.href = currentUrl.toString();
    });
  }

  // ========== VIEW SELLER BUTTON WIRING ==========
  // Wire up View Seller button to use the cart sellers modal with bucket API
  const openBtn = document.getElementById('openSellersBtn');
  if (openBtn && window.actualBucketId) {
    openBtn.addEventListener('click', function(e) {
      e.preventDefault();
      // Set custom URL for bucket sellers API (different from cart sellers)
      window._sellerFetchUrl = function(bucketId) {
        return '/api/bucket/' + bucketId + '/sellers';
      };
      openSellerPopup(window.actualBucketId);
    });
  }

  // ========== PRICE CHART INITIALIZATION ==========
  // Initialize bucket price chart when page loads
  if (window.actualBucketId && typeof initBucketPriceChart === 'function') {
    initBucketPriceChart(window.actualBucketId);
  }
});
