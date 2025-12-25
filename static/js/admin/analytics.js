/**
 * Analytics Dashboard Interactive JavaScript
 * Handles data fetching, chart rendering, and dynamic UI updates
 */

// Global state
let currentFilters = {
    dateRange: '7d',
    startDate: null,
    endDate: null,
    groupBy: 'day',
    metric: 'volume',
    compare: false
};

let timeseriesChart = null;
let chartData = null;

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeFilters();
    initializeExpandableSections();
    loadAllData();
});

/**
 * Initialize filter controls and event listeners
 */
function initializeFilters() {
    // Date range selector
    const dateRangeSelect = document.getElementById('dateRange');
    dateRangeSelect.addEventListener('change', function() {
        const customDatesGroup = document.getElementById('customDatesGroup');
        if (this.value === 'custom') {
            customDatesGroup.style.display = 'flex';
        } else {
            customDatesGroup.style.display = 'none';
        }
        currentFilters.dateRange = this.value;
    });

    // Group by selector
    document.getElementById('groupBy').addEventListener('change', function() {
        currentFilters.groupBy = this.value;
    });

    // Metric selector
    document.getElementById('metric').addEventListener('change', function() {
        currentFilters.metric = this.value;
    });

    // Compare toggle
    document.getElementById('compareToggle').addEventListener('change', function() {
        currentFilters.compare = this.checked;
    });

    // Breakdown by category toggle
    document.getElementById('breakdownByCategory').addEventListener('change', function() {
        loadTimeseriesData();
    });

    // Apply filters button
    document.getElementById('applyFilters').addEventListener('click', function() {
        if (currentFilters.dateRange === 'custom') {
            currentFilters.startDate = document.getElementById('startDate').value;
            currentFilters.endDate = document.getElementById('endDate').value;
        }
        loadAllData();
    });

    // Reset filters button
    document.getElementById('resetFilters').addEventListener('click', function() {
        document.getElementById('dateRange').value = '7d';
        document.getElementById('groupBy').value = 'day';
        document.getElementById('metric').value = 'volume';
        document.getElementById('compareToggle').checked = false;
        document.getElementById('breakdownByCategory').checked = false;
        document.getElementById('customDatesGroup').style.display = 'none';

        currentFilters = {
            dateRange: '7d',
            startDate: null,
            endDate: null,
            groupBy: 'day',
            metric: 'volume',
            compare: false
        };

        loadAllData();
    });
}

/**
 * Initialize expandable sections
 */
function initializeExpandableSections() {
    const expandableHeaders = document.querySelectorAll('.expandable-header');

    expandableHeaders.forEach(header => {
        header.addEventListener('click', function() {
            const targetId = this.getAttribute('data-target');
            const content = document.getElementById(targetId);

            this.classList.toggle('active');
            content.classList.toggle('active');

            // Load data when expanded
            if (content.classList.contains('active')) {
                if (targetId === 'largestTransactionsContent') {
                    loadLargestTransactions();
                }
            }
        });
    });
}

/**
 * Load all dashboard data
 */
function loadAllData() {
    showLoading(true);

    Promise.all([
        loadKPIs(),
        loadTimeseriesData(),
        loadTopItems(),
        loadTopUsers(),
        loadMarketHealth(),
        loadUserAnalytics(),
        loadOperationalMetrics()
    ]).then(() => {
        showLoading(false);
    }).catch(error => {
        console.error('Error loading dashboard data:', error);
        showLoading(false);
    });
}

/**
 * Show/hide loading state
 */
function showLoading(show) {
    const loadingState = document.getElementById('loadingState');
    const kpiGrid = document.getElementById('kpiGrid');

    if (show) {
        loadingState.style.display = 'flex';
        kpiGrid.style.opacity = '0.5';
    } else {
        loadingState.style.display = 'none';
        kpiGrid.style.opacity = '1';
    }
}

/**
 * Get date range parameters based on current filter
 */
function getDateRangeParams() {
    const params = new URLSearchParams();

    if (currentFilters.dateRange === 'custom' && currentFilters.startDate && currentFilters.endDate) {
        params.append('start', new Date(currentFilters.startDate).toISOString());
        params.append('end', new Date(currentFilters.endDate).toISOString());
    } else if (currentFilters.dateRange !== 'all') {
        const end = new Date();
        let start = new Date();

        switch (currentFilters.dateRange) {
            case '24h':
                start.setDate(start.getDate() - 1);
                break;
            case '7d':
                start.setDate(start.getDate() - 7);
                break;
            case '30d':
                start.setDate(start.getDate() - 30);
                break;
            case '90d':
                start.setDate(start.getDate() - 90);
                break;
            case 'ytd':
                start = new Date(start.getFullYear(), 0, 1);
                break;
        }

        params.append('start', start.toISOString());
        params.append('end', end.toISOString());
    }

    return params;
}

/**
 * Load KPI data
 */
async function loadKPIs() {
    try {
        const params = getDateRangeParams();
        params.append('compare', currentFilters.compare);

        const response = await fetch(`/admin/analytics/kpis?${params}`);
        const result = await response.json();

        if (result.success) {
            updateKPIs(result.data);
        }
    } catch (error) {
        console.error('Error loading KPIs:', error);
    }
}

/**
 * Update KPI display
 */
function updateKPIs(data) {
    // Volume traded
    document.getElementById('kpiVolume').textContent = formatCurrency(data.volume_traded);

    // Revenue
    document.getElementById('kpiRevenue').textContent = formatCurrency(data.website_revenue);

    // Trades
    document.getElementById('kpiTrades').textContent = formatNumber(data.num_trades);

    // Active listings
    document.getElementById('kpiListings').textContent = formatNumber(data.active_listings);

    // Users
    document.getElementById('kpiUsers').textContent = formatNumber(data.total_users);

    // Conversion funnel
    const funnelNumbers = document.querySelectorAll('.funnel-number');
    funnelNumbers[0].textContent = formatNumber(data.conversion_funnel.users_with_listings);
    funnelNumbers[1].textContent = formatNumber(data.conversion_funnel.users_with_purchases);

    // Update change indicators if comparison data available
    if (data.previous_period) {
        updateChangeIndicator('kpiVolumeChange', data.volume_traded, data.previous_period.volume_traded);
        updateChangeIndicator('kpiRevenueChange', data.website_revenue, data.previous_period.website_revenue);
        updateChangeIndicator('kpiTradesChange', data.num_trades, data.previous_period.num_trades);
    }

    // Animate KPI cards
    animateKPICards();
}

/**
 * Update change indicator
 */
function updateChangeIndicator(elementId, current, previous) {
    const element = document.getElementById(elementId);

    if (previous === 0) {
        element.textContent = '';
        return;
    }

    const change = ((current - previous) / previous) * 100;
    const changeText = Math.abs(change).toFixed(1) + '%';

    element.textContent = changeText;
    element.className = 'kpi-change';

    if (change > 0) {
        element.classList.add('positive');
    } else if (change < 0) {
        element.classList.add('negative');
    }
}

/**
 * Animate KPI cards on load
 */
function animateKPICards() {
    const cards = document.querySelectorAll('.kpi-card');
    cards.forEach((card, index) => {
        card.style.animation = `fadeIn 0.5s ease-in ${index * 0.1}s both`;
    });
}

/**
 * Load timeseries data and render chart
 */
async function loadTimeseriesData() {
    try {
        const params = getDateRangeParams();
        params.append('group_by', currentFilters.groupBy);
        params.append('metric', currentFilters.metric);

        const breakdown = document.getElementById('breakdownByCategory').checked;
        params.append('breakdown', breakdown);

        const response = await fetch(`/admin/analytics/timeseries?${params}`);
        const result = await response.json();

        if (result.success) {
            renderTimeseriesChart(result.data, breakdown);
        }
    } catch (error) {
        console.error('Error loading timeseries data:', error);
    }
}

/**
 * Render timeseries chart using Chart.js
 */
function renderTimeseriesChart(data, breakdown) {
    const ctx = document.getElementById('timeseriesChart').getContext('2d');

    // Destroy existing chart
    if (timeseriesChart) {
        timeseriesChart.destroy();
    }

    let chartConfig;

    if (breakdown && typeof data === 'object' && !Array.isArray(data)) {
        // Stacked breakdown by category
        const categories = Object.keys(data);
        const allPeriods = new Set();

        categories.forEach(cat => {
            data[cat].forEach(point => allPeriods.add(point.period));
        });

        const periods = Array.from(allPeriods).sort();

        const datasets = categories.map((category, index) => {
            const colors = ['#3da6ff', '#ff6b6b', '#4ecdc4', '#ffd93d', '#95e1d3', '#f38181'];
            const color = colors[index % colors.length];

            return {
                label: category,
                data: periods.map(period => {
                    const point = data[category].find(p => p.period === period);
                    return point ? point.value : 0;
                }),
                backgroundColor: color + '80',
                borderColor: color,
                borderWidth: 2,
                fill: true
            };
        });

        chartConfig = {
            type: 'line',
            data: {
                labels: periods,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                if (currentFilters.metric === 'trades') {
                                    label += formatNumber(context.parsed.y);
                                } else {
                                    label += formatCurrency(context.parsed.y);
                                }
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        stacked: false,
                        grid: {
                            display: false
                        }
                    },
                    y: {
                        stacked: false,
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                if (currentFilters.metric === 'trades') {
                                    return formatNumber(value);
                                }
                                return formatCurrency(value);
                            }
                        }
                    }
                },
                interaction: {
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                }
            }
        };
    } else {
        // Simple line chart
        chartConfig = {
            type: 'line',
            data: {
                labels: data.map(point => point.period),
                datasets: [{
                    label: currentFilters.metric.charAt(0).toUpperCase() + currentFilters.metric.slice(1),
                    data: data.map(point => point.value),
                    backgroundColor: 'rgba(61, 166, 255, 0.1)',
                    borderColor: '#3da6ff',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 4,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                if (currentFilters.metric === 'trades') {
                                    return formatNumber(context.parsed.y);
                                }
                                return formatCurrency(context.parsed.y);
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            display: false
                        }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                if (currentFilters.metric === 'trades') {
                                    return formatNumber(value);
                                }
                                return formatCurrency(value);
                            }
                        }
                    }
                }
            }
        };
    }

    timeseriesChart = new Chart(ctx, chartConfig);
}

/**
 * Load top items data
 */
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
 * Format date
 */
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

/**
 * Format datetime
 */
function formatDateTime(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
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
async function openUserDetail(userId) {
    const modal = document.getElementById('userDetailModal');
    const overlay = document.getElementById('userDetailModalOverlay');
    const title = document.getElementById('userDetailModalTitle');
    const body = document.getElementById('userDetailModalBody');

    title.textContent = 'User Details';
    body.innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><p>Loading user details...</p></div>';

    overlay.classList.add('active');
    modal.classList.add('active');

    try {
        const response = await fetch(`/admin/analytics/user/${userId}`);
        const result = await response.json();

        if (!result.success) throw new Error(result.error);

        renderUserDetail(result.data);
    } catch (error) {
        console.error('Error loading user detail:', error);
        body.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-circle"></i><p>Error loading user details</p></div>';
    }
}

/**
 * Close user detail modal
 */
function closeUserDetail() {
    const modal = document.getElementById('userDetailModal');
    const overlay = document.getElementById('userDetailModalOverlay');

    modal.classList.remove('active');
    overlay.classList.remove('active');

    setTimeout(() => {
        document.getElementById('userDetailModalBody').innerHTML = '';
    }, 300);
}

/**
 * Render user detail
 */
function renderUserDetail(data) {
    const body = document.getElementById('userDetailModalBody');
    const title = document.getElementById('userDetailModalTitle');

    title.textContent = `User: ${data.user.username}`;

    let html = `
        <div class="user-detail-section">
            <h3>Profile Information</h3>
            <p><strong>Email:</strong> ${data.user.email}</p>
            <p><strong>Name:</strong> ${data.user.first_name || 'N/A'} ${data.user.last_name || ''}</p>
            <p><strong>Phone:</strong> ${data.user.phone || 'N/A'}</p>
            ${data.user.is_admin ? '<p><strong>Role:</strong> <span style="color: #9b59b6;">Administrator 👑</span></p>' : ''}
        </div>

        <div class="user-detail-section">
            <h3>Activity Statistics</h3>
            <div class="user-stats-grid">
                <div class="user-stat-card">
                    <div class="user-stat-label">Purchase Volume</div>
                    <div class="user-stat-value">${formatCurrency(data.stats.total_purchase_volume)}</div>
                </div>
                <div class="user-stat-card">
                    <div class="user-stat-label">Sell Volume</div>
                    <div class="user-stat-value">${formatCurrency(data.stats.total_sell_volume)}</div>
                </div>
                <div class="user-stat-card">
                    <div class="user-stat-label">Orders</div>
                    <div class="user-stat-value">${formatNumber(data.stats.order_count)}</div>
                </div>
                <div class="user-stat-card">
                    <div class="user-stat-label">Sales</div>
                    <div class="user-stat-value">${formatNumber(data.stats.sell_count)}</div>
                </div>
                <div class="user-stat-card">
                    <div class="user-stat-label">Avg Rating</div>
                    <div class="user-stat-value">${data.stats.avg_rating ? data.stats.avg_rating.toFixed(1) + ' ⭐' : 'N/A'}</div>
                </div>
                <div class="user-stat-card">
                    <div class="user-stat-label">Messages</div>
                    <div class="user-stat-value">${formatNumber(data.stats.message_count)}</div>
                </div>
            </div>
        </div>
    `;

    // Recent listings
    if (data.listings && data.listings.length > 0) {
        html += `
            <div class="user-detail-section">
                <h3>Recent Listings (${data.listings.length})</h3>
                <table class="analytics-table">
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th>Price</th>
                            <th>Quantity</th>
                            <th>Created</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        data.listings.forEach(listing => {
            html += `
                <tr>
                    <td>${listing.metal} ${listing.product_type}</td>
                    <td>${formatCurrency(listing.price_per_coin)}</td>
                    <td>${formatNumber(listing.quantity)}</td>
                    <td>${formatDate(listing.created_at)}</td>
                </tr>
            `;
        });
        html += '</tbody></table></div>';
    }

    // Recent orders
    if (data.orders && data.orders.length > 0) {
        html += `
            <div class="user-detail-section">
                <h3>Recent Orders (${data.orders.length})</h3>
                <table class="analytics-table">
                    <thead>
                        <tr>
                            <th>Order ID</th>
                            <th>Total</th>
                            <th>Status</th>
                            <th>Date</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        data.orders.forEach(order => {
            html += `
                <tr>
                    <td>#${order.id}</td>
                    <td>${formatCurrency(order.total_price)}</td>
                    <td><span class="status-badge ${order.status.toLowerCase()}">${order.status}</span></td>
                    <td>${formatDate(order.created_at)}</td>
                </tr>
            `;
        });
        html += '</tbody></table></div>';
    }

    // Recent ratings received
    if (data.ratings_received && data.ratings_received.length > 0) {
        html += `
            <div class="user-detail-section">
                <h3>Recent Ratings Received (${data.ratings_received.length})</h3>
                <table class="analytics-table">
                    <thead>
                        <tr>
                            <th>Rating</th>
                            <th>From</th>
                            <th>Review</th>
                            <th>Date</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        data.ratings_received.forEach(rating => {
            html += `
                <tr>
                    <td>${rating.rating} ⭐</td>
                    <td>${rating.reviewer_username}</td>
                    <td>${rating.review || 'No review'}</td>
                    <td>${formatDate(rating.created_at)}</td>
                </tr>
            `;
        });
        html += '</tbody></table></div>';
    }

    body.innerHTML = html;
}

/**
 * Debounce utility for search input
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
