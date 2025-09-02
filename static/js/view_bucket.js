function increaseQty() {
    const input = document.getElementById("quantityInput");
    input.value = parseInt(input.value) + 1;
  }
  
  function decreaseQty() {
    const input = document.getElementById("quantityInput");
    if (parseInt(input.value) > 1) {
      input.value = parseInt(input.value) - 1;
    }
  }
  
  function syncQuantity(targetId) {
    const selectedQty = document.getElementById("quantityInput").value;
    document.getElementById(targetId).value = selectedQty;
  }
  
  function adjustQty(bidId, delta) {
    const input = document.getElementById('quantity_' + bidId);
    const max = parseInt(input.max);
    let val = parseInt(input.value);
    val += delta;
    if (val >= 1 && val <= max) {
      input.value = val;
    }
  }
  
  function appendGradingToForm(form) {
    const filter = localStorage.getItem('gradingFilter');
    if (!filter) return;
  
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = filter;
    input.value = '1';
    form.appendChild(input);
  }
  
  document.addEventListener('DOMContentLoaded', () => {
    const checkboxes = document.querySelectorAll('.bid-checkbox');
    const submitButton = document.getElementById('acceptBidsButton');
  
    function updateButtonState() {
      const anyChecked = Array.from(checkboxes).some(cb => cb.checked);
      if (submitButton) {
        submitButton.disabled = !anyChecked;
      }
    }
  
    checkboxes.forEach(cb => {
      cb.addEventListener('change', () => {
        const bidId = cb.dataset.bidId;
        const qtyControls = document.getElementById('quantity_controls_' + bidId);
        if (qtyControls) qtyControls.style.display = cb.checked ? 'block' : 'none';
        updateButtonState();
      });
    });
  
    updateButtonState();
  
    // === Grading Toggle Logic ===
    const graderToggles = document.querySelectorAll('.grader-toggle');
  
    graderToggles.forEach(toggle => {
      toggle.addEventListener('change', () => {
        if (toggle.checked) {
          graderToggles.forEach(other => {
            if (other !== toggle) other.checked = false;
          });
          localStorage.setItem('gradingFilter', toggle.name);
        } else {
          localStorage.removeItem('gradingFilter');
        }
      });
    });
  
    // Restore grading toggle from localStorage on page load
    const saved = localStorage.getItem('gradingFilter');
    if (saved) {
      const toggle = document.querySelector(`input[name="${saved}"]`);
      if (toggle) toggle.checked = true;
    }
  
    // Inject grading filter into the actual Buy/Add forms
    const buyForm = document.querySelector('form[action*="checkout"]');
    const cartForm = document.querySelector('form[action*="auto_fill_bucket_purchase"]');
  
    if (buyForm) {
      buyForm.addEventListener('submit', () => {
        appendGradingToForm(buyForm);
      });
    }
  
    if (cartForm) {
      cartForm.addEventListener('submit', () => {
        appendGradingToForm(cartForm);
      });
    }
  
    // Flash message popup
    const messages = window.flashMessages || [];
    const container = document.getElementById('popup-message-container');
    if (container && messages.length) {
      messages.forEach(([category, message]) => {
        const popup = document.createElement('div');
        popup.className = 'popup-alert ' + category;
        popup.textContent = message;
        container.appendChild(popup);
  
        setTimeout(() => {
          popup.remove();
        }, 5000);
      });
    }
  });
  