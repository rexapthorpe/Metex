// Header Search Autocomplete
(function() {
    'use strict';

    const searchInput = document.getElementById('headerSearchInput');
    const searchClear = document.getElementById('headerSearchClear');
    const searchDropdown = document.getElementById('headerSearchDropdown');
    const searchResults = document.getElementById('headerSearchResults');
    const headerBar = document.querySelector('.header-bar');

    let searchTimeout = null;
    let currentAbortController = null;

    // === MOBILE SEARCH EXPAND/COLLAPSE ===
    function isMobile() {
        return window.innerWidth <= 768;
    }

    function expandSearch() {
        if (isMobile() && headerBar) {
            headerBar.classList.add('search-expanded');
        }
    }

    function collapseSearch() {
        if (headerBar) {
            headerBar.classList.remove('search-expanded');
        }
    }

    // Expand search bar when focused on mobile
    searchInput.addEventListener('focus', function() {
        expandSearch();
    });

    // Collapse search bar when blurred (with slight delay to allow click events)
    searchInput.addEventListener('blur', function() {
        // Delay collapse to allow click on dropdown items
        setTimeout(function() {
            // Only collapse if dropdown is not being interacted with
            if (!searchDropdown.matches(':hover') && document.activeElement !== searchInput) {
                collapseSearch();
            }
        }, 200);
    });

    // Collapse on escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && headerBar.classList.contains('search-expanded')) {
            collapseSearch();
        }
    });

    // Collapse when clicking outside on mobile
    document.addEventListener('click', function(e) {
        const searchContainer = document.querySelector('.header-search-container');
        if (isMobile() &&
            headerBar.classList.contains('search-expanded') &&
            !searchContainer.contains(e.target)) {
            collapseSearch();
        }
    });

    // Handle window resize - collapse if moving to desktop
    window.addEventListener('resize', function() {
        if (!isMobile()) {
            collapseSearch();
        }
    });

    // Show/hide clear button based on input
    searchInput.addEventListener('input', function() {
        if (this.value.length > 0) {
            searchClear.style.display = 'flex';
        } else {
            searchClear.style.display = 'none';
            hideDropdown();
        }

        // Debounced search
        clearTimeout(searchTimeout);

        if (this.value.trim().length >= 1) {
            searchTimeout = setTimeout(() => {
                performSearch(this.value.trim());
            }, 200);
        } else {
            hideDropdown();
        }
    });

    // Clear button handler
    searchClear.addEventListener('click', function() {
        searchInput.value = '';
        searchClear.style.display = 'none';
        hideDropdown();
        searchInput.focus();
    });

    // Handle Enter key
    searchInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            const query = this.value.trim();
            if (query) {
                navigateToSearch(query);
            }
        } else if (e.key === 'Escape') {
            hideDropdown();
            searchInput.blur();
        }
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (!searchInput.contains(e.target) &&
            !searchDropdown.contains(e.target) &&
            !searchClear.contains(e.target)) {
            hideDropdown();
        }
    });

    // Perform search via API
    async function performSearch(query) {
        // Cancel previous request if still pending
        if (currentAbortController) {
            currentAbortController.abort();
        }

        currentAbortController = new AbortController();

        try {
            const response = await fetch(`/api/search/autocomplete?q=${encodeURIComponent(query)}`, {
                signal: currentAbortController.signal
            });

            if (!response.ok) {
                throw new Error('Search failed');
            }

            const data = await response.json();

            if (data.success) {
                renderResults(data.suggestions, query);
            } else {
                hideDropdown();
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Search error:', error);
                hideDropdown();
            }
        } finally {
            currentAbortController = null;
        }
    }

    // Render search results
    function renderResults(suggestions, query) {
        if (!suggestions || suggestions.length === 0) {
            searchResults.innerHTML = `
                <div class="header-search-no-results">
                    No results found for "${escapeHtml(query)}"
                </div>
            `;
            showDropdown();
            return;
        }

        let html = '';

        // Add suggestion items — two-line layout (title + meta context)
        suggestions.forEach(suggestion => {
            const metaHtml = suggestion.meta
                ? `<span class="header-search-result-meta">${escapeHtml(suggestion.meta)}</span>`
                : '';
            html += `
                <div class="header-search-result-item" data-type="${suggestion.type}" data-id="${suggestion.id || ''}" data-query="${escapeHtml(suggestion.text)}">
                    <i class="fa-solid fa-magnifying-glass header-search-result-icon"></i>
                    <div class="header-search-result-body">
                        <span class="header-search-result-text">${escapeHtml(suggestion.text)}</span>
                        ${metaHtml}
                    </div>
                </div>
            `;
        });

        // Add "Search for..." action at the bottom
        html += `
            <div class="header-search-result-item search-action" data-type="search" data-query="${escapeHtml(query)}">
                <i class="fa-solid fa-magnifying-glass header-search-result-icon"></i>
                <div class="header-search-result-body">
                    <span class="header-search-result-text">Search for '${escapeHtml(query)}'</span>
                </div>
            </div>
        `;

        searchResults.innerHTML = html;

        // Add click handlers to result items
        searchResults.querySelectorAll('.header-search-result-item').forEach(item => {
            item.addEventListener('click', function() {
                const type = this.dataset.type;
                const id = this.dataset.id;
                const q = this.dataset.query;

                if (type === 'search') {
                    navigateToSearch(q);
                } else if (type === 'bucket') {
                    navigateToBucket(id);
                } else if (type === 'listing') {
                    navigateToListing(id);
                } else {
                    navigateToSearch(q);
                }
            });
        });

        showDropdown();
    }

    // Navigation functions
    function navigateToSearch(query) {
        window.location.href = `/buy?search=${encodeURIComponent(query)}`;
    }

    function navigateToBucket(bucketId) {
        window.location.href = `/bucket/${bucketId}`;
    }

    function navigateToListing(listingId) {
        window.location.href = `/listing/${listingId}`;
    }

    // Show/hide dropdown
    function showDropdown() {
        searchDropdown.style.display = 'block';
    }

    function hideDropdown() {
        searchDropdown.style.display = 'none';
    }

    // Utility: Escape HTML to prevent XSS
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

})();
