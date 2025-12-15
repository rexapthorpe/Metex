// static/js/format_utils.js
'use strict';

/**
 * Format a number with comma separators for thousands.
 * Preserves decimal parts. Examples: 1234 -> "1,234" | 1234.56 -> "1,234.56"
 * @param {number|string} value - The number to format
 * @param {number} decimals - Optional: number of decimal places to force (default: preserve original)
 * @returns {string} Formatted number string with commas
 */
function formatWithCommas(value, decimals = null) {
    if (value === null || value === undefined || value === '') {
        return '';
    }

    try {
        // Convert to number
        const num = typeof value === 'string' ? parseFloat(value) : value;

        if (isNaN(num)) {
            return String(value);
        }

        // If decimals parameter is provided, use toFixed
        if (decimals !== null) {
            return num.toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        }

        // Otherwise, preserve original decimal places
        const parts = num.toString().split('.');
        parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        return parts.join('.');
    } catch (e) {
        return String(value);
    }
}

/**
 * Format a price with commas and exactly 2 decimal places.
 * Example: 1234.5 -> "$1,234.50"
 * @param {number|string} value - The price to format
 * @param {boolean} includeSymbol - Whether to include $ symbol (default: true)
 * @returns {string} Formatted price string
 */
function formatPrice(value, includeSymbol = true) {
    const formatted = formatWithCommas(value, 2);
    return includeSymbol ? `$${formatted}` : formatted;
}

/**
 * Format a quantity with commas (no decimals).
 * Example: 1234 -> "1,234"
 * @param {number|string} value - The quantity to format
 * @returns {string} Formatted quantity string
 */
function formatQuantity(value) {
    return formatWithCommas(Math.floor(value), 0);
}
