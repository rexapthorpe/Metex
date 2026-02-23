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
