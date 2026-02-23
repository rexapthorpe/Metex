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
