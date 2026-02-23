# Transaction Ledger & Escrow/Payout State Machine

This document describes the implementation of the transaction ledger system for Metex.

## Overview

The ledger system provides:
- Detailed financial tracking of all orders
- Per-item fee calculation (percent or flat)
- Per-seller payout aggregation
- Audit trail via order events
- Read-only admin dashboard for viewing ledger data

## Files Changed/Created

### New Files

| File | Description |
|------|-------------|
| `migrations/021_add_ledger_tables.sql` | SQL migration for ledger tables |
| `services/ledger_constants.py` | Enums for OrderStatus, PayoutStatus, FeeType, ActorType, EventType |
| `services/ledger_service.py` | Core ledger business logic |
| `templates/admin/ledger.html` | Admin ledger dashboard page |
| `templates/admin/ledger_order_detail.html` | Order detail page |
| `templates/admin/ledger_order_not_found.html` | 404 page for missing orders |
| `static/css/admin/ledger.css` | Styling for admin ledger pages |
| `tests/test_ledger.py` | Pytest tests (11 tests) |
| `docs/LEDGER_IMPLEMENTATION.md` | This documentation |

### Modified Files

| File | Changes |
|------|---------|
| `routes/checkout_routes.py` | Added `_create_ledger_for_order()` helper and integration calls |
| `routes/admin_routes.py` | Added ledger dashboard routes |

## Database Schema

### orders_ledger
Main ledger record for each order.

```sql
CREATE TABLE orders_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER UNIQUE NOT NULL,
    buyer_id INTEGER NOT NULL,
    order_status TEXT NOT NULL DEFAULT 'CHECKOUT_INITIATED',
    payment_method TEXT,
    gross_amount REAL NOT NULL,
    platform_fee_amount REAL NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### order_items_ledger
Per-item fee breakdown.

```sql
CREATE TABLE order_items_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ledger_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    listing_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    gross_amount REAL NOT NULL,
    fee_type TEXT NOT NULL DEFAULT 'percent',
    fee_value REAL NOT NULL DEFAULT 0,
    fee_amount REAL NOT NULL DEFAULT 0,
    seller_net_amount REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### order_payouts
Per-seller payout tracking.

```sql
CREATE TABLE order_payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ledger_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    payout_status TEXT NOT NULL DEFAULT 'PAYOUT_NOT_READY',
    seller_gross_amount REAL NOT NULL,
    fee_amount REAL NOT NULL DEFAULT 0,
    seller_net_amount REAL NOT NULL,
    scheduled_for TIMESTAMP,
    provider_transfer_id TEXT,
    provider_payout_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(order_ledger_id, seller_id)
);
```

### order_events
Audit trail for order lifecycle.

```sql
CREATE TABLE order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id INTEGER,
    payload_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### fee_config
Fee configuration table.

```sql
CREATE TABLE fee_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_key TEXT UNIQUE NOT NULL,
    fee_type TEXT NOT NULL DEFAULT 'percent',
    fee_value REAL NOT NULL DEFAULT 0,
    description TEXT,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Enums

### OrderStatus
```
CHECKOUT_INITIATED → PAYMENT_PENDING → PAID_IN_ESCROW → AWAITING_SHIPMENT
→ (PARTIALLY_SHIPPED →) SHIPPED → COMPLETED

Alternative paths:
- Any state → UNDER_REVIEW (admin intervention)
- Any state → CANCELLED (cancellation)
- PAID_IN_ESCROW+ → REFUNDED (refund processed)
```

### PayoutStatus
```
PAYOUT_NOT_READY → PAYOUT_READY → PAYOUT_SCHEDULED → PAYOUT_IN_PROGRESS → PAID_OUT

Alternative paths:
- PAYOUT_READY → PAYOUT_ON_HOLD (dispute/review)
- PAYOUT_ON_HOLD → PAYOUT_READY (resolved)
- Any non-terminal state → PAYOUT_CANCELLED
```

## Admin Integration

The Ledger Dashboard is integrated as a **tab** in the main Admin Dashboard (`/admin/dashboard#ledger`).

### How to Access
1. Go to `/admin/dashboard`
2. Click the "Ledger" tab (between Transactions and Disputes)

The tab includes:
- **Stats cards**: Total orders, gross volume, platform fees, pending payouts
- **Filters**: Status, buyer ID, date range, gross amount range
- **Orders table**: Paginated list of all ledger records
- **Order detail modal**: Click any order to see items, payouts, and events

## API Endpoints

### Admin Dashboard Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/admin/ledger` | GET | Standalone ledger dashboard page |
| `/admin/ledger/order/<order_id>` | GET | Standalone order detail page |
| `/admin/api/ledger/orders` | GET | Get filtered ledger orders (JSON) |
| `/admin/api/ledger/order/<order_id>` | GET | Get order detail (JSON) |
| `/admin/api/ledger/stats` | GET | Get ledger stats (JSON) |
| `/admin/api/ledger/order/<order_id>/events` | GET | Get order events (JSON) |

### Query Parameters for `/admin/api/ledger/orders`

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by OrderStatus |
| `buyer_id` | int | Filter by buyer ID |
| `start_date` | string | Start date (ISO format) |
| `end_date` | string | End date (ISO format) |
| `min_gross` | float | Minimum gross amount |
| `max_gross` | float | Maximum gross amount |
| `limit` | int | Results limit (default 100) |
| `offset` | int | Results offset (default 0) |

## Service Functions

### LedgerService.create_order_ledger_from_cart()
Creates all ledger records from a cart snapshot.

```python
ledger_id = LedgerService.create_order_ledger_from_cart(
    buyer_id=1,
    cart_snapshot=[
        {
            'seller_id': 2,
            'listing_id': 1,
            'quantity': 2,
            'unit_price': 100.00,
            'fee_type': 'percent',  # optional
            'fee_value': 2.5        # optional
        }
    ],
    payment_method='stripe',
    order_id=123
)
```

### LedgerService.log_order_event()
Logs an event in the order lifecycle.

```python
LedgerService.log_order_event(
    order_id=123,
    event_type='PAYMENT_CONFIRMED',
    actor_type='payment_provider',
    actor_id=None,
    payload={'transaction_id': 'pi_xxxxx'}
)
```

### LedgerService.validate_order_invariants()
Validates ledger invariants for an order.

Invariants:
1. `sum(order_items.gross_amount) == orders_ledger.gross_amount`
2. For each seller: `sum(items.seller_net_amount) == payout.seller_net_amount`
3. `order_payouts` cannot be `PAID_OUT` unless order_status is `PAID_IN_ESCROW` or later

## Default Fee Configuration

- Type: `percent`
- Value: `2.5%`

The default fee is applied to all items unless a custom fee_type/fee_value is specified in the cart snapshot.

## Integration Points

The ledger is created automatically when an order is placed:

1. **AJAX Cart Checkout** (`routes/checkout_routes.py:258`):
   ```python
   order_id = create_order(user_id, cart_data, shipping_address)
   _create_ledger_for_order(user_id, order_id, cart_data, conn)
   ```

2. **Traditional POST Checkout** (`routes/checkout_routes.py:402`):
   ```python
   order_id = create_order(user_id, cart_data, shipping_address, ...)
   _create_ledger_for_order(user_id, order_id, cart_data, conn)
   ```

## Manual Testing

### Prerequisites
1. Flask server running
2. Admin user account
3. Test buyer and seller accounts

### Test Steps

1. **Initialize Database**
   ```bash
   # The ledger tables are created automatically on first checkout
   # Or run manually:
   python -c "from services.ledger_service import init_ledger_tables; init_ledger_tables()"
   ```

2. **Create Test Order**
   - Log in as buyer
   - Add items to cart from different sellers
   - Complete checkout

3. **View Ledger Tab in Admin Dashboard**
   - Log in as admin
   - Navigate to `/admin/dashboard`
   - Click the "Ledger" tab
   - Verify the new order appears in the table
   - Check stats cards show correct totals (Total Orders, Gross Volume, Platform Fees, Pending Payouts)

4. **View Order Detail Modal**
   - Click on an order ID or the view button
   - Verify the modal shows:
     - Order header with correct status, buyer, amounts
     - Items table with correct per-item fees (type, value, amount, seller net)
     - Payouts table with one row per seller
     - Events timeline with ORDER_CREATED and LEDGER_CREATED events

5. **Test Filters**
   - Filter by status (dropdown)
   - Filter by buyer ID
   - Filter by date range (start/end)
   - Filter by gross amount range (min/max)
   - Click "Apply" to filter, "Clear" to reset

### Running Automated Tests

```bash
# Install pytest if not already installed
pip install pytest

# Run all ledger tests
python -m pytest tests/test_ledger.py -v

# Run specific test
python -m pytest tests/test_ledger.py::TestFeeCalculation -v
```

## Future Enhancements

1. **Stripe Integration**: Connect provider_transfer_id and provider_payout_id
2. **Payout Processing**: Implement automated payout scheduling
3. **Admin Actions**: Add status update functionality
4. **Reporting**: Add export functionality for financial reports
5. **Webhooks**: Add payment provider webhook handlers for status updates

## Error Handling

- If ledger creation fails during checkout, the order still completes (ledger is non-blocking)
- Errors are logged to console with `[CHECKOUT]` prefix
- LedgerInvariantError is raised during development if invariants are violated
