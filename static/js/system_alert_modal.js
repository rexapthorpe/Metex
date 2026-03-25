/**
 * System Alert Modal - Custom styled alerts
 * Replaces browser native alert/confirm/prompt with professional modals
 *
 * Usage:
 *   alert('Message') - Shows info modal
 *   confirm('Question?') - Shows confirm modal, returns Promise<boolean>
 *   prompt('Enter value:', 'default') - Shows prompt modal, returns Promise<string|null>
 *
 * Note: Since native alert/confirm/prompt are synchronous and our modals are async,
 * the overridden functions return Promises. For backward compatibility with code
 * expecting synchronous behavior, we also provide:
 *   showAlert(message, options) - Returns Promise
 *   showConfirm(message, options) - Returns Promise<boolean>
 *   showPrompt(message, defaultValue, options) - Returns Promise<string|null>
 */

(function() {
  'use strict';

  // Store original functions for fallback
  const originalAlert = window.alert;
  const originalConfirm = window.confirm;
  const originalPrompt = window.prompt;

  // Create modal HTML structure
  function createModalHTML() {
    const container = document.createElement('div');
    container.id = 'systemAlertOverlay';
    container.className = 'system-alert-overlay';
    container.innerHTML = `
      <div class="system-alert-modal" role="dialog" aria-modal="true" aria-labelledby="systemAlertTitle">
        <div class="system-alert-header">
          <div class="system-alert-icon info" id="systemAlertIcon">
            <i class="fa-solid fa-circle-info"></i>
          </div>
          <h3 class="system-alert-title" id="systemAlertTitle">Notice</h3>
        </div>
        <div class="system-alert-body">
          <p class="system-alert-message" id="systemAlertMessage"></p>
          <input type="text" class="system-alert-input" id="systemAlertInput" style="display: none;">
        </div>
        <div class="system-alert-footer" id="systemAlertFooter">
          <button type="button" class="system-alert-btn system-alert-btn-secondary" id="systemAlertCancel">Cancel</button>
          <button type="button" class="system-alert-btn system-alert-btn-primary" id="systemAlertConfirm">OK</button>
        </div>
      </div>
    `;
    return container;
  }

  // Initialize modal in DOM
  let modalOverlay = null;
  let modalElements = {};
  let resolveCallback = null;
  let modalType = 'alert';

  function ensureModalExists() {
    if (!modalOverlay) {
      modalOverlay = createModalHTML();
      document.body.appendChild(modalOverlay);

      modalElements = {
        overlay: modalOverlay,
        icon: modalOverlay.querySelector('#systemAlertIcon'),
        title: modalOverlay.querySelector('#systemAlertTitle'),
        message: modalOverlay.querySelector('#systemAlertMessage'),
        input: modalOverlay.querySelector('#systemAlertInput'),
        footer: modalOverlay.querySelector('#systemAlertFooter'),
        cancelBtn: modalOverlay.querySelector('#systemAlertCancel'),
        confirmBtn: modalOverlay.querySelector('#systemAlertConfirm')
      };

      // Event listeners
      modalElements.confirmBtn.addEventListener('click', handleConfirm);
      modalElements.cancelBtn.addEventListener('click', handleCancel);
      modalOverlay.addEventListener('click', handleOverlayClick);
      document.addEventListener('keydown', handleKeydown);
    }
  }

  function handleConfirm() {
    const value = modalType === 'prompt' ? modalElements.input.value : true;
    closeModal();
    if (resolveCallback) {
      resolveCallback(value);
      resolveCallback = null;
    }
  }

  function handleCancel() {
    closeModal();
    if (resolveCallback) {
      resolveCallback(modalType === 'prompt' ? null : false);
      resolveCallback = null;
    }
  }

  function handleOverlayClick(e) {
    if (e.target === modalOverlay) {
      // For alerts, clicking outside confirms; for confirm/prompt, it cancels
      if (modalType === 'alert') {
        handleConfirm();
      } else {
        handleCancel();
      }
    }
  }

  function handleKeydown(e) {
    if (!modalOverlay || !modalOverlay.classList.contains('show')) return;

    if (e.key === 'Escape') {
      if (modalType === 'alert') {
        handleConfirm();
      } else {
        handleCancel();
      }
    } else if (e.key === 'Enter') {
      handleConfirm();
    }
  }

  function closeModal() {
    if (modalOverlay) {
      modalOverlay.classList.remove('show');
      modalElements.input.style.display = 'none';
      modalElements.input.value = '';
      // Wait for slide-down transition before hiding
      setTimeout(() => {
        if (!modalOverlay.classList.contains('show')) {
          modalOverlay.style.display = 'none';
        }
      }, 350);
    }
  }

  function showModal(options) {
    ensureModalExists();

    const {
      type = 'alert',
      title = 'Notice',
      message = '',
      confirmText = 'OK',
      cancelText = 'Cancel',
      defaultValue = '',
      iconType = 'info'
    } = options;

    modalType = type;

    // Set icon
    const iconMap = {
      info: { class: 'info', icon: 'fa-circle-info' },
      warning: { class: 'warning', icon: 'fa-triangle-exclamation' },
      error: { class: 'error', icon: 'fa-circle-xmark' },
      success: { class: 'success', icon: 'fa-circle-check' },
      question: { class: 'question', icon: 'fa-circle-question' }
    };

    const iconConfig = iconMap[iconType] || iconMap.info;
    modalElements.icon.className = `system-alert-icon ${iconConfig.class}`;
    modalElements.icon.innerHTML = `<i class="fa-solid ${iconConfig.icon}"></i>`;

    // Set content
    modalElements.title.textContent = title;
    modalElements.message.textContent = message;

    // Configure buttons based on type
    if (type === 'alert') {
      modalElements.cancelBtn.style.display = 'none';
      modalElements.footer.classList.add('single-button');
    } else {
      modalElements.cancelBtn.style.display = '';
      modalElements.footer.classList.remove('single-button');
      modalElements.cancelBtn.textContent = cancelText;
    }

    modalElements.confirmBtn.textContent = confirmText;

    // Configure input for prompt
    if (type === 'prompt') {
      modalElements.input.style.display = '';
      modalElements.input.value = defaultValue;
      setTimeout(() => {
        modalElements.input.focus();
        modalElements.input.select();
      }, 100);
    } else {
      modalElements.input.style.display = 'none';
    }

    // Show modal — set display first, then force reflow before adding class
    // so the translateY(100%) → translateY(0) transition actually fires
    modalOverlay.style.display = 'flex';
    modalOverlay.offsetHeight; // force reflow
    modalOverlay.classList.add('show');

    // Focus confirm button for non-prompt modals
    if (type !== 'prompt') {
      setTimeout(() => modalElements.confirmBtn.focus(), 100);
    }

    return new Promise((resolve) => {
      resolveCallback = resolve;
    });
  }

  // Public API functions

  /**
   * Show an alert modal
   * @param {string} message - The message to display
   * @param {Object} options - Optional configuration
   * @returns {Promise<void>}
   */
  window.showAlert = function(message, options = {}) {
    return showModal({
      type: 'alert',
      title: options.title || 'Notice',
      message: String(message),
      confirmText: options.confirmText || 'OK',
      iconType: options.iconType || 'info'
    });
  };

  /**
   * Show a confirm modal
   * @param {string} message - The question to ask
   * @param {Object} options - Optional configuration
   * @returns {Promise<boolean>}
   */
  window.showConfirm = function(message, options = {}) {
    return showModal({
      type: 'confirm',
      title: options.title || 'Confirm',
      message: String(message),
      confirmText: options.confirmText || 'OK',
      cancelText: options.cancelText || 'Cancel',
      iconType: options.iconType || 'question'
    });
  };

  /**
   * Show a prompt modal
   * @param {string} message - The prompt message
   * @param {string} defaultValue - Default input value
   * @param {Object} options - Optional configuration
   * @returns {Promise<string|null>}
   */
  window.showPrompt = function(message, defaultValue = '', options = {}) {
    return showModal({
      type: 'prompt',
      title: options.title || 'Input Required',
      message: String(message),
      confirmText: options.confirmText || 'OK',
      cancelText: options.cancelText || 'Cancel',
      defaultValue: String(defaultValue),
      iconType: options.iconType || 'question'
    });
  };

  // Override native functions
  // Note: These return Promises, which may break synchronous code expecting immediate values

  window.alert = function(message) {
    // Return promise but don't wait - this maintains backward compatibility
    // for code that doesn't expect a return value from alert()
    return showModal({
      type: 'alert',
      title: 'Notice',
      message: String(message),
      iconType: 'info'
    });
  };

  window.confirm = function(message) {
    // Returns a Promise<boolean> - use with await or .then()
    return showModal({
      type: 'confirm',
      title: 'Confirm',
      message: String(message),
      iconType: 'question'
    });
  };

  window.prompt = function(message, defaultValue) {
    // Returns a Promise<string|null> - use with await or .then()
    return showModal({
      type: 'prompt',
      title: 'Input Required',
      message: String(message),
      defaultValue: defaultValue !== undefined ? String(defaultValue) : '',
      iconType: 'question'
    });
  };

  // Expose original functions if needed
  window.nativeAlert = originalAlert;
  window.nativeConfirm = originalConfirm;
  window.nativePrompt = originalPrompt;

})();
