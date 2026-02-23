function openMetricsModal(metricType) {
  currentMetricType = metricType;
  currentMetricsDays = 30;

  const config = METRIC_CONFIG[metricType];
  if (!config) {
    console.error('Unknown metric type:', metricType);
    return;
  }

  // Update modal header
  const iconEl = document.getElementById('metricsModalIcon');
  iconEl.className = `metrics-icon ${config.iconClass}`;
  iconEl.innerHTML = `<i class="fa-solid ${config.icon}"></i>`;

  document.getElementById('metricsModalTitle').textContent = config.title;
  document.getElementById('metricsModalSubtitle').textContent = 'Last 30 days';

  // Reset time selector buttons
  document.querySelectorAll('.metrics-time-btn').forEach(btn => {
    btn.classList.remove('active');
    if (btn.dataset.range === '30') {
      btn.classList.add('active');
    }
  });

  // Show loading state
  document.getElementById('metricsChartLoading').classList.remove('hidden');

  // Show modal
  document.getElementById('metricsModal').style.display = 'flex';

  // Fetch and render data
  loadMetricsData(metricType, 30);
}

function closeMetricsModal() {
  document.getElementById('metricsModal').style.display = 'none';

  // Destroy chart to free memory
  if (metricsChart) {
    metricsChart.destroy();
    metricsChart = null;
  }
}

function changeMetricsRange(days) {
  currentMetricsDays = days;

  // Update button states
  document.querySelectorAll('.metrics-time-btn').forEach(btn => {
    btn.classList.remove('active');
    if (parseInt(btn.dataset.range) === days) {
      btn.classList.add('active');
    }
  });

  // Update subtitle
  const subtitleMap = {
    7: 'Last 7 days',
    30: 'Last 30 days',
    90: 'Last 90 days',
    365: 'Last year',
    0: 'All time'
  };
  document.getElementById('metricsModalSubtitle').textContent = subtitleMap[days] || 'Custom range';

  // Show loading state
  document.getElementById('metricsChartLoading').classList.remove('hidden');

  // Fetch new data
  loadMetricsData(currentMetricType, days);
}

function loadMetricsData(metricType, days) {
  fetch(`/admin/api/metrics/${metricType}?days=${days}`)
    .then(response => response.json())
    .then(data => {
      document.getElementById('metricsChartLoading').classList.add('hidden');

      if (data.success) {
        renderMetricsData(metricType, data);
      } else {
        console.error('Error loading metrics:', data.error);
        showMetricsError('Failed to load metrics data');
      }
    })
    .catch(error => {
      console.error('Error fetching metrics:', error);
      document.getElementById('metricsChartLoading').classList.add('hidden');
      showMetricsError('Network error. Please try again.');
    });
}

function renderMetricsData(metricType, data) {
  const config = METRIC_CONFIG[metricType];

  // Update summary cards
  document.getElementById('metricsCurrent').textContent = config.formatValue(data.current_value);

  const highEl = document.getElementById('metricsPeriodHigh');
  highEl.textContent = config.formatValue(data.summary.high);

  const lowEl = document.getElementById('metricsPeriodLow');
  lowEl.textContent = config.formatValue(data.summary.low);

  document.getElementById('metricsPeriodAvg').textContent = config.formatValue(data.summary.average);

  const changeEl = document.getElementById('metricsPeriodChange');
  const changeValue = data.summary.change_percent;
  changeEl.textContent = (changeValue >= 0 ? '+' : '') + changeValue.toFixed(1) + '%';
  changeEl.className = 'metrics-summary-value ' + (changeValue >= 0 ? 'metrics-change-positive' : 'metrics-change-negative');

  // Render chart
  renderMetricsChart(metricType, data.data_points, config);

  // Render additional details
  renderAdditionalDetails(metricType, data.additional_details);
}

function renderMetricsChart(metricType, dataPoints, config) {
  const ctx = document.getElementById('metricsChart').getContext('2d');

  // Destroy existing chart
  if (metricsChart) {
    metricsChart.destroy();
  }

  // Prepare data
  const labels = dataPoints.map(d => formatChartDate(d.date));
  const values = dataPoints.map(d => d.value);

  // Create gradient
  const gradient = ctx.createLinearGradient(0, 0, 0, 280);
  gradient.addColorStop(0, config.bgColor.replace('0.1', '0.4'));
  gradient.addColorStop(1, config.bgColor.replace('0.1', '0'));

  metricsChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: config.chartLabel,
        data: values,
        borderColor: config.color,
        backgroundColor: gradient,
        borderWidth: 2.5,
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 6,
        pointHoverBackgroundColor: config.color,
        pointHoverBorderColor: '#ffffff',
        pointHoverBorderWidth: 2
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
          backgroundColor: '#1e293b',
          titleColor: '#f1f5f9',
          bodyColor: '#f1f5f9',
          titleFont: {
            size: 13,
            weight: '600'
          },
          bodyFont: {
            size: 14,
            weight: '700'
          },
          padding: 12,
          cornerRadius: 8,
          displayColors: false,
          callbacks: {
            title: function(context) {
              return context[0].label;
            },
            label: function(context) {
              return config.formatValue(context.raw);
            }
          }
        }
      },
      scales: {
        x: {
          grid: {
            display: false
          },
          ticks: {
            font: {
              size: 11
            },
            color: '#94a3b8',
            maxTicksLimit: 8
          },
          border: {
            display: false
          }
        },
        y: {
          grid: {
            color: '#f1f5f9',
            drawBorder: false
          },
          ticks: {
            font: {
              size: 11
            },
            color: '#94a3b8',
            callback: function(value) {
              if (metricType === 'volume' || metricType === 'revenue') {
                return formatCompactCurrency(value);
              }
              return formatCompactNumber(value);
            }
          },
          border: {
            display: false
          }
        }
      }
    }
  });
}

function renderAdditionalDetails(metricType, details) {
  const container = document.getElementById('metricsDetailsGrid');

  let html = '';

  if (metricType === 'users') {
    html = `
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">New Today</span>
        <span class="metrics-detail-value">${details.new_today || 0}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">New This Week</span>
        <span class="metrics-detail-value">${details.new_this_week || 0}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">New This Month</span>
        <span class="metrics-detail-value">${details.new_this_month || 0}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Users with Email</span>
        <span class="metrics-detail-value">${details.with_email || 0}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Avg. Per Day (30d)</span>
        <span class="metrics-detail-value">${details.avg_per_day || 0}</span>
      </div>
    `;
  } else if (metricType === 'listings') {
    html = `
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Total Listings</span>
        <span class="metrics-detail-value">${(details.total_listings || 0).toLocaleString()}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Currently Active</span>
        <span class="metrics-detail-value">${(details.active_listings || 0).toLocaleString()}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Sold Out</span>
        <span class="metrics-detail-value">${(details.sold_out || 0).toLocaleString()}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Gold Listings</span>
        <span class="metrics-detail-value">${(details.gold_listings || 0).toLocaleString()}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Silver Listings</span>
        <span class="metrics-detail-value">${(details.silver_listings || 0).toLocaleString()}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Platinum Listings</span>
        <span class="metrics-detail-value">${(details.platinum_listings || 0).toLocaleString()}</span>
      </div>
    `;
  } else if (metricType === 'volume') {
    html = `
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Today's Volume</span>
        <span class="metrics-detail-value">${formatCurrency(details.today_volume || 0)}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">This Week</span>
        <span class="metrics-detail-value">${formatCurrency(details.week_volume || 0)}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">This Month</span>
        <span class="metrics-detail-value">${formatCurrency(details.month_volume || 0)}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Total Orders</span>
        <span class="metrics-detail-value">${(details.total_orders || 0).toLocaleString()}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Avg. Order Value</span>
        <span class="metrics-detail-value">${formatCurrency(details.avg_order_value || 0)}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Daily Avg. (30d)</span>
        <span class="metrics-detail-value">${formatCurrency(details.daily_avg || 0)}</span>
      </div>
    `;
  } else if (metricType === 'revenue') {
    html = `
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Today's Revenue</span>
        <span class="metrics-detail-value">${formatCurrency(details.today_revenue || 0)}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">This Week</span>
        <span class="metrics-detail-value">${formatCurrency(details.week_revenue || 0)}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">This Month</span>
        <span class="metrics-detail-value">${formatCurrency(details.month_revenue || 0)}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Platform Fee Rate</span>
        <span class="metrics-detail-value">${details.fee_rate || '2.5%'}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Total Volume Processed</span>
        <span class="metrics-detail-value">${formatCurrency(details.total_volume_processed || 0)}</span>
      </div>
      <div class="metrics-detail-item">
        <span class="metrics-detail-label">Projected Monthly</span>
        <span class="metrics-detail-value">${formatCurrency(details.projected_monthly || 0)}</span>
      </div>
    `;
  }

  container.innerHTML = html;
}

function showMetricsError(message) {
  const chartContainer = document.querySelector('.metrics-chart-container');
  chartContainer.innerHTML = `
    <div class="metrics-no-data">
      <i class="fa-solid fa-circle-exclamation"></i>
      <h4>Unable to Load Data</h4>
      <p>${message}</p>
    </div>
  `;
}

// Helper functions for formatting
function formatCurrency(value) {
  if (value === null || value === undefined) return '$0';
  return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function formatCompactCurrency(value) {
  if (value >= 1000000) {
    return '$' + (value / 1000000).toFixed(1) + 'M';
  } else if (value >= 1000) {
    return '$' + (value / 1000).toFixed(1) + 'K';
  }
  return '$' + value.toLocaleString();
}

function formatCompactNumber(value) {
  if (value >= 1000000) {
    return (value / 1000000).toFixed(1) + 'M';
  } else if (value >= 1000) {
    return (value / 1000).toFixed(1) + 'K';
  }
  return value.toLocaleString();
}

function formatChartDate(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr + 'T00:00:00');
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// Export metrics modal functions
window.openMetricsModal = openMetricsModal;
window.closeMetricsModal = closeMetricsModal;
window.changeMetricsRange = changeMetricsRange;
