# Marketplace Data Wipe Tool

## Overview

This tool provides a safe, repeatable way to clear all marketplace transaction and inventory data while preserving user accounts and database schema. Perfect for creating a clean test environment.

## Two Ways to Run

### Option 1: Flask CLI Command (Recommended)

```bash
# From project root directory
flask clear-marketplace-data          # With confirmation prompt
flask clear-marketplace-data --yes    # Skip confirmation
```

### Option 2: Standalone Python Script

```bash
# From project root directory
python clear_marketplace_data.py          # With confirmation prompt
python clear_marketplace_data.py --yes    # Skip confirmation
```

## What Gets Cleared

The following marketplace data is **DELETED**:

| Table | Description | Example Data |
|-------|-------------|--------------|
| `categories` | Buckets/item categories | Gold Eagles, Silver Maples, etc. |
| `listings` | Items for sale | All active/inactive listings |
| `bids` | Buyer bids on items | All pending/accepted/rejected bids |
| `orders` | Completed transactions | All buyer orders |
| `order_items` | Order line items | Junction between orders and listings |
| `cart` | Shopping cart entries | All items in users' carts |
| `ratings` | Buyer/seller ratings | All rating records |
| `messages` | User conversations | Order-related messages |
| `notifications` | User notifications | Bid acceptance, order updates, etc. |
| `portfolio_exclusions` | Portfolio exclusions | Items excluded from portfolio calculations |
| `portfolio_snapshots` | Portfolio history | Historical portfolio value data |
| `bucket_price_history` | Price history | Historical bucket pricing data |

**Total: 12 tables cleared**

## What Stays Intact

The following data is **PRESERVED**:

| Table | Description | Why Preserved |
|-------|-------------|---------------|
| `users` | User accounts | Keeps login credentials |
| `addresses` | Address books | User profile data |
| `user_preferences` | Notification settings | User preferences |
| All database schema | Tables, columns, indexes | Backend functionality |

## How It Works

### Deletion Order

The script deletes data in a specific order to respect foreign key constraints:

```
1. portfolio_exclusions    (references order_items, users)
2. portfolio_snapshots     (references users)
3. bucket_price_history    (references categories)
4. ratings                 (references orders, users)
5. messages                (references users, orders)
6. notifications           (references users)
7. order_items             (references orders, listings)
8. orders                  (references users)
9. bids                    (references users, categories)
10. cart                   (references users, listings)
11. listings               (references users, categories)
12. categories             (root table)
```

### Foreign Key Handling

```python
# Temporarily disable FK constraints
PRAGMA foreign_keys = OFF

# Delete all data...

# Re-enable FK constraints
PRAGMA foreign_keys = ON
```

### Autoincrement Reset

After clearing each table, the script resets the autoincrement counter:

```python
DELETE FROM sqlite_sequence WHERE name = '{table_name}'
```

This ensures new records start from ID 1.

## Safety Features

### 1. Confirmation Prompt

By default, the tool asks for confirmation:

```
⚠️  WARNING: This will delete ALL marketplace data!

The following will be cleared:
  • All buckets (categories)
  • All listings
  • All bids
  ...

User accounts, addresses, and preferences will be PRESERVED.

Are you sure you want to proceed? (yes/no):
```

### 2. Skip Confirmation (for scripts)

Use `--yes` or `-y` flag to skip confirmation:

```bash
flask clear-marketplace-data --yes
python clear_marketplace_data.py --yes
```

### 3. Graceful Error Handling

- Missing tables are skipped with a warning (not an error)
- Database errors are caught and reported
- Transaction rollback on failure

### 4. Detailed Reporting

```
🗑️  Clearing marketplace data...

  ✓ Cleared 5 Portfolio exclusions
  ✓ Cleared 12 Portfolio snapshots
  ✓ Cleared 156 Bucket price history
  ✓ Cleared 23 Ratings
  ✓ Cleared 45 Messages/conversations
  ✓ Cleared 67 Notifications
  ✓ Cleared 89 Order items
  ✓ Cleared 45 Orders
  ✓ Cleared 123 Bids
  ✓ Cleared 34 Cart items
  ✓ Cleared 234 Listings
  ✓ Cleared 15 Buckets/categories

✅ Marketplace data cleared successfully!

Total records deleted: 848

📊 Summary:
     Portfolio exclusions: 5
     Portfolio snapshots: 12
     ...
```

## Implementation Details

### Flask CLI Command (app.py)

```python
@app.cli.command('clear-marketplace-data')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
@with_appcontext
def clear_marketplace_data(yes):
    """Clear all marketplace data while preserving users and schema."""
    # Implementation...
```

**Location:** `app.py` (lines 72-170)

**Imports added:**
```python
import sqlite3
import click
from flask.cli import with_appcontext
```

### Standalone Script

**Location:** `clear_marketplace_data.py` (root directory)

**Usage:** Can be run independently without Flask context

## Why This List is Sufficient

### Marketplace Data Tables

All tables related to marketplace transactions and inventory:

1. **Categories (buckets)** - Define what items exist
2. **Listings** - Individual items for sale
3. **Bids** - Buyer offers on items
4. **Orders + Order Items** - Completed transactions
5. **Cart** - Shopping cart state
6. **Ratings** - Transaction feedback
7. **Messages** - Order communication
8. **Notifications** - Transaction alerts
9. **Portfolio** - Buyer portfolio tracking
10. **Price History** - Market data

### User Data Preserved

All tables related to user identity and settings:

1. **Users** - Login credentials, account info
2. **Addresses** - Saved shipping addresses
3. **User Preferences** - Notification settings

### Schema Preserved

- All `CREATE TABLE` statements remain
- All columns and data types intact
- All indexes and constraints preserved
- No `DROP TABLE` or `ALTER TABLE` commands

## Common Use Cases

### 1. Development Testing

```bash
# Clear data before each test run
flask clear-marketplace-data --yes
# Run your tests...
```

### 2. Demo Reset

```bash
# Reset to clean slate for demo
flask clear-marketplace-data
# Seed with demo data...
```

### 3. Data Migration

```bash
# Clear old data before import
python clear_marketplace_data.py --yes
# Import new data...
```

### 4. CI/CD Pipeline

```bash
# In your test script
export FLASK_APP=app.py
flask clear-marketplace-data --yes
pytest tests/
```

## Troubleshooting

### Database Not Found

```
❌ Error: Database file "marketplace.db" not found.
```

**Solution:** Run from project root directory where `marketplace.db` exists.

### Permission Denied

```
❌ Database error: database is locked
```

**Solution:** Close any other connections to the database (Flask dev server, database browsers, etc.)

### Table Not Found

```
⚠️  Skipped [Table Name] (table not found)
```

**Solution:** This is normal if your database doesn't have all tables yet. The script gracefully handles missing tables.

## Verification

After running, you can verify the wipe:

```python
import sqlite3
conn = sqlite3.connect('marketplace.db')
cursor = conn.cursor()

# Check if marketplace tables are empty
for table in ['categories', 'listings', 'bids', 'orders']:
    count = cursor.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    print(f'{table}: {count} records')

# Check if user tables still have data
for table in ['users', 'addresses']:
    count = cursor.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    print(f'{table}: {count} records')
```

Expected output:
```
categories: 0 records
listings: 0 records
bids: 0 records
orders: 0 records
users: 5 records        ← Users preserved
addresses: 8 records    ← Addresses preserved
```

## Notes

- This is a **destructive operation** - deleted data cannot be recovered
- Always backup your database before running in production
- The script is idempotent - safe to run multiple times
- No migrations need to be re-run after clearing data
- Autoincrement IDs reset to 1 for fresh start
