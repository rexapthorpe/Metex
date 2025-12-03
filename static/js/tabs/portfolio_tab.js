// static/js/tabs/portfolio_tab.js
'use strict';

/* ==========================================================================
   Portfolio Tab JavaScript
   Handles portfolio value charts, holdings list, and asset allocation
   ========================================================================== */

let portfolioValueChart = null;
let portfolioAllocationChart = null;
let currentTimeRange = '1m';
let portfolioData = null;

/**
 * Initialize portfolio tab
 */
function initPortfolioTab() {
    console.log('[Portfolio] Initializing portfolio tab');

    // Load portfolio data
    loadPortfolioData();

    // Setup time range selector
    setupTimeRangeSelector();

    // Setup periodic refresh (every 5 minutes)
    setInterval(loadPortfolioData, 300000);
}

/**
 * Load portfolio data from API
 */
function loadPortfolioData() {
    fetch('/portfolio/data')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                portfolioData = data;
                updatePortfolioSummary(data.portfolio_value);
                renderHoldingsList(data.holdings);
                renderAllocationChart(data.allocation);
                loadPortfolioHistory(currentTimeRange);
            } else {
                console.error('[Portfolio] Error loading data:', data.error);
                showEmptyState();
            }
        })
        .catch(error => {
            console.error('[Portfolio] Fetch error:', error);
            showEmptyState();
        });
}

/**
 * Update portfolio summary section
 */
function updatePortfolioSummary(valueData) {
    const totalValueEl = document.getElementById('portfolio-total-value');
    const costBasisEl = document.getElementById('portfolio-cost-basis');
    const holdingsCountEl = document.getElementById('portfolio-holdings-count');
    const valueChangeEl = document.getElementById('portfolio-value-change');

    if (totalValueEl) {
        totalValueEl.textContent = `$${valueData.total_value.toFixed(2)}`;
    }

    if (costBasisEl) {
        costBasisEl.textContent = `$${valueData.cost_basis.toFixed(2)}`;
    }

    if (holdingsCountEl) {
        holdingsCountEl.textContent = valueData.holdings_count;
    }

    // Update gain/loss display
    if (valueChangeEl) {
        const gainLoss = valueData.gain_loss;
        const gainLossPercent = valueData.gain_loss_percent;

        const changeAmountEl = valueChangeEl.querySelector('.change-amount');
        const changePercentEl = valueChangeEl.querySelector('.change-percent');

        if (changeAmountEl && changePercentEl) {
            const sign = gainLoss >= 0 ? '+' : '';
            changeAmountEl.textContent = `${sign}$${Math.abs(gainLoss).toFixed(2)}`;
            changePercentEl.textContent = `(${sign}${gainLossPercent.toFixed(2)}%)`;

            // Update color class
            valueChangeEl.classList.remove('positive', 'negative', 'neutral');
            if (gainLoss > 0) {
                valueChangeEl.classList.add('positive');
            } else if (gainLoss < 0) {
                valueChangeEl.classList.add('negative');
            } else {
                valueChangeEl.classList.add('neutral');
            }
        }
    }
}

/**
 * Load and render portfolio history chart
 */
function loadPortfolioHistory(range) {
    console.log('[Portfolio] Loading history for range:', range);

    fetch(`/portfolio/history?range=${range}`)
        .then(response => {
            console.log('[Portfolio] History response status:', response.status);
            return response.json();
        })
        .then(data => {
            console.log('[Portfolio] History data received:', data);

            if (data.success) {
                console.log('[Portfolio] History entries:', data.history.length);
                renderValueChart(data.history);
            } else {
                console.error('[Portfolio] History fetch failed:', data.error);
            }
        })
        .catch(error => {
            console.error('[Portfolio] Error loading history:', error);
        });
}

/**
 * Render portfolio value line chart
 */
function renderValueChart(historyData) {
    console.log('[Portfolio] renderValueChart called with', historyData.length, 'data points');

    const ctx = document.getElementById('portfolio-value-chart');
    if (!ctx) {
        console.error('[Portfolio] Canvas element not found!');
        return;
    }

    console.log('[Portfolio] Canvas found, preparing data...');

    // If only 1 data point, pad with earlier point to show a line
    let chartData = [...historyData];
    if (chartData.length === 1) {
        console.log('[Portfolio] Only 1 data point - adding padding for visibility');
        const singlePoint = chartData[0];
        const date = new Date(singlePoint.date);

        // Add a point 7 days earlier with same values (flat line showing current value)
        const earlierDate = new Date(date);
        earlierDate.setDate(earlierDate.getDate() - 7);

        chartData.unshift({
            date: earlierDate.toISOString(),
            value: singlePoint.value,
            cost_basis: singlePoint.cost_basis
        });

        console.log('[Portfolio] Padded data to 2 points for better visualization');
    }

    // Prepare data
    const labels = chartData.map(item => {
        const date = new Date(item.date);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });

    const values = chartData.map(item => item.value);
    const costBasis = chartData.map(item => item.cost_basis);

    console.log('[Portfolio] Chart labels:', labels);
    console.log('[Portfolio] Chart values:', values);
    console.log('[Portfolio] Chart cost basis:', costBasis);

    // Destroy existing chart if it exists
    if (portfolioValueChart) {
        console.log('[Portfolio] Destroying existing chart');
        portfolioValueChart.destroy();
    }

    // Create gradient
    try {
        const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 400);
        gradient.addColorStop(0, 'rgba(0, 102, 204, 0.15)');
        gradient.addColorStop(1, 'rgba(0, 102, 204, 0)');

        console.log('[Portfolio] Creating Chart.js chart...');

        // Create chart
        portfolioValueChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Portfolio Value',
                    data: values,
                    borderColor: '#0066cc',
                    backgroundColor: gradient,
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 4,
                    pointBackgroundColor: '#0066cc',
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 2,
                    pointHoverRadius: 7,
                    pointHoverBackgroundColor: '#0066cc',
                    pointHoverBorderColor: '#ffffff',
                    pointHoverBorderWidth: 3
                },
                {
                    label: 'Cost Basis',
                    data: costBasis,
                    borderColor: '#9ca3af',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    fill: false,
                    tension: 0.4,
                    pointRadius: 3,
                    pointBackgroundColor: '#9ca3af',
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    align: 'end',
                    labels: {
                        boxWidth: 12,
                        boxHeight: 12,
                        padding: 15,
                        font: {
                            size: 13,
                            weight: '600'
                        }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.9)',
                    titleFont: {
                        size: 13,
                        weight: '600'
                    },
                    bodyFont: {
                        size: 14,
                        weight: '600'
                    },
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': $' + context.parsed.y.toFixed(2);
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    grid: {
                        color: '#f3f4f6',
                        drawBorder: false
                    },
                    ticks: {
                        font: {
                            size: 12
                        },
                        color: '#6b7280',
                        callback: function(value) {
                            return '$' + value.toFixed(0);
                        }
                    }
                },
                x: {
                    grid: {
                        display: false,
                        drawBorder: false
                    },
                    ticks: {
                        font: {
                            size: 12
                        },
                        color: '#6b7280',
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 8
                    }
                }
            }
        }
    });

        console.log('[Portfolio] ✓ Chart created successfully!');
    } catch (error) {
        console.error('[Portfolio] ERROR creating chart:', error);
        console.error('[Portfolio] Error stack:', error.stack);
    }
}

/**
 * Render holdings list
 */
function renderHoldingsList(holdings) {
    const holdingsList = document.getElementById('holdings-list');
    if (!holdingsList) return;

    // Clear loading message
    holdingsList.innerHTML = '';

    if (holdings.length === 0) {
        holdingsList.innerHTML = '<div class="empty-message">No holdings found. Your purchased items will appear here.</div>';
        return;
    }

    // Get template
    const template = document.getElementById('holding-tile-template');
    if (!template) return;

    holdings.forEach(holding => {
        const tile = template.content.cloneNode(true);
        const tileDiv = tile.querySelector('.holding-tile');

        // Set data attribute
        tileDiv.setAttribute('data-order-item-id', holding.order_item_id);
        tileDiv.setAttribute('data-bucket-id', holding.bucket_id);

        // Set image
        const img = tile.querySelector('.holding-image img');
        img.src = holding.image_url || '/static/img/placeholder.png';
        img.alt = `${holding.metal} ${holding.product_type}`;

        // Set specs
        tile.querySelector('.metal-value').textContent = holding.metal || 'N/A';
        tile.querySelector('.product-type-value').textContent = holding.product_type || 'N/A';
        tile.querySelector('.weight-value').textContent = holding.weight || 'N/A';
        tile.querySelector('.year-value').textContent = holding.year || 'N/A';
        tile.querySelector('.grade-value').textContent = holding.grade || 'N/A';

        // Set values
        tile.querySelector('.quantity-value').textContent = holding.quantity;
        tile.querySelector('.purchase-price-value').textContent = `$${holding.purchase_price.toFixed(2)}`;

        const currentPrice = holding.current_market_price || holding.purchase_price;
        tile.querySelector('.current-price-value').textContent = `$${currentPrice.toFixed(2)}`;
        tile.querySelector('.current-value-amount').textContent = `$${holding.current_value.toFixed(2)}`;

        // Set gain/loss
        const gainLossEl = tile.querySelector('.gain-loss-value');
        const gainLoss = holding.gain_loss;
        const gainLossPercent = holding.gain_loss_percent;

        const sign = gainLoss >= 0 ? '+' : '';
        gainLossEl.textContent = `${sign}$${Math.abs(gainLoss).toFixed(2)} (${sign}${gainLossPercent.toFixed(2)}%)`;

        if (gainLoss > 0) {
            gainLossEl.classList.add('positive');
        } else if (gainLoss < 0) {
            gainLossEl.classList.add('negative');
        }

        holdingsList.appendChild(tile);
    });
}

/**
 * Render asset allocation pie chart
 */
function renderAllocationChart(allocationData) {
    const ctx = document.getElementById('portfolio-allocation-chart');
    const legendContainer = document.getElementById('allocation-legend');

    if (!ctx || !legendContainer) return;

    if (allocationData.length === 0) {
        legendContainer.innerHTML = '<div class="empty-message">No allocation data available</div>';
        return;
    }

    // Color palette for metals
    const metalColors = {
        'Gold': '#F59E0B',
        'Silver': '#9CA3AF',
        'Platinum': '#6B7280',
        'Palladium': '#374151',
        'Copper': '#EF4444'
    };

    const labels = allocationData.map(item => item.metal);
    const values = allocationData.map(item => item.value);
    const percentages = allocationData.map(item => item.percentage);
    const colors = allocationData.map(item => metalColors[item.metal] || '#60a5fa');

    // Destroy existing chart
    if (portfolioAllocationChart) {
        portfolioAllocationChart.destroy();
    }

    // Create chart
    portfolioAllocationChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 3,
                borderColor: '#ffffff',
                hoverBorderWidth: 4,
                hoverOffset: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.9)',
                    titleFont: {
                        size: 14,
                        weight: '600'
                    },
                    bodyFont: {
                        size: 15,
                        weight: '600'
                    },
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const percentage = percentages[context.dataIndex];
                            return label + ': $' + value.toFixed(2) + ' (' + percentage.toFixed(1) + '%)';
                        }
                    }
                }
            },
            cutout: '65%'
        }
    });

    // Render custom legend
    legendContainer.innerHTML = '';
    allocationData.forEach((item, index) => {
        const legendItem = document.createElement('div');
        legendItem.className = 'legend-item';
        legendItem.innerHTML = `
            <div class="legend-label">
                <div class="legend-color" style="background: ${colors[index]}"></div>
                <span>${item.metal}</span>
            </div>
            <div class="legend-values">
                <div class="legend-value">$${item.value.toFixed(2)}</div>
                <div class="legend-percent">${item.percentage.toFixed(1)}%</div>
            </div>
        `;
        legendContainer.appendChild(legendItem);
    });
}

/**
 * Setup time range selector
 */
function setupTimeRangeSelector() {
    const timeBtns = document.querySelectorAll('.time-btn');

    timeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const range = btn.getAttribute('data-range');

            // Update active state
            timeBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Load new data
            currentTimeRange = range;
            loadPortfolioHistory(range);
        });
    });
}

/**
 * Exclude a holding from portfolio
 */
function excludeHolding(button) {
    const tile = button.closest('.holding-tile');
    const orderItemId = tile.getAttribute('data-order-item-id');

    if (!confirm('Remove this item from your portfolio calculations?')) {
        return;
    }

    fetch(`/portfolio/exclude/${orderItemId}`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Remove tile with animation
                tile.style.opacity = '0';
                setTimeout(() => {
                    tile.remove();
                    // Reload portfolio data
                    loadPortfolioData();
                }, 300);
            } else {
                alert('Failed to exclude item: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('[Portfolio] Error excluding item:', error);
            alert('An error occurred. Please try again.');
        });
}

/**
 * Open listing modal from holding tile
 */
function openListingModalFromHolding(button) {
    const tile = button.closest('.holding-tile');
    const bucketId = tile.getAttribute('data-bucket-id');

    if (!bucketId) {
        alert('Cannot list this item: Bucket ID not found');
        return;
    }

    // Navigate to the bucket page where they can create a listing
    window.location.href = `/bucket/${bucketId}`;
}

/**
 * Show empty state
 */
function showEmptyState() {
    const holdingsList = document.getElementById('holdings-list');
    if (holdingsList) {
        holdingsList.innerHTML = '<div class="empty-message">Unable to load portfolio data. Please refresh the page.</div>';
    }
}

// Initialize when portfolio tab becomes active
document.addEventListener('DOMContentLoaded', () => {
    // Check if we're on the portfolio tab
    const portfolioTab = document.getElementById('portfolio-tab');
    if (portfolioTab && portfolioTab.style.display !== 'none') {
        initPortfolioTab();
    }
});

// Also initialize when tab is shown (for tab switching)
window.addEventListener('hashchange', () => {
    if (window.location.hash === '#portfolio') {
        initPortfolioTab();
    }
});

// Expose functions globally
window.excludeHolding = excludeHolding;
window.openListingModalFromHolding = openListingModalFromHolding;
