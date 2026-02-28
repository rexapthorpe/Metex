# Notification System

## Overview

Metex's in-app notification system delivers real-time alerts to buyers, sellers, and account holders. Every notification type can be independently toggled per user via the **Account Details → Notification Settings** page.

---

## How Settings Are Stored

| Table | Purpose |
|---|---|
| `notification_settings` | Key-value rows `(user_id, notification_type, enabled)`. Created by migration 025. |
| `NOTIFICATION_DEFAULTS` | Python dict in `services/notification_service.py` — defines the default ON/OFF for each type. Used as fallback when no row exists for a user+type pair. |

### Settings API

| Endpoint | Method | Description |
|---|---|---|
| `/notifications/settings` | `GET` | Returns `{type: bool}` for the current user (merged defaults + overrides) |
| `/notifications/settings` | `POST` | Updates one or more toggles. Accepts JSON `{type: bool}` or form-encoded. |

Settings UI: **Account → Account Details → Notification Settings**. Each toggle auto-saves via `fetch` on change.

---

## Notification Types

### A. Listings

| Type | Default | Where Triggered | File |
|---|---|---|---|
| `listing_created_success` | ✅ ON | After listing is created | `core/blueprints/sell/listing_creation.py` |
| `listing_edited` | ❌ OFF | After listing is edited | `core/blueprints/listings/routes.py` |
| `listing_delisted` | ✅ ON | After listing is cancelled/removed | `core/blueprints/listings/routes.py` |
| `listing_expired` | ✅ ON | Stub — no expiration system yet | `services/notification_types.py` |

### B. Bids

| Type | Default | Where Triggered | File |
|---|---|---|---|
| `bid_placed_success` | ✅ ON | After bid is submitted | `core/blueprints/bids/place_bid.py` |
| `bid_received` | ✅ ON | Seller notified of new bid | `core/blueprints/bids/place_bid.py` |
| `bid_fully_filled` | ✅ ON | Buyer's bid fully filled | `services/notification_types.py` (via `notify_bid_accepted`) |
| `bid_partially_accepted` | ✅ ON | Buyer's bid partially filled | `services/notification_types.py` (via `notify_bid_accepted`) |
| `outbid` | ✅ ON | Another buyer places higher bid | `services/notification_types.py` |
| `bid_withdrawn` | ✅ ON | Bidder withdraws their bid | `services/notification_types.py` |
| `bid_rejected_or_expired` | ✅ ON | Bid expires without filling | `services/notification_types.py` |
| `bid_now_leading` | ❌ OFF | Bid becomes current best | `services/notification_types.py` |
| `bid_filled` (legacy) | ✅ ON | Alias — bid filled (old callers) | `services/notification_types.py` |
| `bid_on_bucket` (legacy) | ✅ ON | Alias — bid on seller's bucket | `core/blueprints/bids/place_bid.py` |

### C. Orders (buyer)

| Type | Default | Where Triggered | File |
|---|---|---|---|
| `order_created` | ✅ ON | After order is placed | `services/notification_types.py` |
| `order_confirmed` (legacy) | ✅ ON | Alias — order confirmed | `core/blueprints/checkout/routes.py`, `direct_purchase.py` |
| `order_status_updated` | ✅ ON | Order status changes | `services/notification_types.py` |
| `order_shipped` | ✅ ON | Seller adds tracking number | `services/notification_types.py` |
| `tracking_updated` | ❌ OFF | Tracking number changes | `services/notification_types.py` |
| `delivered_confirmed` | ✅ ON | Order marked delivered | `services/notification_types.py` |
| `cancellation_requested` | ✅ ON | Buyer submits cancel request | `routes/cancellation_routes.py` |
| `cancellation_denied` | ✅ ON | Any seller denies cancellation | `routes/cancellation_routes.py` |
| `cancellation_approved` | ✅ ON | All sellers approve cancellation | `routes/cancellation_routes.py` |
| `cancel_request_submitted` (legacy) | ✅ ON | Alias — cancel request submitted | `routes/cancellation_routes.py` |
| `payment_succeeded` | ❌ OFF | Stub — no payment system yet | — |
| `payment_failed` | ❌ OFF | Stub | — |
| `refund_issued` | ❌ OFF | Stub | — |

### D. Sales (seller)

| Type | Default | Where Triggered | File |
|---|---|---|---|
| `seller_order_received` | ✅ ON | Seller gets a new order | `services/notification_types.py` |
| `listing_sold` (legacy) | ✅ ON | Alias — listing sold | `core/blueprints/buy/direct_purchase.py`, `checkout/routes.py` |
| `seller_cancellation_request_received` | ✅ ON | Buyer requests cancellation | `routes/cancellation_routes.py` |
| `seller_cancellation_finalized` | ✅ ON | Cancellation is approved or denied | `routes/cancellation_routes.py` |
| `seller_fulfillment_needed` | ❌ OFF | Periodic reminder to ship | — |
| `payout_available` | ❌ OFF | Stub | — |

### E. Messages

| Type | Default | Where Triggered | File |
|---|---|---|---|
| `new_order_message` | ✅ ON | Message about an existing order | `core/blueprints/messages/routes.py` |
| `new_direct_message` | ✅ ON | Direct message (no order) | `core/blueprints/messages/routes.py` |
| `new_message` (legacy) | ✅ ON | Alias | `core/blueprints/messages/routes.py` |

### F. Ratings

| Type | Default | Where Triggered | File |
|---|---|---|---|
| `rating_received` | ✅ ON | User receives a rating | `core/blueprints/ratings/routes.py` |
| `rating_submitted` | ✅ ON | Confirmation: rating submitted | `core/blueprints/ratings/routes.py` |
| `rating_to_leave_reminder` | ❌ OFF | Periodic reminder | — |

### G. Account / Security

| Type | Default | Where Triggered | File |
|---|---|---|---|
| `new_login` | ✅ ON | Each new successful login | `routes/auth_routes.py` |
| `password_changed` | ✅ ON | Password updated | `routes/account_routes.py` |
| `email_changed` | ✅ ON | Email address updated | `routes/account_routes.py` |

### H. Watchlist / Alerts (stubs — OFF by default)

| Type | Default | Notes |
|---|---|---|
| `price_alert_triggered` | ❌ OFF | Future |
| `availability_alert_triggered` | ❌ OFF | Future |
| `saved_search_match` | ❌ OFF | Future |

---

## Central Emission API

```python
from services.notification_service import notify

notify(
    user_id=123,
    notification_type='order_created',
    title='Order Placed',
    body='Your order for 1 oz Gold Eagle was placed.',
    related_order_id=456,
    metadata={'quantity': 2},
)
```

`notify()` calls `is_notification_enabled(user_id, type)` before inserting. If the user has disabled the type (or the default is OFF and no override exists), it returns `None` without creating a row.

All existing `notify_*` helpers in `services/notification_types.py` route through `notify()` automatically.

---

## Multi-Seller Order Rules

1. When an order contains multiple sellers, call `notify_seller_order_received()` (or the legacy `notify_listing_sold()`) once per seller for their portion.
2. The buyer receives exactly one `order_created` notification regardless of how many sellers are involved.
3. Cancellation: `notify_cancellation_requested_seller()` is called for every seller. When the result is final:
   - **Any denial** → `notify_cancellation_denied()` to buyer + `notify_seller_cancellation_finalized(approved=False)` to all sellers.
   - **All approve** → `notify_cancellation_approved()` to buyer + `notify_seller_cancellation_finalized(approved=True)` to all sellers.

---

## Running Tests

```bash
# Run only notification tests
python -m pytest tests/test_notifications.py -v

# Run all tests
python -m pytest tests/ -v
```

### Test Coverage

| # | Scenario | Class |
|---|---|---|
| 1 | `listing_created_success` fires; toggle OFF suppresses | `TestListingCreated` |
| 2 | `bid_placed_success` to bidder; `bid_received` to seller; toggles suppress | `TestBidPlaced` |
| 3 | Full fill → `bid_fully_filled`; partial → `bid_partially_accepted` | `TestBidAccepted` |
| 4 | `outbid` fires; suppressed when toggled off | `TestOutbid` |
| 5 | Multi-seller: each seller gets `seller_order_received`; buyer gets one `order_created` | `TestMultiSellerOrder` |
| 6 | Cancellation multi-seller: request / deny / approve flows | `TestCancellationMultiSeller` |
| 7 | `new_order_message` fires; `new_direct_message` when no order; toggle suppress | `TestMessaging` |
| 8 | `mark_notification_read`, `mark_all_notifications_read`, cross-user isolation | `TestMarkRead` |
| 9 | HTTP endpoints: GET/POST settings, unread-count, mark-all-read | `TestNotificationEndpoints` |
| 10 | `notify()`, `is_notification_enabled()`, `get_user_notification_settings()` unit tests | `TestNotifyAndSettings` |
