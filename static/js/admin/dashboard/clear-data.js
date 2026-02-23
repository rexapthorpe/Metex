function openClearDataModal() {
  const modal = document.getElementById('clearDataModal');
  const input = document.getElementById('clearDataConfirmInput');
  const btn = document.getElementById('clearDataBtn');

  // Reset state
  input.value = '';
  btn.disabled = true;
  deselectAllClearOptions();

  // Set up input validation
  input.oninput = validateClearDataForm;

  // Set up checkbox change handlers
  const checkboxes = document.querySelectorAll('input[name="clear_option"]');
  checkboxes.forEach(cb => {
    cb.onchange = () => {
      updateSelectedCount();
      validateClearDataForm();
    };
  });

  modal.style.display = 'flex';
}

function validateClearDataForm() {
  const input = document.getElementById('clearDataConfirmInput');
  const btn = document.getElementById('clearDataBtn');
  const checkboxes = document.querySelectorAll('input[name="clear_option"]:checked');

  const confirmValid = input.value === 'CONFIRM DELETE';
  const hasSelection = checkboxes.length > 0;

  btn.disabled = !(confirmValid && hasSelection);
}

function updateSelectedCount() {
  const checkboxes = document.querySelectorAll('input[name="clear_option"]:checked');
  const countEl = document.getElementById('clearDataSelectedCount');
  const count = checkboxes.length;

  if (count === 0) {
    countEl.innerHTML = '<i class="fa-solid fa-circle-info"></i><span>No data types selected</span>';
    countEl.classList.remove('has-selection');
  } else {
    const labels = Array.from(checkboxes).map(cb => {
      const label = cb.closest('.clear-data-option').querySelector('.option-label');
      return label ? label.textContent : cb.value;
    });
    countEl.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i><span>${count} selected: ${labels.join(', ')}</span>`;
    countEl.classList.add('has-selection');
  }
}

function selectAllClearOptions() {
  const checkboxes = document.querySelectorAll('input[name="clear_option"]');
  checkboxes.forEach(cb => cb.checked = true);
  updateSelectedCount();
  validateClearDataForm();
}

function deselectAllClearOptions() {
  const checkboxes = document.querySelectorAll('input[name="clear_option"]');
  checkboxes.forEach(cb => cb.checked = false);
  updateSelectedCount();
  validateClearDataForm();
}

function selectMarketplaceData() {
  deselectAllClearOptions();
  const marketplaceOptions = ['listings', 'orders', 'bids', 'cart', 'ratings', 'price_history', 'messages', 'notifications', 'buckets'];
  marketplaceOptions.forEach(opt => {
    const cb = document.querySelector(`input[name="clear_option"][value="${opt}"]`);
    if (cb) cb.checked = true;
  });
  updateSelectedCount();
  validateClearDataForm();
}

function closeClearDataModal() {
  const modal = document.getElementById('clearDataModal');
  const dialog = document.getElementById('clearDataDialog');
  const successContent = document.getElementById('clearDataSuccessContent');

  modal.style.display = 'none';
  document.getElementById('clearDataConfirmInput').value = '';
  document.getElementById('clearDataBtn').disabled = true;

  // Reset success state
  dialog.classList.remove('success');
  successContent.classList.remove('show');
}

function closeClearDataModalAndRefresh() {
  closeClearDataModal();
  location.reload();
}

function showClearDataSuccess(message) {
  const dialog = document.getElementById('clearDataDialog');
  const successContent = document.getElementById('clearDataSuccessContent');
  const successMessage = document.getElementById('clearDataSuccessMessage');

  // Update message
  successMessage.textContent = message;

  // Show success animation
  dialog.classList.add('success');
  successContent.classList.add('show');
}

async function executeClearData() {
  const input = document.getElementById('clearDataConfirmInput');
  const btn = document.getElementById('clearDataBtn');
  const checkboxes = document.querySelectorAll('input[name="clear_option"]:checked');

  // Double-check confirmation
  if (input.value !== 'CONFIRM DELETE') {
    alert('Please type CONFIRM DELETE to proceed');
    return;
  }

  // Get selected options
  const selectedOptions = Array.from(checkboxes).map(cb => cb.value);

  if (selectedOptions.length === 0) {
    alert('Please select at least one data type to clear');
    return;
  }

  // Disable button and show loading
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Deleting...';

  try {
    const response = await fetch('/admin/api/clear-data', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ options: selectedOptions })
    });

    const data = await response.json();

    if (data.success) {
      // Show success animation with message
      showClearDataSuccess(data.message);
    } else {
      alert('Error: ' + data.error);
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-trash-can"></i> Delete Selected Data';
    }
  } catch (error) {
    console.error('Clear data error:', error);
    alert('Failed to clear data. Please try again.');
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-trash-can"></i> Delete Selected Data';
  }
}

