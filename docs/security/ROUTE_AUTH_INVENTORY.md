# Route Authorization Inventory

**Generated**: 2026-01-15
**Status**: Security Audit V4.1

This document provides a machine-checkable inventory of all routes that accept identifier parameters, their authorization guards, and security status.

## Quick Reference

| Symbol | Meaning |
|--------|---------|
| :white_check_mark: | Properly protected |
| :warning: | Implicit protection (SQL filter) |
| :x: | Missing or weak protection |
| :lock: | Admin-only route |

---

## Authorization Matrix by Resource Type

### Orders

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/orders/api/<order_id>/details` | GET | `_verify_order_access()` | 403 | :white_check_mark: |
| `/orders/api/<order_id>/order_sellers` | GET | `_verify_order_access()` | 403 | :white_check_mark: |
| `/orders/api/<order_id>/order_items` | GET | `_verify_order_access()` | 403 | :white_check_mark: |
| `/orders/api/<order_id>/message_sellers` | GET | `authorize_order_participant()` (buyer only) | 403 | :white_check_mark: |
| `/orders/api/<order_id>/message_buyers` | GET | `authorize_order_participant()` (seller only) | 403 | :white_check_mark: |
| `/orders/api/<order_id>/messages/<participant_id>` | GET, POST | `authorize_order_participant()` | 403 | :white_check_mark: |
| `/orders/api/<order_id>/messages/<participant_id>/read` | POST | `authorize_order_participant()` | 403 | :white_check_mark: |
| `/orders/api/<order_id>/pricing` | GET | `authorize_order_participant()` | 403 | :white_check_mark: |
| `/order/<order_id>` | GET | SQL: `buyer_id = ?` | 404 | :warning: |
| `/rate/<order_id>` | GET, POST | `authorize_order_participant()` | 403 | :white_check_mark: |
| `/checkout/confirm/<order_id>` | GET | Explicit `buyer_id` check | redirect | :white_check_mark: |

### Listings

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/listings/edit_listing/<listing_id>` | GET, POST | `authorize_listing_owner()` | 403 | :white_check_mark: |
| `/listings/cancel_listing/<listing_id>` | POST | SQL: `seller_id = ?` | flash + redirect | :warning: |
| `/listings/cancel_listing_confirmation_modal/<listing_id>` | GET | None (read-only) | 200 | :white_check_mark: |
| `/api/listings/<listing_id>/details` | GET | None (public) | 404 | :white_check_mark: |
| `/add_to_cart/<listing_id>` | POST | Session check | 401 | :white_check_mark: |

### Bids

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/bid/form/<bucket_id>` | GET | None (public form) | 200 | :white_check_mark: |
| `/bid/form/<bucket_id>/<bid_id>` | GET | None (reads public bid) | 200 | :warning: |
| `/bid/place_bid/<bucket_id>` | POST | Session + validation | 401/400 | :white_check_mark: |
| `/bid/create/<bucket_id>` | POST | Session + validation | 401/400 | :white_check_mark: |
| `/bid/edit_bid/<bid_id>` | GET | SQL: `buyer_id = ?` | redirect | :white_check_mark: |
| `/bid/edit_form/<bid_id>` | GET | SQL: `buyer_id = ?` | 404 | :white_check_mark: |
| `/bid/cancel/<bid_id>` | POST | `authorize_bid_participant()` | 403 | :white_check_mark: |
| `/bid/accept_bid/<bucket_id>` | POST | Session + seller verify | 401/403 | :white_check_mark: |
| `/api/bid/<bid_id>/bidder_info` | GET | Seller verification | 403 | :white_check_mark: |

### Messages (Admin Contact)

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/api/admin/messages` | GET | Session + server-selected admin | 401 | :lock: |
| `/api/admin/messages` | POST | Session + server-selected admin + rate limit | 401 | :lock: |
| `/api/admin/messages/read` | POST | Session + server-selected admin | 401 | :lock: |
| `/api/admin/participant` | GET | Session + server-selected admin | 401 | :lock: |

**Note**: Admin message routes no longer accept admin_id in URL. Admin identity is server-derived (primary admin auto-selected). Legacy routes with admin_id param still work but the param is ignored.

### Addresses

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/account/get_address/<address_id>` | GET | `authorize_address_owner()` | 403 | :white_check_mark: |
| `/account/edit_address/<address_id>` | POST | `authorize_address_owner()` | 403 | :white_check_mark: |
| `/account/delete_address/<address_id>` | POST | `authorize_address_owner()` | 403 | :white_check_mark: |

### Payment Methods

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/api/payment-methods/<method_id>` | DELETE | `authorize_payment_method_owner()` + SQL | 403 | :white_check_mark: |
| `/api/payment-methods/<method_id>/default` | POST | `authorize_payment_method_owner()` + SQL | 403 | :white_check_mark: |

### Notifications

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/notifications/<notification_id>/read` | POST | `authorize_notification_owner()` | 403 | :white_check_mark: |
| `/notifications/<notification_id>` | DELETE | `authorize_notification_owner()` | 403 | :white_check_mark: |

### Cart

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/remove_seller/<bucket_id>/<seller_id>` | POST | Session check | 401 | :white_check_mark: |
| `/remove_item/<listing_id>` | POST | Session check | 401 | :white_check_mark: |
| `/remove_bucket/<bucket_id>` | POST | Session check | 401 | :white_check_mark: |
| `/update_bucket_quantity/<category_id>` | POST | Session check | 401 | :white_check_mark: |
| `/api/bucket/<bucket_id>/cart_sellers` | GET | Session check | 401 | :white_check_mark: |
| `/api/bucket/<bucket_id>/price_breakdown` | GET | Session check | 401 | :white_check_mark: |

### Reports

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/api/reports/<report_id>` | GET | `authorize_report_owner()` | 403 | :white_check_mark: |
| `/api/reports/submit` | POST | Session + rate limit | 401 | :white_check_mark: |

### Portfolio

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/portfolio/exclude/<order_item_id>` | POST | Explicit buyer ownership check | 403 | :white_check_mark: |
| `/portfolio/include/<order_item_id>` | POST | Explicit buyer ownership check | 403 | :white_check_mark: |
| `/account/api/orders/<order_id>/portfolio/include` | POST | ownership check | 403 | :white_check_mark: |
| `/account/api/orders/<order_id>/delivery-address` | PUT | ownership check | 403 | :white_check_mark: |

### Buckets (Public)

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/bucket/<bucket_id>` | GET | None (public) | 404 | :white_check_mark: |
| `/bucket/<bucket_id>/availability_json` | GET | None (public) | 404 | :white_check_mark: |
| `/api/bucket/<bucket_id>/sellers` | GET | None (public) | 200 | :white_check_mark: |
| `/bucket/<bucket_id>/price-history` | GET | None (public) | 200 | :white_check_mark: |

### Purchase

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/purchase_from_bucket/<bucket_id>` | POST | Session check | 401 | :white_check_mark: |
| `/preview_buy/<bucket_id>` | POST | Session check | 401 | :white_check_mark: |
| `/direct_buy/<bucket_id>` | POST | Session check | 401 | :white_check_mark: |
| `/refresh_price_lock/<bucket_id>` | POST | Session check | 401 | :white_check_mark: |

### Cancellation

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/api/orders/<order_id>/cancellation/status` | GET | Participant verification | 403 | :white_check_mark: |
| `/api/orders/<order_id>/cancel` | POST | Buyer verification | 403 | :white_check_mark: |
| `/api/orders/<order_id>/cancel/respond` | POST | Seller verification | 403 | :white_check_mark: |
| `/api/seller/<seller_id>/cancellation-stats` | GET | Admin check | 403 | :white_check_mark: |

### Auth Tokens

| Route | Methods | Auth Guard | Return on Unauthorized | Status |
|-------|---------|------------|------------------------|--------|
| `/reset_password/<token>` | GET, POST | Token validation | redirect | :white_check_mark: |

---

## Admin Routes (All Protected by @admin_required)

All admin routes are protected by the `@admin_required` decorator which:
1. Checks `session['user_id']` exists
2. Verifies `users.is_admin = 1` in database
3. Returns 403 if either check fails

| Route | Methods | Resource |
|-------|---------|----------|
| `/admin/ledger/order/<order_id>` | GET | Order Details |
| `/admin/api/ledger/order/<order_id>` | GET | Order API |
| `/admin/api/ledger/order/<order_id>/events` | GET | Order Events |
| `/admin/api/user/<user_id>` | GET | User Details |
| `/admin/api/user/<user_id>/ban` | POST | User Ban |
| `/admin/api/user/<user_id>/freeze` | POST | User Freeze |
| `/admin/api/user/<user_id>/delete` | POST | User Delete |
| `/admin/api/user/<user_id>/message` | POST | Admin Message |
| `/admin/api/user/<user_id>/messages` | GET | Admin Conversation |
| `/admin/api/user/<user_id>/stats` | GET | User Stats |
| `/admin/api/order/<order_id>` | GET | Order Details |
| `/admin/api/orders/<order_id>/hold` | POST | Order Hold |
| `/admin/api/orders/<order_id>/approve` | POST | Order Approve |
| `/admin/api/orders/<order_id>/refund` | POST | Order Refund |
| `/admin/api/payouts/<payout_id>/hold` | POST | Payout Hold |
| `/admin/api/payouts/<payout_id>/release` | POST | Payout Release |
| `/admin/api/buckets/<bucket_id>` | GET | Bucket Details |
| `/admin/api/buckets/<bucket_id>/fee` | POST | Bucket Fee |
| `/admin/buckets/<bucket_id>` | GET | Bucket Page |
| `/admin/api/reports/<report_id>` | GET | Report Details |
| `/admin/api/reports/<report_id>/status` | POST | Report Status |
| `/admin/api/reports/<report_id>/resolve` | POST | Report Resolve |
| `/admin/api/reports/<report_id>/halt-funds` | POST | Halt Funds |
| `/admin/api/reports/<report_id>/refund` | POST | Report Refund |
| `/admin/analytics/user/<user_id>` | GET | User Analytics |
| `/admin/api/metrics/<metric_type>` | GET | Metrics Data |

---

## Authorization Helpers Available

From `utils/security.py`:

| Helper | Purpose |
|--------|---------|
| `authorize_resource_owner(user_id)` | Generic ownership check |
| `authorize_order_participant(order_id)` | Buyer or seller in order |
| `authorize_listing_owner(listing_id)` | Listing seller check |
| `authorize_bid_participant(bid_id)` | Bidder or listing seller |
| `authorize_message_thread(order_id, participant_id)` | Message thread access |
| `authorize_address_owner(address_id)` | Address ownership |
| `authorize_notification_owner(notification_id)` | Notification ownership |
| `authorize_payment_method_owner(method_id)` | Payment method ownership |
| `authorize_report_owner(report_id)` | Report creator check |
| `authorize_cart_owner_for_bucket(bucket_id)` | Cart item ownership |

---

## Issues Requiring Attention

### Critical (Must Fix)

*No critical issues found.* All routes with identifier parameters have authorization checks.

### Medium (Implicit Protection)

1. **Order View Route** (`/order/<order_id>`) - Uses SQL filter `buyer_id = ?` for implicit protection. Could add explicit `authorize_order_participant()` for consistency.

### Low (Acceptable)

1. **Public Read Routes** - Bucket views, listing details, and price history are intentionally public for marketplace browsing.

---

## Testing Recommendations

Run the route guard detection test to ensure all new routes with identifiers have proper authorization:

```bash
pytest tests/test_security_p0.py::TestRouteGuards -v
```

The test scans Flask's URL map and verifies:
1. All routes with `<int:*_id>` parameters have authorization checks
2. Admin routes have `@admin_required` decorator
3. State-changing routes have CSRF protection
