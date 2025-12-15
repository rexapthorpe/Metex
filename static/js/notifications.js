/**
 * Notification System JavaScript
 * Handles notification bell, sidebar, and all interactions
 */

// ===================================
// STATE & CONFIGURATION
// ===================================

let notifications = [];
let isNotificationSidebarOpen = false;
const POLL_INTERVAL = 30000; // Poll every 30 seconds for new notifications

// ===================================
// DOM ELEMENTS
// ===================================

const bellBtn = document.getElementById('notificationBellBtn');
const badge = document.getElementById('notificationBadge');
const sidebar = document.getElementById('notificationSidebar');
const overlay = document.getElementById('notificationOverlay');
const closeBtn = document.getElementById('notificationCloseBtn');
const notificationList = document.getElementById('notificationList');

// ===================================
// INITIALIZATION
// ===================================

document.addEventListener('DOMContentLoaded', () => {
    // Initial load
    loadNotifications();
    updateBadgeCount();

    // Set up event listeners
    if (bellBtn) {
        bellBtn.addEventListener('click', toggleNotificationSidebar);
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', closeNotificationSidebar);
    }

    if (overlay) {
        overlay.addEventListener('click', closeNotificationSidebar);
    }

    // Poll for new notifications
    setInterval(() => {
        updateBadgeCount();
        if (isNotificationSidebarOpen) {
            loadNotifications();
        }
    }, POLL_INTERVAL);
});

// ===================================
// SIDEBAR OPEN/CLOSE
// ===================================

function toggleNotificationSidebar() {
    if (isNotificationSidebarOpen) {
        closeNotificationSidebar();
    } else {
        openNotificationSidebar();
    }
}

function openNotificationSidebar() {
    isNotificationSidebarOpen = true;
    sidebar.classList.add('open');
    overlay.classList.add('show');
    loadNotifications(); // Refresh notifications when opening
}

function closeNotificationSidebar() {
    isNotificationSidebarOpen = false;
    sidebar.classList.remove('open');
    overlay.classList.remove('show');
}

// ===================================
// LOAD NOTIFICATIONS
// ===================================

function loadNotifications() {
    fetch('/notifications')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                notifications = data.notifications;
                renderNotifications();
            } else {
                console.error('Failed to load notifications:', data.error);
            }
        })
        .catch(error => {
            console.error('Error loading notifications:', error);
            notificationList.innerHTML = `
                <div class="notification-empty">
                    <i class="fa-solid fa-exclamation-triangle"></i>
                    <p>Failed to load notifications</p>
                </div>
            `;
        });
}

// ===================================
// RENDER NOTIFICATIONS
// ===================================

function renderNotifications() {
    // Clear loading state
    notificationList.innerHTML = '';

    // Check if empty
    if (notifications.length === 0) {
        notificationList.innerHTML = `
            <div class="notification-empty">
                <i class="fa-solid fa-bell-slash"></i>
                <p>No notifications yet</p>
            </div>
        `;
        return;
    }

    // Render each notification
    notifications.forEach(notification => {
        const tile = createNotificationTile(notification);
        notificationList.appendChild(tile);
    });
}

// ===================================
// CREATE NOTIFICATION TILE
// ===================================

function createNotificationTile(notification) {
    const tile = document.createElement('div');
    tile.className = 'notification-tile' + (notification.is_read ? '' : ' unread');
    tile.setAttribute('data-notification-id', notification.id);
    tile.setAttribute('data-type', notification.type);

    // Unread dot (only if unread)
    const unreadDot = notification.is_read ? '' : '<div class="notification-unread-dot"></div>';

    // Determine button text and link based on type
    let buttonText = 'View';
    let targetUrl = '/account';

    if (notification.type === 'bid_filled') {
        buttonText = 'View Order';
        targetUrl = '/account#orders';
    } else if (notification.type === 'order_confirmed') {
        buttonText = 'View Order';
        targetUrl = '/account#orders';
    } else if (notification.type === 'listing_sold') {
        buttonText = 'View Sold';
        targetUrl = '/account#sold';
    }

    // Format timestamp
    const timeAgo = getTimeAgo(notification.created_at);

    tile.innerHTML = `
        ${unreadDot}
        <div class="notification-content">
            <h4 class="notification-title">${escapeHtml(notification.title)}</h4>
            <p class="notification-message">${escapeHtml(notification.message)}</p>
            <p class="notification-time">${timeAgo}</p>
        </div>
        <div class="notification-actions">
            <button class="notification-delete-btn" data-notification-id="${notification.id}">
                <i class="fa-solid fa-trash"></i>
            </button>
            <button class="notification-goto-btn" data-notification-id="${notification.id}" data-url="${targetUrl}">
                ${buttonText}
            </button>
        </div>
    `;

    // Add event listeners
    const deleteBtn = tile.querySelector('.notification-delete-btn');
    const gotoBtn = tile.querySelector('.notification-goto-btn');

    deleteBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteNotification(notification.id, tile);
    });

    gotoBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        handleGotoClick(notification.id, targetUrl);
    });

    return tile;
}

// ===================================
// UPDATE BADGE COUNT
// ===================================

function updateBadgeCount() {
    fetch('/notifications/unread-count')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const count = data.count;
                if (count > 0) {
                    badge.textContent = count > 99 ? '99+' : count;
                    badge.style.display = 'flex';
                } else {
                    badge.style.display = 'none';
                }
            }
        })
        .catch(error => {
            console.error('Error updating badge count:', error);
        });
}

// ===================================
// DELETE NOTIFICATION
// ===================================

function deleteNotification(notificationId, tileElement) {
    // Add deleting class for animation
    tileElement.classList.add('deleting');

    // Wait for animation to complete, then remove from DOM and update server
    setTimeout(() => {
        fetch(`/notifications/${notificationId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Remove from local state
                notifications = notifications.filter(n => n.id !== notificationId);

                // Remove from DOM
                tileElement.remove();

                // Update badge
                updateBadgeCount();

                // Check if list is now empty
                if (notifications.length === 0) {
                    renderNotifications();
                }
            } else {
                console.error('Failed to delete notification:', data.error);
                // Remove animation class if failed
                tileElement.classList.remove('deleting');
            }
        })
        .catch(error => {
            console.error('Error deleting notification:', error);
            tileElement.classList.remove('deleting');
        });
    }, 300); // Match CSS transition duration
}

// ===================================
// HANDLE "GO TO" BUTTON CLICK
// ===================================

function handleGotoClick(notificationId, targetUrl) {
    // Mark as read
    fetch(`/notifications/${notificationId}/read`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update local state
            const notification = notifications.find(n => n.id === notificationId);
            if (notification) {
                notification.is_read = 1;
            }

            // Update badge
            updateBadgeCount();

            // Navigate to target URL
            window.location.href = targetUrl;
        }
    })
    .catch(error => {
        console.error('Error marking notification as read:', error);
        // Still navigate even if marking as read failed
        window.location.href = targetUrl;
    });
}

// ===================================
// UTILITY FUNCTIONS
// ===================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getTimeAgo(timestamp) {
    const now = new Date();
    const notifTime = new Date(timestamp);
    const diffMs = now - notifTime;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) {
        return 'Just now';
    } else if (diffMins < 60) {
        return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
    } else if (diffHours < 24) {
        return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
    } else if (diffDays < 7) {
        return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
    } else {
        return notifTime.toLocaleDateString();
    }
}

// ===================================
// GLOBAL REFRESH FUNCTION
// (Can be called from other scripts)
// ===================================

window.refreshNotifications = function() {
    loadNotifications();
    updateBadgeCount();
};
