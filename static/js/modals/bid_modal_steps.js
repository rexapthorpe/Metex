/**
 * Bid Modal Step Navigation - Lovable Specification
 * Handles multi-step form flow for creating/editing bids
 */

(function() {
  let currentStep = 1;
  const totalSteps = 4;

  /**
   * Initialize step navigation when DOM is ready
   */
  function initStepNavigation() {
    const btnBack = document.getElementById('btn-back');
    const btnContinue = document.getElementById('btn-continue');
    const btnSubmit = document.getElementById('btn-submit');

    if (!btnBack || !btnContinue || !btnSubmit) {
      console.warn('Step navigation buttons not found');
      return;
    }

    // Back button handler
    btnBack.addEventListener('click', () => {
      if (currentStep > 1) {
        goToStep(currentStep - 1);
      }
    });

    // Continue button handler
    btnContinue.addEventListener('click', () => {
      if (validateCurrentStep()) {
        if (currentStep < totalSteps) {
          goToStep(currentStep + 1);
        }
      }
    });

    // Initialize quantity stepper
    initQuantityStepper();

    // Initialize pricing mode toggle
    initPricingModeToggle();

    // Initialize variable pricing calculator
    initVariablePricingCalculator();

    // Initialize grading checkboxes
    initGradingCheckboxes();

    // Initialize address selector
    initAddressSelector();

    // Initialize payment radios
    initPaymentRadios();
  }

  /**
   * Navigate to a specific step
   */
  function goToStep(stepNumber) {
    if (stepNumber < 1 || stepNumber > totalSteps) {
      return;
    }

    // Hide all step content
    document.querySelectorAll('.step-content').forEach(content => {
      content.classList.remove('active');
    });

    // Show target step content
    const targetContent = document.getElementById(`step-${stepNumber}`);
    if (targetContent) {
      targetContent.classList.add('active');
    }

    // Update step indicator
    document.querySelectorAll('.step-item').forEach((step, index) => {
      const stepNum = index + 1;
      step.classList.remove('active', 'completed');

      if (stepNum < stepNumber) {
        step.classList.add('completed');
      } else if (stepNum === stepNumber) {
        step.classList.add('active');
      }
    });

    // Update navigation buttons
    const btnBack = document.getElementById('btn-back');
    const btnContinue = document.getElementById('btn-continue');
    const btnSubmit = document.getElementById('btn-submit');

    // Show/hide back button
    btnBack.style.display = stepNumber === 1 ? 'none' : 'inline-flex';

    // Show continue or submit button
    if (stepNumber === totalSteps) {
      btnContinue.style.display = 'none';
      btnSubmit.style.display = 'inline-flex';
    } else {
      btnContinue.style.display = 'inline-flex';
      btnSubmit.style.display = 'none';
    }

    currentStep = stepNumber;
  }

  /**
   * Validate current step before proceeding
   */
  function validateCurrentStep() {
    switch (currentStep) {
      case 1: // Pricing
        return validatePricingStep();
      case 2: // Options
        return true; // Options are optional
      case 3: // Delivery
        return validateDeliveryStep();
      case 4: // Payment
        return true; // Payment already selected
      default:
        return true;
    }
  }

  /**
   * Validate pricing step
   */
  function validatePricingStep() {
    const pricingMode = document.getElementById('bid-pricing-mode').value;
    const quantity = parseInt(document.getElementById('qty-input').value);

    if (!quantity || quantity < 1) {
      alert('Please enter a valid quantity');
      return false;
    }

    if (pricingMode === 'static') {
      const price = parseFloat(document.getElementById('bid-price-input').value);
      if (!price || price <= 0) {
        alert('Please enter a valid price');
        return false;
      }
    } else if (pricingMode === 'variable') {
      const ceiling = parseFloat(document.getElementById('bid-ceiling-price').value);
      if (!ceiling || ceiling <= 0) {
        alert('Please enter a valid floor price');
        return false;
      }
    }

    return true;
  }

  /**
   * Validate delivery step
   */
  function validateDeliveryStep() {
    const line1 = document.getElementById('addr-line1').value.trim();
    const city = document.getElementById('addr-city').value.trim();
    const state = document.getElementById('addr-state').value;
    const zip = document.getElementById('addr-zip').value.trim();

    if (!line1 || !city || !state || !zip) {
      alert('Please fill in all required address fields');
      return false;
    }

    return true;
  }

  /**
   * Initialize quantity stepper
   */
  function initQuantityStepper() {
    const qtyInput = document.getElementById('qty-input');
    const qtyDisplay = document.getElementById('qty-display');
    const qtyMinus = document.getElementById('qty-minus');
    const qtyPlus = document.getElementById('qty-plus');

    if (!qtyInput || !qtyDisplay || !qtyMinus || !qtyPlus) return;

    qtyMinus.addEventListener('click', () => {
      let currentValue = parseInt(qtyInput.value) || 1;
      if (currentValue > 1) {
        qtyInput.value = currentValue - 1;
        qtyDisplay.textContent = currentValue - 1;
      }
    });

    qtyPlus.addEventListener('click', () => {
      let currentValue = parseInt(qtyInput.value) || 1;
      qtyInput.value = currentValue + 1;
      qtyDisplay.textContent = currentValue + 1;
    });
  }

  /**
   * Update spot price display
   */
  function updateSpotPriceDisplay() {
    const metalSelect = document.getElementById('bid-pricing-metal');
    const premiumInput = document.getElementById('bid-spot-premium');
    const spotMetalName = document.getElementById('spot-metal-name');
    const spotPriceDisplay = document.getElementById('spot-price-display');
    const spotCalcDisplay = document.getElementById('spot-calc-display');

    if (!metalSelect || !spotMetalName || !spotPriceDisplay || !spotCalcDisplay) {
      console.log('Spot price elements not found');
      return;
    }

    // Get live spot prices from cache (fetched from API via bid_modal.js)
    const spotPrices = typeof getSpotPrices === 'function'
      ? getSpotPrices()
      : { 'Gold': 0, 'Silver': 0, 'Platinum': 0, 'Palladium': 0 };

    const selectedMetal = metalSelect.value;
    const spotPrice = spotPrices[selectedMetal] || 0;
    const premium = parseFloat(premiumInput ? premiumInput.value : 0) || 0;
    const totalBid = spotPrice + premium;

    spotMetalName.textContent = selectedMetal;
    spotPriceDisplay.textContent = formatPrice(spotPrice);
    spotCalcDisplay.textContent = `Your bid: Spot + ${formatPrice(premium)} = ${formatPrice(totalBid)}`;

    console.log('Updated spot price display:', { selectedMetal, spotPrice, premium, totalBid });
  }

  /**
   * Initialize pricing mode dropdown
   */
  function initPricingModeToggle() {
    console.log('Initializing pricing mode toggle...');

    const modeSelect = document.getElementById('bid-pricing-mode');
    const staticSection = document.getElementById('static-pricing-section');
    const premiumSection = document.getElementById('premium-pricing-section');
    const helperText = document.getElementById('pricing-mode-helper');

    console.log('Elements found:', {
      modeSelect: !!modeSelect,
      staticSection: !!staticSection,
      premiumSection: !!premiumSection,
      helperText: !!helperText
    });

    if (!modeSelect) {
      console.error('CRITICAL: Pricing mode select not found!');
      return;
    }

    if (!staticSection || !premiumSection) {
      console.error('CRITICAL: Pricing sections not found!', {
        staticSection: !!staticSection,
        premiumSection: !!premiumSection
      });
      return;
    }

    console.log('Initial mode value:', modeSelect.value);

    // Handle dropdown change
    modeSelect.addEventListener('change', function(e) {
      const selectedMode = this.value;
      console.log('=== PRICING MODE CHANGED ===');
      console.log('New mode:', selectedMode);

      if (selectedMode === 'static') {
        staticSection.style.display = 'block';
        premiumSection.style.display = 'none';
        if (helperText) {
          helperText.textContent = 'Enter a fixed price per item.';
        }
        console.log('✓ Switched to static pricing');
        console.log('Static display:', staticSection.style.display);
        console.log('Premium display:', premiumSection.style.display);
      } else if (selectedMode === 'variable') {
        staticSection.style.display = 'none';
        premiumSection.style.display = 'block';
        if (helperText) {
          helperText.textContent = 'Bid tracks live spot price plus your premium.';
        }
        console.log('✓ Switched to variable pricing');
        console.log('Static display:', staticSection.style.display);
        console.log('Premium display:', premiumSection.style.display);
        // Update spot price display when switching to variable
        setTimeout(updateSpotPriceDisplay, 100);
      }
    });

    console.log('Event listener attached to dropdown');

    // Initialize display based on current selection
    const initialMode = modeSelect.value;
    console.log('Setting initial display for mode:', initialMode);

    if (initialMode === 'static') {
      staticSection.style.display = 'block';
      premiumSection.style.display = 'none';
      console.log('Initial: Static pricing shown');
    } else if (initialMode === 'variable') {
      staticSection.style.display = 'none';
      premiumSection.style.display = 'block';
      console.log('Initial: Variable pricing shown');
      setTimeout(updateSpotPriceDisplay, 100);
    }

    console.log('Pricing mode toggle initialization complete');
  }

  /**
   * Initialize variable pricing calculator
   */
  function initVariablePricingCalculator() {
    const metalSelect = document.getElementById('bid-pricing-metal');
    const premiumInput = document.getElementById('bid-spot-premium');

    if (metalSelect) {
      metalSelect.addEventListener('change', updateSpotPriceDisplay);
    }

    if (premiumInput) {
      premiumInput.addEventListener('input', updateSpotPriceDisplay);
    }

    // Initial update
    updateSpotPriceDisplay();
  }

  /**
   * Initialize grading checkboxes (mutual exclusivity)
   */
  function initGradingCheckboxes() {
    const anyGrader = document.getElementById('grader_any');
    const pcgs = document.getElementById('grader_pcgs');
    const ngc = document.getElementById('grader_ngc');
    const requiresGrading = document.getElementById('requires_grading');
    const preferredGrader = document.getElementById('preferred_grader');

    if (!anyGrader || !pcgs || !ngc) return;

    [anyGrader, pcgs, ngc].forEach(checkbox => {
      checkbox.addEventListener('change', function() {
        if (this.checked) {
          // Uncheck others
          [anyGrader, pcgs, ngc].forEach(cb => {
            if (cb !== this) cb.checked = false;
          });

          // Update hidden fields
          requiresGrading.value = 'yes';
          if (this === anyGrader) preferredGrader.value = 'Any';
          else if (this === pcgs) preferredGrader.value = 'PCGS';
          else if (this === ngc) preferredGrader.value = 'NGC';
        } else {
          // If unchecked and no others are checked
          const anyChecked = [anyGrader, pcgs, ngc].some(cb => cb.checked);
          if (!anyChecked) {
            requiresGrading.value = 'no';
            preferredGrader.value = '';
          }
        }
      });
    });
  }

  /**
   * Initialize address selector
   */
  function initAddressSelector() {
    const selector = document.getElementById('addr-selector');
    if (!selector) return;

    selector.addEventListener('change', function() {
      if (this.value === 'custom') {
        // Clear fields
        document.getElementById('addr-line1').value = '';
        document.getElementById('addr-line2').value = '';
        document.getElementById('addr-city').value = '';
        document.getElementById('addr-state').value = '';
        document.getElementById('addr-zip').value = '';
      } else {
        // Load selected address
        const option = this.options[this.selectedIndex];
        document.getElementById('addr-line1').value = option.dataset.line1 || '';
        document.getElementById('addr-line2').value = option.dataset.line2 || '';
        document.getElementById('addr-city').value = option.dataset.city || '';
        document.getElementById('addr-state').value = option.dataset.state || '';
        document.getElementById('addr-zip').value = option.dataset.zip || '';
      }
    });
  }

  /**
   * Initialize payment radio buttons
   */
  function initPaymentRadios() {
    const radios = document.querySelectorAll('.radio-option');

    radios.forEach(radio => {
      radio.addEventListener('click', function() {
        // Remove selected class from all
        radios.forEach(r => r.classList.remove('selected'));
        // Add selected class to clicked
        this.classList.add('selected');
        // Check the radio input
        const input = this.querySelector('input[type="radio"]');
        if (input) input.checked = true;
      });
    });
  }

  /**
   * Initialize on DOM ready
   */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStepNavigation);
  } else {
    initStepNavigation();
  }

  // Export for external use
  window.initBidModalSteps = initStepNavigation;
})();
