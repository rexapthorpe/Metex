/**
 * Notification System JavaScript
 * Handles notification bell, sidebar, and all interactions
 */

// ===================================
// STATE & CONFIGURATION
// ===================================

let notifications = [];
let isNotificationSidebarOpen = false;
const POLL_INTERVAL = 30000; // Poll every 30 seconds

// ===================================
// NOTIFICATION TYPE → ICON/COLOR MAP
// ===================================

const NOTIF_ICON_MAP = {
    'bid_filled':       { icon: 'fa-dollar-sign',  bg: '#f3e8ff', color: '#9333ea' },
    'new_bid':          { icon: 'fa-dollar-sign',  bg: '#f3e8ff', color: '#9333ea' },
    'bid_received':     { icon: 'fa-dollar-sign',  bg: '#f3e8ff', color: '#9333ea' },
    'order_confirmed':  { icon: 'fa-cube',          bg: '#dbeafe', color: '#6366f1' },
    'order_shipped':    { icon: 'fa-cube',          bg: '#dbeafe', color: '#6366f1' },
    'order_delivered':  { icon: 'fa-cube',          bg: '#e0e7ff', color: '#818cf8' },
    'listing_sold':     { icon: 'fa-tag',           bg: '#dbeafe', color: '#2563eb' },
    'new_message':      { icon: 'fa-comment',       bg: '#dcfce7', color: '#22c55e' },
    'message':          { icon: 'fa-comment',       bg: '#dcfce7', color: '#22c55e' },
    'new_review':       { icon: 'fa-star',          bg: '#fef9c3', color: '#ca8a04' },
    'rating':           { icon: 'fa-star',          bg: '#fef9c3', color: '#ca8a04' },
    'review':           { icon: 'fa-star',          bg: '#fef9c3', color: '#ca8a04' },
};

function getNotifIcon(type) {
    return NOTIF_ICON_MAP[type] || { icon: 'fa-bell', bg: '#f3f4f6', color: '#9ca3af' };
}

// ===================================
// TARGET URL PER TYPE
// ===================================

function getTargetUrl(type) {
    if (type === 'bid_filled' || type === 'new_bid' || type === 'bid_received') return '/account#orders';
    if (type === 'order_confirmed' || type === 'order_shipped' || type === 'order_delivered') return '/account#orders';
    if (type === 'listing_sold') return '/account#sold';
    if (type === 'new_message' || type === 'message') return '/account#messages';
    if (type === 'new_review' || type === 'rating' || type === 'review') return '/account#ratings';
    return '/account';
}

// ===================================
// DOM ELEMENTS
// ===================================

const bellBtn = document.getElementById('notificationBellBtn');
const badge = document.getElementById('notificationBadge');
const notifNewBadge = document.getElementById('notifNewBadge');
const sidebar = document.getElementById('notificationSidebar');
const overlay = document.getElementById('notificationOverlay');
const closeBtn = document.getElementById('notificationCloseBtn');
const notificationList = document.getElementById('notificationList');
const markAllBtn = document.getElementById('notifMarkAllBtn');

// ===================================
// INITIALIZATION
// ===================================

document.addEventListener('DOMContentLoaded', () => {
    loadNotifications();
    updateBadgeCount();

    if (bellBtn) bellBtn.addEventListener('click', toggleNotificationSidebar);
    if (closeBtn) closeBtn.addEventListener('click', closeNotificationSidebar);
    if (overlay) overlay.addEventListener('click', closeNotificationSidebar);
    if (markAllBtn) markAllBtn.addEventListener('click', handleMarkAllRead);

    setInterval(() => {
        updateBadgeCount();
        if (isNotificationSidebarOpen) loadNotifications();
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
    loadNotifications();
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
                updateNewBadge();
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
    notificationList.innerHTML = '';

    if (notifications.length === 0) {
        notificationList.innerHTML = `
            <div class="notification-empty">
                <i class="fa-regular fa-bell-slash"></i>
                <p>No notifications yet</p>
            </div>
        `;
        return;
    }

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

    const { icon, bg, color } = getNotifIcon(notification.type);
    const timeAgo = getTimeAgo(notification.created_at);
    const unreadDot = notification.is_read ? '' : '<div class="notif-unread-dot"></div>';

    tile.innerHTML = `
        <div class="notif-icon-circle" style="background:${bg}; color:${color}">
            <i class="fa-solid ${icon}"></i>
        </div>
        <div class="notif-body">
            <div class="notification-title">${escapeHtml(notification.title)}</div>
            <div class="notification-message">${escapeHtml(notification.message)}</div>
            <div class="notification-time">${timeAgo}</div>
        </div>
        ${unreadDot}
    `;

    // Click the whole tile to navigate (and mark as read)
    tile.addEventListener('click', () => {
        const targetUrl = getTargetUrl(notification.type);
        handleTileClick(notification.id, targetUrl, tile);
    });

    return tile;
}

// ===================================
// TILE CLICK — MARK READ + NAVIGATE
// ===================================

function handleTileClick(notificationId, targetUrl, tileEl) {
    if (!notifications.find(n => n.id === notificationId)?.is_read) {
        fetch(`/notifications/${notificationId}/read`, { method: 'POST' })
            .then(() => { updateBadgeCount(); })
            .catch(() => {});
    }
    window.location.href = targetUrl;
}

// ===================================
// MARK ALL AS READ
// ===================================

function handleMarkAllRead() {
    fetch('/notifications/mark-all-read', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                loadNotifications();
                updateBadgeCount();
            }
        })
        .catch(error => console.error('Error marking all as read:', error));
}

// ===================================
// UPDATE BADGE COUNT (bell icon)
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
        .catch(error => console.error('Error updating badge count:', error));
}

// Update the "N new" pill in the sidebar header
function updateNewBadge() {
    const unreadCount = notifications.filter(n => !n.is_read).length;
    if (notifNewBadge) {
        if (unreadCount > 0) {
            notifNewBadge.textContent = `${unreadCount} new`;
            notifNewBadge.style.display = '';
        } else {
            notifNewBadge.style.display = 'none';
        }
    }
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

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
    if (diffDays < 7) return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
    return notifTime.toLocaleDateString();
}

// ===================================
// GLOBAL REFRESH FUNCTION
// ===================================

window.refreshNotifications = function() {
    loadNotifications();
    updateBadgeCount();
};
