async function loadTopItems() {
    try {
        const params = getDateRangeParams();
        params.append('limit', 10);

        const response = await fetch(`/admin/analytics/top-items?${params}`);
        const result = await response.json();

        if (result.success) {
            populateTopItemsTable(result.data.by_volume);
        }
    } catch (error) {
        console.error('Error loading top items:', error);
    }
}

/**
 * Populate top items table
 */
function populateTopItemsTable(items) {
    const tbody = document.getElementById('topItemsTable');

    if (!items || items.length === 0) {
        tbody.innerHTML = '<tr class="no-data"><td colspan="6">No data available</td></tr>';
        return;
    }

    tbody.innerHTML = items.map(item => `
        <tr>
            <td>${item.metal || 'N/A'}</td>
            <td>${item.product_type || 'N/A'}</td>
            <td>${item.weight || 'N/A'}</td>
            <td>${formatCurrency(item.total_volume)}</td>
            <td>${formatNumber(item.trade_count)}</td>
            <td>${formatCurrency(item.avg_price)}</td>
        </tr>
    `).join('');
}

/**
 * Load top users data
 */
async function loadTopUsers() {
    try {
        const params = getDateRangeParams();
        params.append('limit', 10);

        const response = await fetch(`/admin/analytics/top-users?${params}`);
        const result = await response.json();

        if (result.success) {
            populateTopSellersTable(result.data.sellers);
            populateTopBuyersTable(result.data.buyers);
        }
    } catch (error) {
        console.error('Error loading top users:', error);
    }
}

/**
 * Populate top sellers table
 */
function populateTopSellersTable(sellers) {
    const tbody = document.getElementById('topSellersTable');

    if (!sellers || sellers.length === 0) {
        tbody.innerHTML = '<tr class="no-data"><td colspan="4">No data available</td></tr>';
        return;
    }

    tbody.innerHTML = sellers.map(seller => `
        <tr>
            <td>${seller.username}</td>
            <td>${formatCurrency(seller.total_volume)}</td>
            <td>${formatNumber(seller.order_count)}</td>
            <td>${seller.avg_rating ? seller.avg_rating.toFixed(1) + ' ⭐' : 'N/A'}</td>
        </tr>
    `).join('');
}

/**
 * Populate top buyers table
 */
function populateTopBuyersTable(buyers) {
    const tbody = document.getElementById('topBuyersTable');

    if (!buyers || buyers.length === 0) {
        tbody.innerHTML = '<tr class="no-data"><td colspan="4">No data available</td></tr>';
        return;
    }

    tbody.innerHTML = buyers.map(buyer => `
        <tr>
            <td>${buyer.username}</td>
            <td>${formatCurrency(buyer.total_volume)}</td>
            <td>${formatNumber(buyer.order_count)}</td>
            <td>${buyer.avg_rating ? buyer.avg_rating.toFixed(1) + ' ⭐' : 'N/A'}</td>
        </tr>
    `).join('');
}

/**
 * Load market health metrics
 */
async function loadMarketHealth() {
    try {
        const params = getDateRangeParams();

        const response = await fetch(`/admin/analytics/market-health?${params}`);
        const result = await response.json();

        if (result.success) {
            updateMarketHealth(result.data);
        }
    } catch (error) {
        console.error('Error loading market health:', error);
    }
}

/**
 * Update market health display
 */
function updateMarketHealth(data) {
    document.getElementById('medianTimeToSell').textContent =
        Math.round(data.median_time_to_sell) + ' days';

    document.getElementById('sellThroughRate').textContent =
        data.sell_through_rate.toFixed(1) + '%';
}

/**
 * Load user analytics
 */
async function loadUserAnalytics() {
    try {
        const params = getDateRangeParams();

        const response = await fetch(`/admin/analytics/user-analytics?${params}`);
        const result = await response.json();

        if (result.success) {
            updateUserAnalytics(result.data);
        }
    } catch (error) {
        console.error('Error loading user analytics:', error);
    }
}

/**
 * Update user analytics display
 */
function updateUserAnalytics(data) {
    document.getElementById('activeUsers').textContent = formatNumber(data.active_users);
    document.getElementById('activityRate').textContent = data.activity_rate.toFixed(1) + '%';
}

/**
 * Load operational metrics
 */
async function loadOperationalMetrics() {
    try {
        const params = getDateRangeParams();

        const response = await fetch(`/admin/analytics/operational?${params}`);
        const result = await response.json();

        if (result.success) {
            updateOperationalMetrics(result.data);
        }
    } catch (error) {
        console.error('Error loading operational metrics:', error);
    }
}

/**
 * Update operational metrics display
 */
function updateOperationalMetrics(data) {
    document.getElementById('avgRating').textContent =
        data.avg_rating.toFixed(1) + ' ⭐';

    document.getElementById('totalRatings').textContent =
        formatNumber(data.total_ratings);

    document.getElementById('totalMessages').textContent =
        formatNumber(data.total_messages);
}

/**
 * Load largest transactions
 */
async function loadLargestTransactions() {
    try {
        const response = await fetch('/admin/analytics/largest-transactions?limit=10');
        const result = await response.json();

        if (result.success) {
            populateLargestTransactionsTable(result.data);
        }
    } catch (error) {
        console.error('Error loading largest transactions:', error);
    }
}

/**
 * Populate largest transactions table
 */
function populateLargestTransactionsTable(transactions) {
    const tbody = document.getElementById('largestTransactionsTable');

    if (!transactions || transactions.length === 0) {
        tbody.innerHTML = '<tr class="no-data"><td colspan="6">No data available</td></tr>';
        return;
    }

    tbody.innerHTML = transactions.map(tx => `
        <tr>
            <td>#${tx.id}</td>
            <td>${tx.buyer_username}</td>
            <td>${formatCurrency(tx.total_price)}</td>
            <td>${formatNumber(tx.item_count)} items</td>
            <td>${formatDate(tx.created_at)}</td>
            <td><span class="status-badge ${tx.status.toLowerCase()}">${tx.status}</span></td>
        </tr>
    `).join('');
}

/**
 * Format currency
 */
function formatCurrency(value) {
    if (value === null || value === undefined) return '$0';
    return '$' + parseFloat(value).toLocaleString('en-US', {
