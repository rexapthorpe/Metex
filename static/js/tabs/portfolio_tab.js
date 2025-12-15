// static/js/tabs/portfolio_tab.js
'use strict';

/* ==========================================================================
   Portfolio Tab JavaScript
   Handles portfolio value charts, holdings list, and asset allocation
   ========================================================================== */

let portfolioValueChart = null;
let portfolioAllocationChart = null;
let currentTimeRange = '1d';
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
 * Supports partial updates for hover functionality (only updates provided fields)
 */
function updatePortfolioSummary(valueData) {
    const totalValueEl = document.getElementById('portfolio-total-value');
    const costBasisEl = document.getElementById('portfolio-cost-basis');
    const holdingsCountEl = document.getElementById('portfolio-holdings-count');
    const valueChangeEl = document.getElementById('portfolio-value-change');

    // Update total value if provided
    if (totalValueEl && valueData.total_value !== undefined) {
        totalValueEl.textContent = formatPrice(valueData.total_value);
    }

    // Update cost basis if provided
    if (costBasisEl && valueData.cost_basis !== undefined) {
        costBasisEl.textContent = formatPrice(valueData.cost_basis);
    }

    // Update holdings count if provided
    if (holdingsCountEl && valueData.holdings_count !== undefined) {
        holdingsCountEl.textContent = valueData.holdings_count;
    }

    // Update gain/loss display if provided
    if (valueChangeEl && valueData.gain_loss !== undefined && valueData.gain_loss_percent !== undefined) {
        const gainLoss = valueData.gain_loss;
        const gainLossPercent = valueData.gain_loss_percent;

        const changeAmountEl = valueChangeEl.querySelector('.change-amount');
        const changePercentEl = valueChangeEl.querySelector('.change-percent');

        if (changeAmountEl && changePercentEl) {
            const sign = gainLoss >= 0 ? '+' : '';
            changeAmountEl.textContent = `${sign}${formatPrice(Math.abs(gainLoss))}`;
            changePercentEl.textContent = `(${sign}${formatWithCommas(gainLossPercent, 2)}%)`;

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

    // Prepare data with appropriate label format based on time range
    const labels = chartData.map(item => {
        const date = new Date(item.date);

        // Format labels based on current time range
        if (currentTimeRange === '1d') {
            // 1D: Show hour (e.g., "9 AM", "3 PM")
            return date.toLocaleTimeString('en-US', { hour: 'numeric', hour12: true });
        } else if (currentTimeRange === '1y') {
            // 1Y: Show month and year (e.g., "Jan 2024")
            return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
        } else {
            // 1W, 1M, 3M: Show month and day (e.g., "Nov 2")
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        }
    });

    const values = chartData.map(item => item.value);
    const costBasis = chartData.map(item => item.cost_basis);

    console.log('[Portfolio] Chart labels:', labels);
    console.log('[Portfolio] Chart values:', values);
    console.log('[Portfolio] Chart cost basis:', costBasis);

    // Check if all values are zero (empty portfolio)
    const allZero = values.every(v => v === 0) && costBasis.every(c => c === 0);
    console.log('[Portfolio] All values zero?', allZero);

    // Calculate max value across both series for y-axis scaling
    const maxValue = Math.max(...values, ...costBasis);
    console.log('[Portfolio] Max value in data:', maxValue);

    // Store last values for the original summary (current state)
    const lastValue = values[values.length - 1] || 0;
    const lastCostBasis = costBasis[costBasis.length - 1] || 0;

    // Store original summary for reset on mouseleave
    // Calculate gain/loss vs cost basis (not vs first value)
    const originalSummary = {
        total_value: lastValue,
        cost_basis: lastCostBasis,
        gain_loss: lastValue - lastCostBasis,
        gain_loss_percent: lastCostBasis > 0 ? ((lastValue - lastCostBasis) / lastCostBasis * 100) : 0
    };

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

        // Configure y-axis based on whether portfolio is empty
        const yAxisConfig = {
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
        };

        // If all values are zero, fix y-axis from 0 to 100 (no negative values)
        if (allZero) {
            yAxisConfig.min = 0;
            yAxisConfig.max = 100;
            yAxisConfig.beginAtZero = true;
            console.log('[Portfolio] Using fixed y-axis (0-100) for empty portfolio');
        } else {
            // For non-zero data, set y-axis from 0 to maxValue * 1.2 (20% headroom)
            yAxisConfig.min = 0;
            yAxisConfig.max = Math.ceil(maxValue * 1.2);
            yAxisConfig.beginAtZero = true;
            console.log('[Portfolio] Using scaled y-axis (0-' + yAxisConfig.max + ') with 20% headroom');
        }

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
            onHover: function(event, activeElements) {
                // Update summary when hovering over data points
                if (activeElements && activeElements.length > 0) {
                    const index = activeElements[0].index;
                    const hoveredValue = values[index];
                    const hoveredCostBasis = costBasis[index];

                    // Calculate gain/loss vs cost basis at this point
                    const gainLoss = hoveredValue - hoveredCostBasis;
                    const gainLossPercent = hoveredCostBasis > 0 ? (gainLoss / hoveredCostBasis * 100) : 0;

                    updatePortfolioSummary({
                        total_value: hoveredValue,
                        gain_loss: gainLoss,
                        gain_loss_percent: gainLossPercent
                    });
                } else {
                    // Reset to original summary when not hovering over a point
                    updatePortfolioSummary(originalSummary);
                }
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
                            return context.dataset.label + ': ' + formatPrice(context.parsed.y);
                        }
                    }
                }
            },
            scales: {
                y: yAxisConfig,
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
        },
        plugins: [{
            id: 'gainLossFill',
            afterDatasetsDraw: function(chart) {
                // Draw colored fills between portfolio value and cost basis lines
                const ctx = chart.ctx;
                const chartArea = chart.chartArea;
                const meta0 = chart.getDatasetMeta(0); // Portfolio Value dataset
                const meta1 = chart.getDatasetMeta(1); // Cost Basis dataset

                if (!meta0 || !meta1) return;

                const points0 = meta0.data; // Portfolio Value points
                const points1 = meta1.data; // Cost Basis points

                if (points0.length === 0 || points1.length === 0) return;

                ctx.save();

                // Draw fills between each pair of adjacent points
                for (let i = 0; i < points0.length - 1; i++) {
                    const p0Value = points0[i];
                    const p1Value = points0[i + 1];
                    const p0Cost = points1[i];
                    const p1Cost = points1[i + 1];

                    if (!p0Value || !p1Value || !p0Cost || !p1Cost) continue;

                    // Determine if this segment is gain (green) or loss (red)
                    const avgValue = (values[i] + values[i + 1]) / 2;
                    const avgCost = (costBasis[i] + costBasis[i + 1]) / 2;
                    const isGain = avgValue > avgCost;

                    // Set fill color with transparency
                    ctx.fillStyle = isGain
                        ? 'rgba(34, 197, 94, 0.15)'   // Green with 15% opacity
                        : 'rgba(239, 68, 68, 0.15)';   // Red with 15% opacity

                    // Draw filled polygon between the two lines for this segment
                    ctx.beginPath();
                    ctx.moveTo(p0Value.x, p0Value.y);
                    ctx.lineTo(p1Value.x, p1Value.y);
                    ctx.lineTo(p1Cost.x, p1Cost.y);
                    ctx.lineTo(p0Cost.x, p0Cost.y);
                    ctx.closePath();
                    ctx.fill();
                }

                ctx.restore();
            }
        }]
    });

        console.log('[Portfolio] ✓ Chart created successfully!');

        // Add mouseleave event to reset summary when cursor leaves chart
        ctx.addEventListener('mouseleave', function() {
            console.log('[Portfolio] Mouse left chart - resetting summary');
            updatePortfolioSummary(originalSummary);
        });
        console.log('[Portfolio] ✓ Mouseleave handler attached');
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

        // Set data attributes - store all order_item_ids for this consolidated holding
        const orderItemIds = holding.order_item_ids ? holding.order_item_ids.join(',') : '';
        tileDiv.setAttribute('data-order-item-ids', orderItemIds);
        tileDiv.setAttribute('data-bucket-id', holding.bucket_id);

        // Store all category data as data attributes for the Item Details modal
        tileDiv.setAttribute('data-metal', holding.metal || '');
        tileDiv.setAttribute('data-product-type', holding.product_type || '');
        tileDiv.setAttribute('data-weight', holding.weight || '');
        tileDiv.setAttribute('data-purity', holding.purity || '');
        tileDiv.setAttribute('data-mint', holding.mint || '');
        tileDiv.setAttribute('data-year', holding.year || '');
        tileDiv.setAttribute('data-finish', holding.finish || '');
        tileDiv.setAttribute('data-grade', holding.grade || '');
        tileDiv.setAttribute('data-product-line', holding.product_line || '');
        tileDiv.setAttribute('data-graded', holding.graded ? '1' : '0');
        tileDiv.setAttribute('data-grading-service', holding.grading_service || '');
        tileDiv.setAttribute('data-seller-username', holding.seller_username || '');
        tileDiv.setAttribute('data-purchase-date', holding.purchase_date || '');

        // Set image
        const img = tile.querySelector('.holding-image img');
        img.src = holding.image_url || '/static/img/placeholder.png';
        img.alt = `${holding.metal} ${holding.product_type}`;

        // Add isolated/set badge if applicable
        const holdingImageDiv = tile.querySelector('.holding-image');
        if (holding.is_isolated) {
            const badge = document.createElement('div');
            badge.style.position = 'absolute';
            badge.style.top = '8px';
            badge.style.left = '8px';
            badge.style.zIndex = '10';

            if (holding.isolated_type === 'set') {
                badge.innerHTML = '<span style="background-color: #10b981; color: white; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: bold;">SET</span>';
            } else if (holding.issue_number && holding.issue_total) {
                badge.innerHTML = `<span style="background-color: #8b5cf6; color: white; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: bold;">#${holding.issue_number}/${holding.issue_total}</span>`;
            } else {
                badge.innerHTML = '<span style="background-color: #f59e0b; color: white; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: bold;">1-OF-A-KIND</span>';
            }

            // Make sure holding-image has position: relative
            if (holdingImageDiv) {
                holdingImageDiv.style.position = 'relative';
                holdingImageDiv.appendChild(badge);
            }
        }

        // Set values
        tile.querySelector('.quantity-value').textContent = formatQuantity(holding.quantity);
        tile.querySelector('.purchase-price-value').textContent = formatPrice(holding.purchase_price);

        const currentPrice = holding.current_market_price || holding.purchase_price;
        tile.querySelector('.current-price-value').textContent = formatPrice(currentPrice);
        tile.querySelector('.current-value-amount').textContent = formatPrice(holding.current_value);

        // Set gain/loss
        const gainLossEl = tile.querySelector('.gain-loss-value');
        const gainLoss = holding.gain_loss;
        const gainLossPercent = holding.gain_loss_percent;

        const sign = gainLoss >= 0 ? '+' : '';
        gainLossEl.textContent = `${sign}${formatPrice(Math.abs(gainLoss))} (${sign}${formatWithCommas(gainLossPercent, 2)}%)`;

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
                            return label + ': ' + formatPrice(value) + ' (' + percentage.toFixed(1) + '%)';
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
                <div class="legend-value">${formatPrice(item.value)}</div>
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
 * For consolidated holdings, excludes all lots of the same item
 */
// Store pending exclusion data for modal confirmation
let pendingExclusion = null;

function excludeHolding(button) {
    const tile = button.closest('.holding-tile');
    const orderItemIdsStr = tile.getAttribute('data-order-item-ids');
    const orderItemIds = orderItemIdsStr ? orderItemIdsStr.split(',') : [];

    if (orderItemIds.length === 0) {
        alert('No items to exclude');
        return;
    }

    const itemCount = orderItemIds.length;
    const message = itemCount === 1
        ? 'Remove this holding from your portfolio view? This will exclude it from your portfolio value and charts.'
        : `Remove all ${itemCount} lots of this item from your portfolio view? This will exclude them from your portfolio value and charts.`;

    // Store the exclusion data for confirmation
    pendingExclusion = {
        tile: tile,
        orderItemIds: orderItemIds
    };

    // Update modal message and open
    document.getElementById('excludeHoldingMessage').textContent = message;
    document.getElementById('excludeHoldingConfirmModal').style.display = 'flex';
}

function closeExcludeHoldingModal() {
    document.getElementById('excludeHoldingConfirmModal').style.display = 'none';
    pendingExclusion = null;
}

function confirmExcludeHolding() {
    if (!pendingExclusion) {
        closeExcludeHoldingModal();
        return;
    }

    const { tile, orderItemIds } = pendingExclusion;

    // Close modal immediately
    closeExcludeHoldingModal();

    // Exclude all order_item_ids for this consolidated holding
    const excludePromises = orderItemIds.map(id =>
        fetch(`/portfolio/exclude/${id}`, { method: 'POST' }).then(r => r.json())
    );

    Promise.all(excludePromises)
        .then(results => {
            const allSuccess = results.every(data => data.success);
            if (allSuccess) {
                // Remove tile with animation
                tile.style.opacity = '0';
                setTimeout(() => {
                    tile.remove();
                    // Reload portfolio data
                    loadPortfolioData();
                }, 300);
            } else {
                alert('Failed to exclude some items. Please try again.');
            }
        })
        .catch(error => {
            console.error('[Portfolio] Error excluding items:', error);
            alert('An error occurred. Please try again.');
        });
}

/**
 * Open Sell page with prefilled data from holding tile
 * Redirects to /sell with item details as query parameters
 */
function openListingModalFromHolding(button) {
    const tile = button.closest('.holding-tile');
    const bucketId = tile.getAttribute('data-bucket-id');

    if (!bucketId) {
        alert('Cannot list this item: Bucket ID not found');
        return;
    }

    // Extract holding data from tile
    const metal = tile.querySelector('.metal-value')?.textContent?.trim() || '';
    const productType = tile.querySelector('.product-type-value')?.textContent?.trim() || '';
    const weight = tile.querySelector('.weight-value')?.textContent?.trim() || '';
    const purity = tile.querySelector('.purity-value')?.textContent?.trim() || '';
    const mint = tile.querySelector('.mint-value')?.textContent?.trim() || '';
    const year = tile.querySelector('.year-value')?.textContent?.trim() || '';
    const finish = tile.querySelector('.finish-value')?.textContent?.trim() || '';
    const grade = tile.querySelector('.grade-value')?.textContent?.trim() || '';
    const productLine = tile.querySelector('.product-line-value')?.textContent?.trim() || '';

    // Build query string with prefilled data
    const params = new URLSearchParams();
    if (metal && metal !== '--') params.append('metal', metal);
    if (productType && productType !== '--') params.append('product_type', productType);
    if (weight && weight !== '--') params.append('weight', weight);
    if (purity && purity !== '--') params.append('purity', purity);
    if (mint && mint !== '--') params.append('mint', mint);
    if (year && year !== '--') params.append('year', year);
    if (finish && finish !== '--') params.append('finish', finish);
    if (grade && grade !== '--') params.append('grade', grade);
    if (productLine && productLine !== '--') params.append('product_line', productLine);

    // Redirect to Sell page with prefilled data
    window.location.href = `/sell?${params.toString()}`;
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

/**
 * View holding item details in the existing order items modal
 */
function viewHoldingDetails(button) {
    const tile = button.closest('.holding-tile');
    if (!tile) return;

    // Extract all the holding data from the tile's data attributes
    const holdingData = {
        // Category details from data attributes
        metal: tile.dataset.metal || null,
        product_type: tile.dataset.productType || null,
        weight: tile.dataset.weight || null,
        purity: tile.dataset.purity || null,
        mint: tile.dataset.mint || null,
        year: tile.dataset.year || null,
        finish: tile.dataset.finish || null,
        grade: tile.dataset.grade || null,
        product_line: tile.dataset.productLine || null,

        // Price and quantity from visible elements
        quantity: tile.querySelector('.quantity-value')?.textContent || null,
        price_each: tile.querySelector('.purchase-price-value')?.textContent?.replace(/[$,]/g, '') || null,

        // Grading info from data attributes
        grading: tile.dataset.grade || null,
        graded: tile.dataset.graded === '1' ? 1 : 0,
        grading_service: (tile.dataset.graded === '1') ? (tile.dataset.gradingService || null) : null,

        // Seller info from data attributes
        seller_username: tile.dataset.sellerUsername || null,

        // Image
        image_url: tile.querySelector('.holding-image img')?.src || null,

        // Title (construct from available data)
        title: (() => {
            const metal = tile.dataset.metal;
            const weight = tile.dataset.weight;
            const year = tile.dataset.year;
            const mint = tile.dataset.mint;

            let title = '';
            if (weight) title += weight + ' ';
            if (metal) title += metal;

            const details = [];
            if (mint) details.push(mint);
            if (year) details.push(year);

            if (details.length > 0) {
                title += ' (' + details.join(', ') + ')';
            }

            return title.trim() || 'Holding Item';
        })()
    };

    // Clean up any empty string values to null
    Object.keys(holdingData).forEach(key => {
        if (holdingData[key] === '') {
            holdingData[key] = null;
        }
    });

    // Open the existing order items modal with this single holding
    // Use openCartItemsPopup which accepts an array of items
    if (typeof openCartItemsPopup === 'function') {
        openCartItemsPopup([holdingData], { context: 'portfolio' });
    } else {
        console.error('openCartItemsPopup function not found');
    }
}

// Expose functions globally
window.excludeHolding = excludeHolding;
window.openListingModalFromHolding = openListingModalFromHolding;
window.viewHoldingDetails = viewHoldingDetails;
