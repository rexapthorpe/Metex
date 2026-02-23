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
