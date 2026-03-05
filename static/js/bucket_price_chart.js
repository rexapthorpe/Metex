// static/js/bucket_price_chart.js
'use strict';

/* ==========================================================================
   Bucket Reference Price Chart
   Renders the canonical Reference Price P(t) for a bucket:
     - Midpoint of BestAsk + BestBid when both sides exist
     - Last cleared trade price when only one side (or neither) is active
   Polls the backend every 90 s and re-renders only when data has changed.
   ========================================================================== */

let bucketPriceChart = null;
let currentBucketTimeRange = '1d';  // Default to 1D instead of 1M
let bucketChartData = null;
let bucketChartMouseLeaveHandler = null;  // Store reference to event handler for cleanup
let currentBucketId = null;  // Stored for resize-triggered redraws
let chartResizeTimer = null;
let lastChartWasMobile = null;

// Polling state
let _chartPollTimer = null;
let _lastTimestamps = { spot: null, bid: null, clear: null };

const isMobileChart = () => window.innerWidth <= 768;

/**
 * Initialize bucket price chart
 * @param {number} bucketId - The bucket ID to load history for
 */
function initBucketPriceChart(bucketId) {
    console.log('[BucketChart] Initializing price chart for bucket:', bucketId);

    currentBucketId = bucketId;
    lastChartWasMobile = isMobileChart();

    // Setup time range selector
    setupBucketTimeRangeSelector(bucketId);

    // Load initial data
    loadBucketPriceHistory(bucketId, currentBucketTimeRange);

    // Start background polling
    startChartPolling(bucketId);

    // Stop polling when the page is navigated away
    window.addEventListener('beforeunload', stopChartPolling);

    // Redraw chart when crossing the mobile breakpoint (y-axis visibility changes)
    window.addEventListener('resize', function() {
        clearTimeout(chartResizeTimer);
        chartResizeTimer = setTimeout(function() {
            const nowMobile = isMobileChart();
            if (nowMobile !== lastChartWasMobile) {
                lastChartWasMobile = nowMobile;
                if (currentBucketId) {
                    loadBucketPriceHistory(currentBucketId, currentBucketTimeRange);
                }
            }
        }, 300);
    });
}

/**
 * Start background polling — re-renders chart only when timestamps change.
 */
function startChartPolling(bucketId) {
    if (_chartPollTimer) return; // Already running

    _chartPollTimer = setInterval(function() {
        const url = `/api/buckets/${bucketId}/reference_price_history?range=${currentBucketTimeRange}`;
        fetch(url)
            .then(r => r.json())
            .then(data => {
                if (!data.success) return;

                const spotChanged  = data.latest_spot_as_of  !== _lastTimestamps.spot;
                const bidChanged   = data.latest_bid_as_of   !== _lastTimestamps.bid;
                const clearChanged = data.latest_clear_as_of !== _lastTimestamps.clear;

                if (spotChanged || bidChanged || clearChanged) {
                    console.log('[BucketChart] Poll: data changed — re-rendering');
                    _lastTimestamps = {
                        spot:  data.latest_spot_as_of,
                        bid:   data.latest_bid_as_of,
                        clear: data.latest_clear_as_of,
                    };
                    bucketChartData = data;
                    updateBucketPriceSummary(data.summary);
                    renderBucketPriceChart(data.primary_series, currentBucketTimeRange);
                }
            })
            .catch(() => {}); // Silently ignore network errors during polling
    }, 90000); // 90 seconds
}

/**
 * Stop background polling.
 */
function stopChartPolling() {
    if (_chartPollTimer) {
        clearInterval(_chartPollTimer);
        _chartPollTimer = null;
    }
}

/**
 * Load reference price history from the new canonical API endpoint.
 */
function loadBucketPriceHistory(bucketId, range) {
    console.log('[BucketChart] Loading reference price history for bucket ID:', bucketId, 'range:', range);

    const chartContainer = document.getElementById('bucket-price-chart-container');
    const emptyState = document.getElementById('bucket-price-empty-state');

    // Validate bucket ID
    if (!bucketId) {
        console.error('[BucketChart] No bucket ID provided!');
        if (chartContainer) chartContainer.style.display = 'none';
        if (emptyState) emptyState.style.display = 'flex';
        return;
    }

    fetch(`/api/buckets/${bucketId}/reference_price_history?range=${encodeURIComponent(range)}`)
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

                // Store timestamps for change-detection polling
                _lastTimestamps = {
                    spot:  data.latest_spot_as_of,
                    bid:   data.latest_bid_as_of,
                    clear: data.latest_clear_as_of,
                };

                const series = data.primary_series || [];

                if (series.length > 0) {
                    console.log('[BucketChart] Found', series.length, 'reference price points');

                    if (chartContainer) chartContainer.style.display = 'block';
                    if (emptyState) emptyState.style.display = 'none';

                    updateBucketPriceSummary(data.summary);
                    renderBucketPriceChart(series, range);
                } else {
                    console.log('[BucketChart] No reference price data for this bucket');
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

    // Sort by timestamp to ensure proper ordering (series points use key 't')
    chartData.sort((a, b) => {
        const dateA = a.t instanceof Date ? a.t : new Date(a.t);
        const dateB = b.t instanceof Date ? b.t : new Date(b.t);
        return dateA - dateB;
    });

    // Handle duplicate or extremely close timestamps to prevent degenerate curve artifacts
    // Add tiny offsets (milliseconds) purely for rendering while preserving data integrity
    for (let i = 1; i < chartData.length; i++) {
        const prevDate = chartData[i - 1].t instanceof Date ?
            chartData[i - 1].t : new Date(chartData[i - 1].t);
        const currDate = chartData[i].t instanceof Date ?
            chartData[i].t : new Date(chartData[i].t);

        // If timestamps are identical or within 1 second, add small offset
        const timeDiff = currDate.getTime() - prevDate.getTime();
        if (timeDiff < 1000) {
            // Offset by i milliseconds to maintain ordering
            const offsetDate = new Date(prevDate.getTime() + i);
            chartData[i].t = offsetDate;
            console.log('[BucketChart] Adjusted close timestamp:', currDate, '->', offsetDate);
        }
    }

    // Determine time range boundaries (using browser's local timezone)
    const now = new Date();
    let minTime, maxTime, timeUnit, xMaxTicks;

    switch(range) {
        case '1d':
            minTime = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            maxTime = now;
            timeUnit = 'hour';
            xMaxTicks = 7;   // ~every 3-4 h
            break;
        case '1w':
            minTime = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            maxTime = now;
            timeUnit = 'day';
            xMaxTicks = 7;   // one per day
            break;
        case '1m':
            minTime = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            maxTime = now;
            timeUnit = 'day';
            xMaxTicks = 6;   // ~every 5 days
            break;
        case '3m':
            minTime = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
            maxTime = now;
            timeUnit = 'week';
            xMaxTicks = 7;   // ~every 2 weeks
            break;
        case '1y':
            minTime = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000);
            maxTime = now;
            timeUnit = 'month';
            xMaxTicks = 12;  // one per month
            break;
        default:
            minTime = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            maxTime = now;
            timeUnit = 'day';
            xMaxTicks = 6;
    }

    // Apply backfill and forward-fill to ensure line spans full interval
    if (chartData.length > 0) {
        const firstDataPoint = chartData[0];
        const lastDataPoint = chartData[chartData.length - 1];

        const firstDate = firstDataPoint.t instanceof Date ?
            firstDataPoint.t : new Date(firstDataPoint.t);
        const lastDate = lastDataPoint.t instanceof Date ?
            lastDataPoint.t : new Date(lastDataPoint.t);

        // Backfill: If first data point is after minTime, add a point at minTime with same price
        if (firstDate > minTime) {
            console.log('[BucketChart] Backfilling from', minTime, 'to first data point at', firstDate);
            chartData.unshift({ t: new Date(minTime), price: firstDataPoint.price });
        }

        // Forward-fill: If last data point is before now, add a point at now with same price
        if (lastDate < maxTime) {
            console.log('[BucketChart] Forward-filling from last data point at', lastDate, 'to', maxTime);
            chartData.push({ t: new Date(maxTime), price: lastDataPoint.price });
        }
    } else if (chartData.length === 0) {
        // No data - show empty state (handled by caller)
        console.log('[BucketChart] No data to display');
        return;
    }

    // Prepare data points with actual timestamps for time-scale plotting
    const dataPoints = chartData.map(item => {
        const date = item.t instanceof Date ? item.t : new Date(item.t);
        return {
            x: date,  // Use actual Date object for time-based positioning
            y: item.price
        };
    });

    // Calculate Y-axis domain — never allow negative values for price history
    const prices = dataPoints.map(p => p.y).filter(v => typeof v === 'number' && isFinite(v));
    const minPrice = prices.length ? Math.min(...prices) : 0;
    const maxPrice = prices.length ? Math.max(...prices) : 100;
    const priceRange = maxPrice - minPrice;

    let yMin, yMax;
    if (prices.length === 0) {
        yMin = 0;
        yMax = 100;
    } else if (priceRange === 0) {
        // Flat line — pad by 5% of the value (min $1) symmetrically, floor at 0
        const margin = Math.max(minPrice * 0.05, 1);
        yMin = Math.max(0, minPrice - margin);
        yMax = maxPrice + margin;
    } else {
        // Normal case — pad by 10% of the range, floor yMin at 0
        const margin = priceRange * 0.1;
        yMin = Math.max(0, minPrice - margin);
        yMax = maxPrice + margin;
    }

    // Snap to clean integers so tick labels land on round numbers
    yMin = Math.floor(yMin);
    yMax = Math.ceil(yMax);

    console.log('[BucketChart] Chart data points:', dataPoints.length);
    console.log('[BucketChart] Time range:', minTime.toLocaleString(), 'to', maxTime.toLocaleString());
    console.log('[BucketChart] Using time scale with unit:', timeUnit, 'maxTicks:', xMaxTicks);
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
                    label: 'Reference Price',
                    data: dataPoints,  // Use {x, y} format with Date objects
                    borderColor: '#0066cc',
                    backgroundColor: gradient,
                    borderWidth: 3,
                    fill: true,
                    tension: 0,  // Straight lines between points (no curves)
                    pointRadius: 0,
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
                        enabled: false  // Disabled — hover updates the top-left price indicators instead
                    }
                },
                scales: {
                    y: {
                        display: !isMobileChart(),  // Hide y-axis on mobile — chart fills full width
                        beginAtZero: false,
                        min: yMin,  // Apply 10% margin below minimum
                        max: yMax,  // Apply 10% margin above maximum
                        grid: {
                            color: isMobileChart() ? 'transparent' : '#f3f4f6',
                            drawBorder: false,
                            display: !isMobileChart()
                        },
                        ticks: {
                            display: !isMobileChart(),
                            font: {
                                size: 12
                            },
                            color: '#6b7280',
                            maxTicksLimit: 6,
                            callback: function(value) {
                                if (value < 0) return '';  // Defensive: never show negative labels
                                return '$' + formatWithCommas(value, 0);
                            }
                        }
                    },
                    x: {
                        type: 'time',  // Use time scale for accurate positioning
                        min: minTime,  // Start of time range (browser timezone)
                        max: maxTime,  // End of time range (browser timezone)
                        time: {
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
                            minRotation: 0,
                            autoSkip: true,
                            autoSkipPadding: 20,
                            maxTicksLimit: xMaxTicks,
                            source: 'auto'        // Uniform distribution, not one-per-data-point
                        }
                    }
                },
                onHover: function(event, activeElements) {
                    // Update summary when hovering over data points
                    if (activeElements && activeElements.length > 0) {
                        const index = activeElements[0].index;
                        const hoveredPrice = dataPoints[index].y;
                        const hoveredDate = dataPoints[index].x;
                        const firstPrice = bucketChartData.summary.first_price;
                        const changeAmount = hoveredPrice - firstPrice;
                        const changePercent = (changeAmount / firstPrice * 100);

                        updateBucketPriceSummary({
                            current_price: hoveredPrice,
                            change_amount: changeAmount,
                            change_percent: changePercent
                        });
                        updateBucketPriceDatetime(hoveredDate, range);
                    } else {
                        // Reset to original summary when not hovering
                        updateBucketPriceSummary(bucketChartData.summary);
                        clearBucketPriceDatetime();
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
                clearBucketPriceDatetime();
            }
        };
        ctx.addEventListener('mouseleave', bucketChartMouseLeaveHandler);

    } catch (error) {
        console.error('[BucketChart] ERROR creating chart:', error);
        console.error('[BucketChart] Error stack:', error.stack);
    }
}

/**
 * Update the datetime indicator below the main price display.
 * @param {Date} date - The timestamp of the hovered data point
 * @param {string} range - Current time range (1d, 1w, 1m, 3m, 1y)
 */
function updateBucketPriceDatetime(date, range) {
    const el = document.getElementById('bucket-price-datetime');
    if (!el || !(date instanceof Date)) return;

    let formatted;
    if (range === '1d') {
        // e.g. "Sun, Mar 1 · 4:30 PM"
        formatted = date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
            + ' · '
            + date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
    } else {
        // e.g. "Sun, Mar 1, 2026"
        formatted = date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
    }

    el.textContent = formatted;
}

/**
 * Clear the datetime indicator (when hover ends).
 */
function clearBucketPriceDatetime() {
    const el = document.getElementById('bucket-price-datetime');
    if (el) el.textContent = '';
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
window.stopChartPolling = stopChartPolling;
