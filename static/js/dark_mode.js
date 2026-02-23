/**
 * Dark Mode Toggle System
 * Handles dark mode toggle functionality with localStorage persistence
 */

(function() {
    'use strict';

    const DARK_MODE_KEY = 'metex_dark_mode';

    /**
     * Check if dark mode is enabled in localStorage
     */
    function isDarkModeEnabled() {
        const stored = localStorage.getItem(DARK_MODE_KEY);
        if (stored !== null) {
            return stored === 'true';
        }
        // Default to light mode if no stored preference
        return false;
    }

    /**
     * Apply dark mode to the document
     */
    function applyDarkMode(enabled) {
        if (enabled) {
            document.body.classList.add('dark-mode');
        } else {
            document.body.classList.remove('dark-mode');
        }
        // Update toggle button icons
        updateToggleButton(enabled);
    }

    /**
     * Update the toggle button icon
     */
    function updateToggleButton(isDark) {
        const toggleBtn = document.getElementById('darkModeToggle');
        if (toggleBtn) {
            const moonIcon = toggleBtn.querySelector('.fa-moon');
            const sunIcon = toggleBtn.querySelector('.fa-sun');
            if (moonIcon && sunIcon) {
                moonIcon.style.display = isDark ? 'none' : 'inline-block';
                sunIcon.style.display = isDark ? 'inline-block' : 'none';
            }
            toggleBtn.setAttribute('title', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
        }
    }

    /**
     * Toggle dark mode on/off
     */
    function toggleDarkMode() {
        const isCurrentlyDark = document.body.classList.contains('dark-mode');
        const newMode = !isCurrentlyDark;

        // Save preference to localStorage
        localStorage.setItem(DARK_MODE_KEY, newMode.toString());

        // Apply the new mode
        applyDarkMode(newMode);

        // Dispatch custom event for other scripts to listen to
        window.dispatchEvent(new CustomEvent('darkModeChanged', {
            detail: { isDarkMode: newMode }
        }));
    }

    /**
     * Initialize dark mode on page load
     */
    function initDarkMode() {
        // Apply saved preference immediately (before DOMContentLoaded to prevent flash)
        const enabled = isDarkModeEnabled();
        applyDarkMode(enabled);
    }

    /**
     * Setup event listeners after DOM is ready
     */
    function setupEventListeners() {
        // Toggle button click handler
        const toggleBtn = document.getElementById('darkModeToggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', function(e) {
                e.preventDefault();
                toggleDarkMode();
            });
        }

        // Listen for system preference changes
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
                // Only auto-switch if user hasn't set a preference
                if (localStorage.getItem(DARK_MODE_KEY) === null) {
                    applyDarkMode(e.matches);
                }
            });
        }
    }

    // Initialize dark mode as early as possible
    initDarkMode();

    // Setup event listeners when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupEventListeners);
    } else {
        setupEventListeners();
    }

    // Expose functions globally for external use
    window.MetExDarkMode = {
        toggle: toggleDarkMode,
        enable: function() {
            localStorage.setItem(DARK_MODE_KEY, 'true');
            applyDarkMode(true);
        },
        disable: function() {
            localStorage.setItem(DARK_MODE_KEY, 'false');
            applyDarkMode(false);
        },
        isEnabled: function() {
            return document.body.classList.contains('dark-mode');
        }
    };
})();
