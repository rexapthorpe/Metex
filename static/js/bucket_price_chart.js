// static/js/bucket_price_chart.js
'use strict';

/* ==========================================================================
   Bucket Price History Chart
   Tracks best ask price changes over time for a specific bucket
   ========================================================================== */

let bucketPriceChart = null;
let currentBucketTimeRange = '1d';  // Default to 1D instead of 1M
let bucketChartData = null;
let bucketChartMouseLeaveHandler = null;  // Store reference to event handler for cleanup

/**
 * Initialize bucket price chart
 * @param {number} bucketId - The bucket ID to load history for
 */
function initBucketPriceChart(bucketId) {
    console.log('[BucketChart] Initializing price chart for bucket:', bucketId);

    // Setup time range selector
    setupBucketTimeRangeSelector(bucketId);

    // Load initial data
    loadBucketPriceHistory(bucketId, currentBucketTimeRange);
}

/**
 * Load bucket price history from API
 */
function loadBucketPriceHistory(bucketId, range) {
    console.log('[BucketChart] Loading history for bucket ID:', bucketId, 'range:', range);

    const chartContainer = document.getElementById('bucket-price-chart-container');
    const emptyState = document.getElementById('bucket-price-empty-state');

    // Validate bucket ID
    if (!bucketId) {
        console.error('[BucketChart] No bucket ID provided!');
        if (chartContainer) chartContainer.style.display = 'none';
        if (emptyState) emptyState.style.display = 'flex';
        return;
    }

    // Build query parameters including filters
    const params = new URLSearchParams({ range });

    // Add Random Year mode if enabled
    const randomYearToggle = document.getElementById('randomYearToggle');
    if (randomYearToggle && randomYearToggle.checked) {
        params.append('random_year', '1');
    }

    // Add packaging filters (multi-select checkboxes)
    const packagingTypeCheckboxes = document.querySelectorAll('.packaging-type-checkbox:checked');
    packagingTypeCheckboxes.forEach(checkbox => {
        params.append('packaging_styles', checkbox.value);
    });

    fetch(`/bucket/${bucketId}/price-history?${params.toString()}`)
        .then(response => {
            console.log('[BucketChart] History response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('[BucketChart] History data received:', data);

            if (data.success) {
                bucketChartData = data;

                if (data.history && data.history.length > 0) {
                    console.log('[BucketChart] Found', data.history.length, 'history points');

                    // Check if this is historical data with no active listings
                    if (data.summary && !data.summary.has_active_listings) {
                        console.log('[BucketChart] No active listings - displaying historical data with forward-fill');
                    }

                    // Show chart, hide empty state (even if no active listings)
                    if (chartContainer) chartContainer.style.display = 'block';
                    if (emptyState) emptyState.style.display = 'none';

                    // Update summary
                    updateBucketPriceSummary(data.summary);

                    // Render chart (will forward-fill if needed)
                    renderBucketPriceChart(data.history, range);
                } else {
                    // Truly no historical data at all - show empty state
                    console.log('[BucketChart] No price history exists for this bucket');
                    if (chartContainer) chartContainer.style.display = 'none';
                    if (emptyState) emptyState.style.display = 'flex';
                }
            } else {
                console.error('[BucketChart] API returned success=false:', data.error);
                if (chartContainer) chartContainer.style.display = 'none';
                if (emptyState) emptyState.style.display = 'flex';
            }
        })
        .catch(error => {
            console.error('[BucketChart] Error loading history:', error);
            console.error('[BucketChart] Bucket ID was:', bucketId);
            if (chartContainer) chartContainer.style.display = 'none';
            if (emptyState) emptyState.style.display = 'flex';
        });
}

/**
 * Update price summary section
 */
function updateBucketPriceSummary(summary) {
    const currentPriceEl = document.getElementById('bucket-current-price');
    const changeAmountEl = document.getElementById('bucket-price-change-amount');
    const changePercentEl = document.getElementById('bucket-price-change-percent');
    const changeContainerEl = document.getElementById('bucket-price-change');

    if (currentPriceEl && summary.current_price !== null) {
        currentPriceEl.textContent = formatPrice(summary.current_price);
    }

    if (changeAmountEl && changePercentEl && changeContainerEl) {
        const changeAmount = summary.change_amount || 0;
        const changePercent = summary.change_percent || 0;

        const sign = changeAmount >= 0 ? '+' : '';
        changeAmountEl.textContent = `${sign}${formatPrice(Math.abs(changeAmount), false)}`;
        changePercentEl.textContent = `(${sign}${formatWithCommas(changePercent, 2)}%)`;

        // Update color class
        changeContainerEl.classList.remove('positive', 'negative', 'neutral');
        if (changeAmount > 0) {
            changeContainerEl.classList.add('positive');
        } else if (changeAmount < 0) {
            changeContainerEl.classList.add('negative');
        } else {
            changeContainerEl.classList.add('neutral');
        }
    }
}

/**
 * Generate uniform time intervals for consistent x-axis spacing
 * @param {Array} historyData - Raw price history data
 * @param {string} range - Time range (1d, 1w, 1m, 3m, 1y)
 * @returns {Array} Normalized data with uniform time intervals
 */
function normalizeToUniformIntervals(historyData, range) {
    if (!historyData || historyData.length === 0) {
        return [];
    }

    // Determine time range and interval based on selected range
    const now = new Date();
    let startTime, intervalMs, numIntervals;

    switch(range) {
        case '1d':
            // 1 Day: hourly intervals (24 points)
            startTime = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            intervalMs = 60 * 60 * 1000; // 1 hour
            numIntervals = 24;
            break;
        case '1w':
            // 1 Week: daily intervals (7 points)
            startTime = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            intervalMs = 24 * 60 * 60 * 1000; // 1 day
            numIntervals = 7;
            break;
        case '1m':
            // 1 Month: every 2 days (15 points)
            startTime = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            intervalMs = 2 * 24 * 60 * 60 * 1000; // 2 days
            numIntervals = 15;
            break;
        case '3m':
            // 3 Months: weekly intervals (12 points)
            startTime = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
            intervalMs = 7 * 24 * 60 * 60 * 1000; // 1 week
            numIntervals = 13;
            break;
        case '1y':
            // 1 Year: bi-weekly intervals (26 points)
            startTime = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000);
            intervalMs = 14 * 24 * 60 * 60 * 1000; // 2 weeks
            numIntervals = 26;
            break;
        default:
            // Default to monthly
            startTime = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            intervalMs = 2 * 24 * 60 * 60 * 1000;
            numIntervals = 15;
    }

    // Generate uniform time points
    const uniformPoints = [];
    for (let i = 0; i < numIntervals; i++) {
        const timestamp = new Date(startTime.getTime() + (i * intervalMs));
        uniformPoints.push({
            timestamp: timestamp,
            price: null
        });
    }

    // Sort raw data by timestamp
    const sortedData = [...historyData].sort((a, b) =>
        new Date(a.timestamp) - new Date(b.timestamp)
    );

    // Map prices to uniform intervals using "last known price" approach
    let lastKnownPrice = null;
    let dataIndex = 0;

    for (let i = 0; i < uniformPoints.length; i++) {
        const uniformTime = uniformPoints[i].timestamp;

        // Advance through data to find all prices up to this uniform time point
        while (dataIndex < sortedData.length) {
            const dataTime = new Date(sortedData[dataIndex].timestamp);

            if (dataTime <= uniformTime) {
                lastKnownPrice = sortedData[dataIndex].price;
                dataIndex++;
            } else {
                break;
            }
        }

        // Assign the last known price to this uniform point
        if (lastKnownPrice !== null) {
            uniformPoints[i].price = lastKnownPrice;
        }
    }

    // Filter out points with no price (before first data point)
    const validPoints = uniformPoints.filter(point => point.price !== null);

    console.log('[BucketChart] Normalized', historyData.length, 'raw points to', validPoints.length, 'uniform intervals');

    return validPoints;
}

/**
 * Render bucket price line chart
 */
function renderBucketPriceChart(historyData, range) {
    console.log('[BucketChart] renderBucketPriceChart called with', historyData.length, 'data points');

    const ctx = document.getElementById('bucket-price-chart');
    if (!ctx) {
        console.error('[BucketChart] Canvas element not found!');
        return;
    }

    console.log('[BucketChart] Canvas found, preparing data...');

    // Use raw data - plot at actual timestamps (time scale handles spacing)
    let chartData = [...historyData];

    // Sort by timestamp to ensure proper ordering
    chartData.sort((a, b) => {
        const dateA = a.timestamp instanceof Date ? a.timestamp : new Date(a.timestamp);
        const dateB = b.timestamp instanceof Date ? b.timestamp : new Date(b.timestamp);
        return dateA - dateB;
    });

    // Handle duplicate or extremely close timestamps to prevent degenerate curve artifacts
    // Add tiny offsets (milliseconds) purely for rendering while preserving data integrity
    for (let i = 1; i < chartData.length; i++) {
        const prevDate = chartData[i - 1].timestamp instanceof Date ?
            chartData[i - 1].timestamp : new Date(chartData[i - 1].timestamp);
        const currDate = chartData[i].timestamp instanceof Date ?
            chartData[i].timestamp : new Date(chartData[i].timestamp);

        // If timestamps are identical or within 1 second, add small offset
        const timeDiff = currDate.getTime() - prevDate.getTime();
        if (timeDiff < 1000) {
            // Offset by i milliseconds to maintain ordering
            const offsetDate = new Date(prevDate.getTime() + i);
            chartData[i].timestamp = offsetDate;
            console.log('[BucketChart] Adjusted close timestamp:', currDate, '->', offsetDate);
        }
    }

    // Determine time range boundaries (using browser's local timezone)
    const now = new Date();
    let minTime, maxTime, timeUnit, stepSize;

    switch(range) {
        case '1d':
            // Rolling 24-hour window in user's local timezone
            minTime = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            maxTime = now;
            timeUnit = 'hour';
            stepSize = 3; // Every 3 hours
            break;
        case '1w':
            minTime = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            maxTime = now;
            timeUnit = 'day';
            stepSize = 1; // Every day
            break;
        case '1m':
            minTime = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            maxTime = now;
            timeUnit = 'day';
            stepSize = 5; // Every 5 days
            break;
        case '3m':
            minTime = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
            maxTime = now;
            timeUnit = 'week';
            stepSize = 2; // Every 2 weeks
            break;
        case '1y':
            minTime = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000);
            maxTime = now;
            timeUnit = 'month';
            stepSize = 1; // Every month
            break;
        default:
            minTime = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            maxTime = now;
            timeUnit = 'day';
            stepSize = 5;
    }

    // Apply backfill and forward-fill to ensure line spans full interval
    if (chartData.length > 0) {
        const firstDataPoint = chartData[0];
        const lastDataPoint = chartData[chartData.length - 1];

        const firstDate = firstDataPoint.timestamp instanceof Date ?
            firstDataPoint.timestamp : new Date(firstDataPoint.timestamp);
        const lastDate = lastDataPoint.timestamp instanceof Date ?
            lastDataPoint.timestamp : new Date(lastDataPoint.timestamp);

        // Backfill: If first data point is after minTime, add a point at minTime with same price
        if (firstDate > minTime) {
            console.log('[BucketChart] Backfilling from', minTime, 'to first data point at', firstDate);
            chartData.unshift({
                timestamp: new Date(minTime),
                price: firstDataPoint.price
            });
        }

        // Forward-fill: If last data point is before now, add a point at now with same price
        if (lastDate < maxTime) {
            console.log('[BucketChart] Forward-filling from last data point at', lastDate, 'to', maxTime);
            chartData.push({
                timestamp: new Date(maxTime),
                price: lastDataPoint.price
            });
        }
    } else if (chartData.length === 0) {
        // No data - show empty state (handled by caller)
        console.log('[BucketChart] No data to display');
        return;
    }

    // Prepare data points with actual timestamps for time-scale plotting
    const dataPoints = chartData.map(item => {
        const date = item.timestamp instanceof Date ? item.timestamp : new Date(item.timestamp);
        return {
            x: date,  // Use actual Date object for time-based positioning
            y: item.price
        };
    });

    // Calculate Y-axis range with 10% margin
    const prices = dataPoints.map(p => p.y);
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const priceRange = maxPrice - minPrice;

    let yMin, yMax;
    if (priceRange === 0) {
        // All prices are equal - add symmetric margin (10% of the price value, or $1 minimum)
        const margin = Math.max(minPrice * 0.1, 1);
        yMin = minPrice - margin;
        yMax = maxPrice + margin;
        console.log('[BucketChart] All prices equal at', minPrice, '- using symmetric margin:', margin);
    } else {
        // Add 10% margin based on the actual price range
        const margin = priceRange * 0.1;
        yMin = minPrice - margin;
        yMax = maxPrice + margin;
        console.log('[BucketChart] Price range:', minPrice, 'to', maxPrice, '- adding 10% margin:', margin);
    }

    console.log('[BucketChart] Chart data points:', dataPoints.length);
    console.log('[BucketChart] Time range:', minTime.toLocaleString(), 'to', maxTime.toLocaleString());
    console.log('[BucketChart] Using time scale with unit:', timeUnit, 'step:', stepSize);
    console.log('[BucketChart] Y-axis range:', yMin.toFixed(2), 'to', yMax.toFixed(2));

    // Destroy existing chart if it exists
    if (bucketPriceChart) {
        console.log('[BucketChart] Destroying existing chart');
        bucketPriceChart.destroy();
    }

    // Remove previous mouseleave handler if it exists
    if (bucketChartMouseLeaveHandler) {
        ctx.removeEventListener('mouseleave', bucketChartMouseLeaveHandler);
        bucketChartMouseLeaveHandler = null;
    }

    // Create gradient
    try {
        const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 400);
        gradient.addColorStop(0, 'rgba(0, 102, 204, 0.15)');
        gradient.addColorStop(1, 'rgba(0, 102, 204, 0)');

        console.log('[BucketChart] Creating Chart.js chart...');

        // Store normalized data for hover functionality
        const originalData = chartData;

        // Create chart with time scale for accurate positioning
        bucketPriceChart = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [{
                    label: 'Best Ask Price',
                    data: dataPoints,  // Use {x, y} format with Date objects
                    borderColor: '#0066cc',
                    backgroundColor: gradient,
                    borderWidth: 3,
                    fill: true,
                    cubicInterpolationMode: 'monotone',  // Use monotone cubic spline to prevent vertical loops
                    tension: 0,  // Disable Bezier tension (monotone handles smoothing)
                    pointRadius: 4,
                    pointBackgroundColor: '#0066cc',
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 2,
                    pointHoverRadius: 7,
                    pointHoverBackgroundColor: '#0066cc',
                    pointHoverBorderColor: '#ffffff',
                    pointHoverBorderWidth: 3
                }]
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
                        display: false
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
                        displayColors: false,
                        callbacks: {
                            title: function(context) {
                                // Show full date/time
                                const index = context[0].dataIndex;
                                const timestamp = originalData[index].timestamp;
                                const date = timestamp instanceof Date ? timestamp : new Date(timestamp);

                                if (range === '1d') {
                                    return date.toLocaleString('en-US', {
                                        month: 'short',
                                        day: 'numeric',
                                        hour: 'numeric',
                                        minute: '2-digit',
                                        hour12: true
                                    });
                                } else {
                                    return date.toLocaleDateString('en-US', {
                                        month: 'short',
                                        day: 'numeric',
                                        year: 'numeric'
                                    });
                                }
                            },
                            label: function(context) {
                                const price = context.parsed.y;

                                // Calculate change from first point
                                const firstPrice = bucketChartData.summary.first_price;
                                const changeAmount = price - firstPrice;
                                const changePercent = (changeAmount / firstPrice * 100);

                                const sign = changeAmount >= 0 ? '+' : '';

                                return [
                                    'Price: ' + formatPrice(price),
                                    sign + formatPrice(Math.abs(changeAmount), false) + ' (' + sign + formatWithCommas(changePercent, 2) + '%)'
                                ];
                            },
                            afterLabel: function(context) {
                                return ''; // Empty to add spacing
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: false,
                        min: yMin,  // Apply 10% margin below minimum
                        max: yMax,  // Apply 10% margin above maximum
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
                        type: 'time',  // Use time scale for accurate positioning
                        min: minTime,  // Start of time range (browser timezone)
                        max: maxTime,  // End of time range (browser timezone)
                        time: {
                            unit: timeUnit,
                            stepSize: stepSize,
                            displayFormats: {
                                hour: 'h a',           // "9 AM"
                                day: 'MMM d',          // "Nov 2"
                                week: 'MMM d',         // "Nov 2"
                                month: 'MMM yyyy'      // "Nov 2024"
                            },
                            tooltipFormat: range === '1d' ? 'MMM d, h:mm a' : 'MMM d, yyyy'
                        },
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
                            autoSkip: false,  // Don't skip - we control with stepSize
                            source: 'auto'
                        }
                    }
                },
                onHover: function(event, activeElements) {
                    // Update summary when hovering over data points
                    if (activeElements && activeElements.length > 0) {
                        const index = activeElements[0].index;
                        const hoveredPrice = dataPoints[index].y;
                        const firstPrice = bucketChartData.summary.first_price;
                        const changeAmount = hoveredPrice - firstPrice;
                        const changePercent = (changeAmount / firstPrice * 100);

                        updateBucketPriceSummary({
                            current_price: hoveredPrice,
                            change_amount: changeAmount,
                            change_percent: changePercent
                        });
                    } else {
                        // Reset to original summary when not hovering
                        updateBucketPriceSummary(bucketChartData.summary);
                    }
                }
            },
            plugins: [{
                id: 'verticalHoverLine',
                afterDatasetsDraw: function(chart) {
                    if (chart.tooltip._active && chart.tooltip._active.length) {
                        const activePoint = chart.tooltip._active[0];
                        const ctx = chart.ctx;
                        const x = activePoint.element.x;
                        const topY = chart.scales.y.top;
                        const bottomY = chart.scales.y.bottom;

                        // Draw vertical line
                        ctx.save();
                        ctx.beginPath();
                        ctx.moveTo(x, topY);
                        ctx.lineTo(x, bottomY);
                        ctx.lineWidth = 1;
                        ctx.strokeStyle = '#9ca3af';
                        ctx.stroke();
                        ctx.restore();
                    }
                }
            }]
        });

        console.log('[BucketChart] ✓ Chart created successfully!');

        // Add mouseleave event to reset summary when cursor leaves chart
        bucketChartMouseLeaveHandler = function() {
            // Reset to original summary data (current price, not last hovered)
            if (bucketChartData && bucketChartData.summary) {
                console.log('[BucketChart] Mouse left chart - resetting summary to current price');
                updateBucketPriceSummary(bucketChartData.summary);
            }
        };
        ctx.addEventListener('mouseleave', bucketChartMouseLeaveHandler);

    } catch (error) {
        console.error('[BucketChart] ERROR creating chart:', error);
        console.error('[BucketChart] Error stack:', error.stack);
    }
}

/**
 * Setup time range selector
 */
function setupBucketTimeRangeSelector(bucketId) {
    const timeBtns = document.querySelectorAll('.bucket-time-btn');

    timeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const range = btn.getAttribute('data-range');

            // Update active state
            timeBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Load new data
            currentBucketTimeRange = range;
            loadBucketPriceHistory(bucketId, range);
        });
    });
}

// Expose functions globally
window.initBucketPriceChart = initBucketPriceChart;
window.loadBucketPriceHistory = loadBucketPriceHistory;
