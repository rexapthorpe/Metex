        minimumFractionDigits: 0,
        maximumFractionDigits: 2
    });
}

/**
 * Format number with commas
 */
function formatNumber(value) {
    if (value === null || value === undefined) return '0';
    return parseFloat(value).toLocaleString('en-US');
}

/**
 * Format date (no time): DD, DayName, MonthName, YYYY
 */
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return String(dateString);
    const dd = String(date.getDate()).padStart(2, '0');
    const dayName = date.toLocaleDateString('en-US', { weekday: 'long' });
    const monthName = date.toLocaleDateString('en-US', { month: 'long' });
    const yyyy = date.getFullYear();
    return `${dd}, ${dayName}, ${monthName}, ${yyyy}`;
}

/**
 * Format datetime: HH:MM, DD, DayName, MonthName, YYYY
 */
function formatDateTime(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return String(dateString);
    const hh = String(date.getHours()).padStart(2, '0');
    const mm = String(date.getMinutes()).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    const dayName = date.toLocaleDateString('en-US', { weekday: 'long' });
    const monthName = date.toLocaleDateString('en-US', { month: 'long' });
    const yyyy = date.getFullYear();
    return `${hh}:${mm}, ${dd}, ${dayName}, ${monthName}, ${yyyy}`;
}

// ============================================================================
// KPI DRILLDOWN FUNCTIONALITY
// ============================================================================

// Drilldown state
let drilldownState = {
    currentType: null,
    offset: 0,
    limit: 50,
    hasMore: false,
    search: '',
    filter: null
};

/**
 * Initialize KPI drilldown click handlers
 */
document.addEventListener('DOMContentLoaded', function() {
    // KPI card click handlers
    const kpiCards = document.querySelectorAll('.kpi-card.clickable');
    kpiCards.forEach(card => {
        card.addEventListener('click', function() {
            const drilldownType = this.getAttribute('data-drilldown');
            openDrilldown(drilldownType);
        });
    });

    // Modal close handlers
    document.getElementById('drilldownModalClose').addEventListener('click', closeDrilldown);
    document.getElementById('drilldownModalOverlay').addEventListener('click', closeDrilldown);
    document.getElementById('userDetailModalClose').addEventListener('click', closeUserDetail);
    document.getElementById('userDetailModalOverlay').addEventListener('click', closeUserDetail);

    // Close modals on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeDrilldown();
            closeUserDetail();
        }
    });
});

/**
 * Open drilldown modal
 */
function openDrilldown(type) {
    drilldownState = {
        currentType: type,
        offset: 0,
        limit: 50,
        hasMore: false,
        search: '',
        filter: null
    };

    const modal = document.getElementById('drilldownModal');
    const overlay = document.getElementById('drilldownModalOverlay');
    const title = document.getElementById('drilldownModalTitle');

    // Set title based on type
    const titles = {
        volume: 'Volume Drilldown',
        revenue: 'Revenue Drilldown',
        trades: 'Trades Drilldown',
        listings: 'Active Listings',
        users: 'User Analytics',
        conversion: 'User Analytics'
    };

    title.textContent = titles[type] || 'Details';

    // Show modal
    overlay.classList.add('active');
    modal.classList.add('active');

    // Load drilldown data
    loadDrilldownData(type);
}

/**
 * Close drilldown modal
 */
function closeDrilldown() {
    const modal = document.getElementById('drilldownModal');
    const overlay = document.getElementById('drilldownModalOverlay');

    modal.classList.remove('active');
    overlay.classList.remove('active');

    // Clear modal body after transition
    setTimeout(() => {
        document.getElementById('drilldownModalBody').innerHTML = '';
    }, 300);
}

/**
 * Load drilldown data based on type
 */
async function loadDrilldownData(type) {
    const modalBody = document.getElementById('drilldownModalBody');
    modalBody.innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><p>Loading...</p></div>';

    try {
        let data;
        switch (type) {
            case 'volume':
                data = await fetchVolumeDrilldown();
                renderVolumeDrilldown(data);
                break;
            case 'revenue':
                data = await fetchRevenueDrilldown();
                renderRevenueDrilldown(data);
                break;
            case 'trades':
                data = await fetchTradesDrilldown();
                renderTradesDrilldown(data);
                break;
            case 'listings':
                data = await fetchListingsDrilldown();
                renderListingsDrilldown(data);
                break;
            case 'users':
            case 'conversion':
                data = await fetchUsersDrilldown();
                renderUsersDrilldown(data);
                break;
        }
    } catch (error) {
        console.error('Error loading drilldown data:', error);
        modalBody.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-circle"></i><p>Error loading data</p></div>';
    }
}

/**
 * Fetch volume drilldown data
 */
async function fetchVolumeDrilldown() {
    const params = getDateRangeParams();
    params.append('limit', drilldownState.limit);
    params.append('offset', drilldownState.offset);

    const response = await fetch(`/admin/analytics/drilldown/volume?${params}`);
    const result = await response.json();

    if (!result.success) throw new Error(result.error);

    drilldownState.hasMore = result.data.has_more;
    return result.data;
}

/**
 * Render volume drilldown
 */
function renderVolumeDrilldown(data) {
    const modalBody = document.getElementById('drilldownModalBody');

    let html = '';

    // Summary stats
    if (data.summary) {
        html += `
            <div class="drilldown-summary">
                <div class="drilldown-summary-item">
                    <div class="drilldown-summary-label">Total Orders</div>
                    <div class="drilldown-summary-value">${formatNumber(data.summary.total_count)}</div>
                </div>
                <div class="drilldown-summary-item">
                    <div class="drilldown-summary-label">Total Volume</div>
                    <div class="drilldown-summary-value">${formatCurrency(data.summary.total_volume)}</div>
                </div>
                <div class="drilldown-summary-item">
                    <div class="drilldown-summary-label">Avg Order Size</div>
                    <div class="drilldown-summary-value">${formatCurrency(data.summary.avg_order_size)}</div>
                </div>
                <div class="drilldown-summary-item">
                    <div class="drilldown-summary-label">Largest Order</div>
                    <div class="drilldown-summary-value">${formatCurrency(data.summary.largest_order)}</div>
                </div>
            </div>
        `;
    }

    // Orders table
    html += `
        <table class="analytics-table">
            <thead>
                <tr>
                    <th>Order ID</th>
                    <th>Date</th>
                    <th>Buyer</th>
                    <th>Total Price</th>
                    <th>Items</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
    `;

    if (data.orders && data.orders.length > 0) {
        data.orders.forEach(order => {
            html += `
                <tr>
                    <td>#${order.order_id}</td>
                    <td>${formatDate(order.order_date)}</td>
                    <td>${order.buyer_username}</td>
                    <td>${formatCurrency(order.total_price)}</td>
                    <td>${formatNumber(order.item_count)}</td>
                    <td><span class="status-badge ${order.status.toLowerCase()}">${order.status}</span></td>
                </tr>
            `;
        });
    } else {
        html += '<tr class="no-data"><td colspan="6">No orders found</td></tr>';
    }

    html += '</tbody></table>';

    // Load more button
    if (drilldownState.hasMore) {
        html += `
            <div class="load-more-container">
                <button class="btn-load-more" onclick="loadMoreDrilldown()">Load More</button>
            </div>
        `;
    }

    modalBody.innerHTML = html;
}

/**
 * Fetch revenue drilldown data
 */
async function fetchRevenueDrilldown() {
    const params = getDateRangeParams();
    params.append('limit', drilldownState.limit);
    params.append('offset', drilldownState.offset);

    const response = await fetch(`/admin/analytics/drilldown/revenue?${params}`);
    const result = await response.json();

    if (!result.success) throw new Error(result.error);

    drilldownState.hasMore = result.data.has_more;
    return result.data;
}

/**
 * Render revenue drilldown
 */
function renderRevenueDrilldown(data) {
    const modalBody = document.getElementById('drilldownModalBody');

    let html = '';

    // Summary stats
    if (data.summary) {
        html += `
            <div class="drilldown-summary">
                <div class="drilldown-summary-item">
                    <div class="drilldown-summary-label">Total Revenue</div>
                    <div class="drilldown-summary-value">${formatCurrency(data.summary.total_revenue)}</div>
                </div>
                <div class="drilldown-summary-item">
                    <div class="drilldown-summary-label">Avg Fee</div>
                    <div class="drilldown-summary-value">${formatCurrency(data.summary.avg_fee)}</div>
                </div>
                <div class="drilldown-summary-item">
                    <div class="drilldown-summary-label">Largest Fee</div>
                    <div class="drilldown-summary-value">${formatCurrency(data.summary.largest_fee)}</div>
                </div>
                <div class="drilldown-summary-item">
                    <div class="drilldown-summary-label">Orders</div>
                    <div class="drilldown-summary-value">${formatNumber(data.summary.total_count)}</div>
                </div>
            </div>
        `;
    }

    // Revenue table
    html += `
        <table class="analytics-table">
            <thead>
                <tr>
                    <th>Order ID</th>
                    <th>Date</th>
                    <th>Buyer</th>
                    <th>Total Price</th>
                    <th>Fee (5%)</th>
                    <th>Product Type</th>
                </tr>
            </thead>
            <tbody>
    `;

    if (data.orders && data.orders.length > 0) {
        data.orders.forEach(order => {
            html += `
                <tr>
                    <td>#${order.order_id}</td>
                    <td>${formatDate(order.order_date)}</td>
                    <td>${order.buyer_username}</td>
                    <td>${formatCurrency(order.total_price)}</td>
                    <td>${formatCurrency(order.fee)}</td>
                    <td>${order.product_type || 'Mixed'}</td>
                </tr>
            `;
        });
    } else {
        html += '<tr class="no-data"><td colspan="6">No orders found</td></tr>';
    }

    html += '</tbody></table>';

    // Load more button
    if (drilldownState.hasMore) {
        html += `
            <div class="load-more-container">
                <button class="btn-load-more" onclick="loadMoreDrilldown()">Load More</button>
            </div>
        `;
    }

    modalBody.innerHTML = html;
}

/**
 * Fetch trades drilldown data
 */
async function fetchTradesDrilldown() {
    const params = getDateRangeParams();
    params.append('limit', drilldownState.limit);
    params.append('offset', drilldownState.offset);

    const response = await fetch(`/admin/analytics/drilldown/trades?${params}`);
    const result = await response.json();

    if (!result.success) throw new Error(result.error);

    drilldownState.hasMore = result.data.has_more;
    return result.data;
}

/**
 * Render trades drilldown
 */
function renderTradesDrilldown(data) {
    const modalBody = document.getElementById('drilldownModalBody');

    let html = `
        <p style="margin-bottom: 24px; color: #666;">Total trades: <strong>${formatNumber(data.total_count)}</strong></p>
        <table class="analytics-table">
            <thead>
                <tr>
                    <th>Order ID</th>
                    <th>Date</th>
                    <th>Buyer</th>
                    <th>Total Price</th>
                    <th>Items</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
    `;

    if (data.trades && data.trades.length > 0) {
        data.trades.forEach(trade => {
            html += `
                <tr>
                    <td>#${trade.order_id}</td>
                    <td>${formatDate(trade.order_date)}</td>
                    <td>${trade.buyer_username}</td>
                    <td>${formatCurrency(trade.total_price)}</td>
                    <td>${formatNumber(trade.item_count)}</td>
                    <td><span class="status-badge ${trade.status.toLowerCase()}">${trade.status}</span></td>
                </tr>
            `;
        });
    } else {
        html += '<tr class="no-data"><td colspan="6">No trades found</td></tr>';
    }

    html += '</tbody></table>';

    // Load more button
    if (drilldownState.hasMore) {
        html += `
            <div class="load-more-container">
                <button class="btn-load-more" onclick="loadMoreDrilldown()">Load More</button>
            </div>
        `;
    }

    modalBody.innerHTML = html;
}

/**
 * Fetch listings drilldown data
 */
async function fetchListingsDrilldown() {
    const params = new URLSearchParams();
    params.append('limit', drilldownState.limit);
    params.append('offset', drilldownState.offset);

    const response = await fetch(`/admin/analytics/drilldown/listings?${params}`);
    const result = await response.json();

    if (!result.success) throw new Error(result.error);

    drilldownState.hasMore = result.data.has_more;
    return result.data;
}

/**
 * Render listings drilldown
 */
function renderListingsDrilldown(data) {
    const modalBody = document.getElementById('drilldownModalBody');

    let html = '';

    // Summary stats
    if (data.summary) {
        html += `
            <div class="drilldown-summary">
                <div class="drilldown-summary-item">
                    <div class="drilldown-summary-label">Total Listings</div>
                    <div class="drilldown-summary-value">${formatNumber(data.summary.total_listings)}</div>
                </div>
                <div class="drilldown-summary-item">
                    <div class="drilldown-summary-label">Total Units</div>
                    <div class="drilldown-summary-value">${formatNumber(data.summary.total_units)}</div>
                </div>
                <div class="drilldown-summary-item">
                    <div class="drilldown-summary-label">Categories</div>
                    <div class="drilldown-summary-value">${formatNumber(data.summary.category_count)}</div>
                </div>
            </div>
        `;
    }

    // Listings table
    html += `
        <table class="analytics-table">
            <thead>
                <tr>
                    <th>Listing ID</th>
                    <th>Created</th>
                    <th>Seller</th>
                    <th>Product</th>
                    <th>Price</th>
                    <th>Quantity</th>
                    <th>Days Listed</th>
                </tr>
            </thead>
            <tbody>
    `;

    if (data.listings && data.listings.length > 0) {
        data.listings.forEach(listing => {
            html += `
                <tr>
                    <td>#${listing.listing_id}</td>
                    <td>${formatDate(listing.created_at)}</td>
                    <td>${listing.seller_username}</td>
                    <td>${listing.metal} ${listing.product_type}</td>
                    <td>${formatCurrency(listing.price_per_coin)}</td>
                    <td>${formatNumber(listing.quantity)}</td>
                    <td>${listing.days_listed} days</td>
                </tr>
            `;
        });
    } else {
        html += '<tr class="no-data"><td colspan="7">No listings found</td></tr>';
    }

    html += '</tbody></table>';

    // Load more button
    if (drilldownState.hasMore) {
        html += `
            <div class="load-more-container">
                <button class="btn-load-more" onclick="loadMoreDrilldown()">Load More</button>
            </div>
        `;
    }

    modalBody.innerHTML = html;
}

/**
 * Fetch users drilldown data
 */
async function fetchUsersDrilldown() {
    const params = new URLSearchParams();
    params.append('limit', drilldownState.limit);
    params.append('offset', drilldownState.offset);

    if (drilldownState.search) {
        params.append('search', drilldownState.search);
    }

    if (drilldownState.filter) {
        params.append('filter', drilldownState.filter);
    }

    const response = await fetch(`/admin/analytics/drilldown/users?${params}`);
    const result = await response.json();

    if (!result.success) throw new Error(result.error);

    drilldownState.hasMore = result.data.has_more;
    return result.data;
}

/**
 * Render users drilldown
 */
function renderUsersDrilldown(data) {
    const modalBody = document.getElementById('drilldownModalBody');

    let html = `
        <div class="modal-filters">
            <input type="text" placeholder="Search users..." id="userSearchInput" value="${drilldownState.search}">
            <select id="userFilterSelect">
                <option value="">All Users</option>
                <option value="sellers" ${drilldownState.filter === 'sellers' ? 'selected' : ''}>Sellers Only</option>
                <option value="buyers" ${drilldownState.filter === 'buyers' ? 'selected' : ''}>Buyers Only</option>
                <option value="both" ${drilldownState.filter === 'both' ? 'selected' : ''}>Both Sellers & Buyers</option>
            </select>
        </div>
    `;

    html += `
        <p style="margin-bottom: 24px; color: #666;">Total users: <strong>${formatNumber(data.total_count)}</strong></p>
        <table class="analytics-table">
            <thead>
                <tr>
                    <th>User</th>
                    <th>Email</th>
                    <th>Purchase Volume</th>
                    <th>Sell Volume</th>
                    <th>Listings</th>
                    <th>Avg Rating</th>
                </tr>
            </thead>
            <tbody>
    `;

    if (data.users && data.users.length > 0) {
        data.users.forEach(user => {
            html += `
                <tr class="user-row" data-user-id="${user.id}" style="cursor: pointer;">
                    <td>
                        ${user.username}
                        ${user.is_admin ? '<span style="color: #9b59b6; font-weight: bold; margin-left: 4px;">👑</span>' : ''}
                    </td>
                    <td>${user.email}</td>
                    <td>${formatCurrency(user.total_purchase_volume || 0)}</td>
                    <td>${formatCurrency(user.total_sell_volume || 0)}</td>
                    <td>${formatNumber(user.listing_count || 0)}</td>
                    <td>${user.avg_rating ? user.avg_rating.toFixed(1) + ' ⭐' : 'N/A'}</td>
                </tr>
            `;
        });
    } else {
        html += '<tr class="no-data"><td colspan="6">No users found</td></tr>';
    }

    html += '</tbody></table>';

    // Load more button
    if (drilldownState.hasMore) {
        html += `
            <div class="load-more-container">
                <button class="btn-load-more" onclick="loadMoreDrilldown()">Load More</button>
            </div>
        `;
    }

    modalBody.innerHTML = html;

    // Attach event listeners
    document.getElementById('userSearchInput').addEventListener('keyup', debounce(function(e) {
        drilldownState.search = e.target.value;
        drilldownState.offset = 0;
        loadDrilldownData('users');
    }, 500));

    document.getElementById('userFilterSelect').addEventListener('change', function(e) {
        drilldownState.filter = e.target.value || null;
        drilldownState.offset = 0;
        loadDrilldownData('users');
    });

    // User row click handlers
    document.querySelectorAll('.user-row').forEach(row => {
        row.addEventListener('click', function() {
            const userId = this.getAttribute('data-user-id');
            openUserDetail(userId);
        });
    });
}

/**
 * Load more drilldown data (pagination)
 */
function loadMoreDrilldown() {
    drilldownState.offset += drilldownState.limit;
    loadDrilldownData(drilldownState.currentType);
}

/**
 * Open user detail modal
 */
