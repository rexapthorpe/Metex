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
