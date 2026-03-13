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
const INITIAL_LIMIT = 10;    // Notifications shown on initial sidebar open

// Sidebar state
let sidebarNotifications = [];  // All notifications currently displayed in sidebar
let allLoaded = false;          // Whether all notifications have been fetched
let sidebarLoading = false;     // Prevent concurrent "load more" requests

// Toast state
let lastSeenNotifId = null;
let hasInitializedToasts = false;

// ===================================
// NOTIFICATION TYPE → ICON/COLOR MAP
// ===================================

const NOTIF_ICON_MAP = {
    // ── Legacy ──────────────────────────────────────────────────────────
    'bid_filled':                           { icon: 'fa-dollar-sign',    bg: '#f3e8ff', color: '#9333ea' },
    'new_bid':                              { icon: 'fa-dollar-sign',    bg: '#f3e8ff', color: '#9333ea' },
    'bid_received':                         { icon: 'fa-dollar-sign',    bg: '#f3e8ff', color: '#9333ea' },
    'order_confirmed':                      { icon: 'fa-cube',           bg: '#dbeafe', color: '#6366f1' },
    'order_shipped':                        { icon: 'fa-truck',          bg: '#dbeafe', color: '#2563eb' },
    'order_delivered':                      { icon: 'fa-cube',           bg: '#e0e7ff', color: '#818cf8' },
    'listing_sold':                         { icon: 'fa-tag',            bg: '#dbeafe', color: '#2563eb' },
    'new_message':                          { icon: 'fa-comment',        bg: '#dcfce7', color: '#22c55e' },
    'message':                              { icon: 'fa-comment',        bg: '#dcfce7', color: '#22c55e' },
    'new_review':                           { icon: 'fa-star',           bg: '#fef9c3', color: '#ca8a04' },
    'rating':                               { icon: 'fa-star',           bg: '#fef9c3', color: '#ca8a04' },
    'review':                               { icon: 'fa-star',           bg: '#fef9c3', color: '#ca8a04' },
    // ── Listings ────────────────────────────────────────────────────────
    'listing_created_success':              { icon: 'fa-tag',            bg: '#dcfce7', color: '#16a34a' },
    'listing_edited':                       { icon: 'fa-pen',            bg: '#f3f4f6', color: '#6b7280' },
    'listing_delisted':                     { icon: 'fa-ban',            bg: '#fee2e2', color: '#ef4444' },
    'listing_expired':                      { icon: 'fa-clock',          bg: '#fff7ed', color: '#f59e0b' },
    // ── Bids ────────────────────────────────────────────────────────────
    'bid_placed_success':                   { icon: 'fa-gavel',          bg: '#f3e8ff', color: '#9333ea' },
    'bid_placed':                           { icon: 'fa-gavel',          bg: '#f3e8ff', color: '#9333ea' },
    'bid_on_bucket':                        { icon: 'fa-gavel',          bg: '#f3e8ff', color: '#9333ea' },
    'bid_fully_filled':                     { icon: 'fa-circle-check',   bg: '#dcfce7', color: '#16a34a' },
    'bid_partially_accepted':               { icon: 'fa-circle-half-stroke', bg: '#f0fdf4', color: '#22c55e' },
    'outbid':                               { icon: 'fa-arrow-up',       bg: '#fff7ed', color: '#f59e0b' },
    'bid_withdrawn':                        { icon: 'fa-minus-circle',   bg: '#f3f4f6', color: '#9ca3af' },
    'bid_now_leading':                      { icon: 'fa-trophy',         bg: '#fef9c3', color: '#ca8a04' },
    'bid_rejected_or_expired':              { icon: 'fa-clock',          bg: '#fee2e2', color: '#ef4444' },
    // ── Orders (buyer) ──────────────────────────────────────────────────
    'order_created':                        { icon: 'fa-cube',           bg: '#dbeafe', color: '#6366f1' },
    'order_status_updated':                 { icon: 'fa-rotate',         bg: '#dbeafe', color: '#3b82f6' },
    'tracking_updated':                     { icon: 'fa-truck',          bg: '#dbeafe', color: '#2563eb' },
    'delivered_confirmed':                  { icon: 'fa-circle-check',   bg: '#dcfce7', color: '#16a34a' },
    'cancellation_requested':               { icon: 'fa-circle-xmark',   bg: '#fff7ed', color: '#f59e0b' },
    'cancellation_denied':                  { icon: 'fa-ban',            bg: '#fee2e2', color: '#ef4444' },
    'cancellation_approved':                { icon: 'fa-circle-check',   bg: '#dcfce7', color: '#16a34a' },
    'cancel_request_submitted':             { icon: 'fa-circle-xmark',   bg: '#fff7ed', color: '#f59e0b' },
    'cancellation_request':                 { icon: 'fa-circle-xmark',   bg: '#fff7ed', color: '#f59e0b' },
    // ── Sales (seller) ──────────────────────────────────────────────────
    'seller_order_received':                { icon: 'fa-store',          bg: '#dbeafe', color: '#2563eb' },
    'seller_fulfillment_needed':            { icon: 'fa-truck',          bg: '#fff7ed', color: '#f59e0b' },
    'seller_cancellation_request_received': { icon: 'fa-circle-xmark',   bg: '#fee2e2', color: '#ef4444' },
    'seller_cancellation_finalized':        { icon: 'fa-circle-check',   bg: '#dcfce7', color: '#16a34a' },
    // ── Messages ────────────────────────────────────────────────────────
    'new_order_message':                    { icon: 'fa-comment',        bg: '#dcfce7', color: '#22c55e' },
    'new_direct_message':                   { icon: 'fa-comment-dots',   bg: '#dcfce7', color: '#16a34a' },
    // ── Ratings ─────────────────────────────────────────────────────────
    'rating_received':                      { icon: 'fa-star',           bg: '#fef9c3', color: '#ca8a04' },
    'rating_submitted':                     { icon: 'fa-star',           bg: '#f0fdf4', color: '#22c55e' },
    'rating_to_leave_reminder':             { icon: 'fa-star-half',      bg: '#fef9c3', color: '#ca8a04' },
    // ── Account / Security ──────────────────────────────────────────────
    'new_login':                            { icon: 'fa-shield-halved',  bg: '#fff7ed', color: '#f59e0b' },
    'password_changed':                     { icon: 'fa-lock',           bg: '#fee2e2', color: '#ef4444' },
    'email_changed':                        { icon: 'fa-envelope',       bg: '#dbeafe', color: '#3b82f6' },
    // ── Reports ─────────────────────────────────────────────────────────
    'report_submitted':                     { icon: 'fa-flag',           bg: '#fff7ed', color: '#f59e0b' },
};

function getNotifIcon(type) {
    return NOTIF_ICON_MAP[type] || { icon: 'fa-bell', bg: '#f3f4f6', color: '#9ca3af' };
}

// ===================================
// TARGET URL PER TYPE
// ===================================

function getTargetUrl(type) {
    const ORDERS_TYPES = new Set([
        'bid_filled','new_bid','order_confirmed','order_created','order_status_updated',
        'order_shipped','tracking_updated','delivered_confirmed',
        'cancellation_requested','cancellation_denied','cancellation_approved',
        'cancel_request_submitted','cancellation_request',
        'bid_fully_filled','bid_partially_accepted',
    ]);
    const BIDS_TYPES = new Set([
        'bid_placed','bid_placed_success','bid_received','bid_on_bucket',
        'bid_withdrawn','bid_rejected_or_expired','outbid','bid_now_leading',
    ]);
    const SOLD_TYPES = new Set([
        'listing_sold','seller_order_received','seller_fulfillment_needed',
        'seller_cancellation_request_received','seller_cancellation_finalized',
    ]);
    const LISTINGS_TYPES = new Set([
        'listing_created_success','listing_edited','listing_delisted','listing_expired',
    ]);
    const MSG_TYPES = new Set(['new_message','message','new_order_message','new_direct_message']);
    const RATING_TYPES = new Set(['new_review','rating','review','rating_received','rating_submitted','rating_to_leave_reminder']);
    const ACCOUNT_TYPES = new Set(['new_login','password_changed','email_changed','report_submitted']);

    if (ORDERS_TYPES.has(type)) return '/account#orders';
    if (BIDS_TYPES.has(type))   return '/account#bids';
    if (SOLD_TYPES.has(type))   return '/account#sold';
    if (LISTINGS_TYPES.has(type)) return '/account#listings';
    if (MSG_TYPES.has(type))    return '/account#messages';
    if (RATING_TYPES.has(type)) return '/account#ratings';
    if (ACCOUNT_TYPES.has(type)) return '/account#details';
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
        loadNotifications(); // always poll — detects new notifications for toasts
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
    sidebarNotifications = [];
    allLoaded = false;
    loadSidebarInitial();
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
    fetch(`/notifications?limit=${INITIAL_LIMIT}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                notifications = data.notifications || [];
                checkAndShowToasts();
            } else {
                console.error('[Notifications] Failed to load:', data.error);
            }
        })
        .catch(error => console.error('[Notifications] Fetch error:', error));
}

// ===================================
// SIDEBAR LOAD (INITIAL + MORE)
// ===================================

function loadSidebarInitial() {
    notificationList.innerHTML = `
        <div class="notification-loading">Loading notifications...</div>
    `;
    fetch(`/notifications?limit=${INITIAL_LIMIT}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                notifications = data.notifications || [];
                sidebarNotifications = data.notifications || [];
                allLoaded = sidebarNotifications.length < INITIAL_LIMIT;
                try {
                    renderNotifications();
                } catch (renderErr) {
                    console.error('[Notifications] renderNotifications error:', renderErr);
                    notificationList.innerHTML = `
                        <div class="notification-empty">
                            <i class="fa-solid fa-exclamation-triangle"></i>
                            <p>Failed to display notifications</p>
                        </div>
                    `;
                }
                updateNewBadge();
                updateViewAllBtn();
            } else {
                console.error('[Notifications] Server error:', data.error);
                notificationList.innerHTML = `
                    <div class="notification-empty">
                        <i class="fa-solid fa-exclamation-triangle"></i>
                        <p>Failed to load notifications</p>
                    </div>
                `;
            }
        })
        .catch(err => {
            console.error('[Notifications] Fetch error:', err);
            notificationList.innerHTML = `
                <div class="notification-empty">
                    <i class="fa-solid fa-exclamation-triangle"></i>
                    <p>Failed to load notifications</p>
                </div>
            `;
        });
}

function loadMoreNotifications() {
    if (allLoaded || sidebarLoading) return;
    sidebarLoading = true;
    const btn = document.getElementById('notifViewAllBtn');
    if (btn) btn.textContent = 'Loading...';

    fetch(`/notifications?offset=${INITIAL_LIMIT}&limit=9999`)
        .then(response => response.json())
        .then(data => {
            sidebarLoading = false;
            if (data.success) {
                const newNotifs = data.notifications;
                sidebarNotifications = [...sidebarNotifications, ...newNotifs];
                allLoaded = true;
                newNotifs.forEach(notification => {
                    const tile = createNotificationTile(notification);
                    notificationList.appendChild(tile);
                });
                updateViewAllBtn();
            } else {
                if (btn) btn.textContent = 'View All Notifications';
            }
        })
        .catch(() => {
            sidebarLoading = false;
            if (btn) btn.textContent = 'View All Notifications';
        });
}

function updateViewAllBtn() {
    const footer = document.getElementById('notifFooter');
    if (!footer) return;
    footer.style.display = allLoaded ? 'none' : '';
}

// ===================================
// TOAST DETECTION & DISPLAY
// ===================================

function checkAndShowToasts() {
    if (!hasInitializedToasts) {
        // First load: record the current highest ID so we only toast future arrivals
        if (notifications.length > 0) {
            lastSeenNotifId = Math.max(...notifications.map(n => n.id));
        }
        hasInitializedToasts = true;
        return;
    }

    // Find notifications newer than what we've seen
    const newNotifs = notifications.filter(n => n.id > (lastSeenNotifId || 0));

    // Advance the watermark
    if (notifications.length > 0) {
        lastSeenNotifId = Math.max(...notifications.map(n => n.id));
    }

    // Show toasts (cap at 3 to avoid overwhelming the screen)
    newNotifs.slice(0, 3).forEach((notif, index) => {
        setTimeout(() => showNotifToast(notif), index * 200);
    });
}

function showNotifToast(notification) {
    const container = document.getElementById('notif-toast-container');
    if (!container) return;

    const { icon, bg, color } = getNotifIcon(notification.type);
    const targetUrl = getTargetUrl(notification.type);

    const toast = document.createElement('div');
    toast.className = 'notif-toast';
    toast.innerHTML = `
        <div class="notif-icon-circle" style="background:${bg}; color:${color}">
            <i class="fa-solid ${icon}"></i>
        </div>
        <div class="notif-toast-body">
            <div class="notif-toast-title">${escapeHtml(notification.title)}</div>
            <div class="notif-toast-message">${escapeHtml(notification.message)}</div>
        </div>
        <button class="notif-toast-close" aria-label="Dismiss">
            <i class="fa-solid fa-xmark"></i>
        </button>
    `;

    let dismissed = false;

    function dismissToast() {
        if (dismissed) return;
        dismissed = true;
        toast.classList.add('hide');
        setTimeout(() => {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 320);
    }

    // Click body → navigate
    toast.addEventListener('click', (e) => {
        if (e.target.closest('.notif-toast-close')) return;
        dismissToast();
        window.location.href = targetUrl;
    });

    // X button → dismiss only
    toast.querySelector('.notif-toast-close').addEventListener('click', (e) => {
        e.stopPropagation();
        dismissToast();
    });

    container.appendChild(toast);

    // CSS @keyframes on .notif-toast fires automatically on DOM insertion.
    // Auto-dismiss after 3 seconds
    setTimeout(dismissToast, 3000);
}

// ===================================
// RENDER NOTIFICATIONS
// ===================================

function renderNotifications() {
    notificationList.innerHTML = '';

    if (sidebarNotifications.length === 0) {
        notificationList.innerHTML = `
            <div class="notification-empty">
                <i class="fa-regular fa-bell-slash"></i>
                <p>No notifications yet</p>
            </div>
        `;
        return;
    }

    sidebarNotifications.forEach(notification => {
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
                sidebarNotifications = [];
                allLoaded = false;
                loadSidebarInitial();
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
    const unreadCount = sidebarNotifications.filter(n => !n.is_read).length;
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
