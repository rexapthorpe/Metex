# Dropdown Options Investigation Report

## Issue
After wiping all buckets from the database, the **weight, mint, year, finish, and grade** dropdowns are not appearing on the sell page when listing an item. The dropdowns appear empty and non-functional.

## Root Cause
The dropdown options are sourced from the `categories` table in the database. Since all categories were deleted, these dropdowns now have **zero options** and therefore do not appear.

## How Dropdown Options Are Stored

### Primary Source: `routes/category_options.py`

**File:** `routes/category_options.py`
**Function:** `_load_dropdown_options()` (lines 9-247)
**Cache Function:** `get_dropdown_options()` (lines 250-255)

This module loads dropdown options from the database and caches them. It queries the `categories` table for DISTINCT values.

### Database Queries (Lines 44-89)

Each dropdown is populated by querying the `categories` table:

```python
# Weights (lines 44-49)
opts['weights'] = [
    row['weight']
    for row in conn.execute(
        'SELECT DISTINCT weight FROM categories WHERE weight IS NOT NULL ORDER BY weight'
    ).fetchall()
]

# Mints (lines 60-65)
opts['mints'] = [
    row['mint']
    for row in conn.execute(
        'SELECT DISTINCT mint FROM categories WHERE mint IS NOT NULL ORDER BY mint'
    ).fetchall()
]

# Years (lines 68-73)
opts['years'] = [
    row['year']
    for row in conn.execute(
        'SELECT DISTINCT year FROM categories WHERE year IS NOT NULL ORDER BY year'
    ).fetchall()
]

# Finishes (lines 76-81)
opts['finishes'] = [
    row['finish']
    for row in conn.execute(
        'SELECT DISTINCT finish FROM categories WHERE finish IS NOT NULL ORDER BY finish'
    ).fetchall()
]

# Grades (lines 84-89)
opts['grades'] = [
    row['grade']
    for row in conn.execute(
        'SELECT DISTINCT grade FROM categories WHERE grade IS NOT NULL ORDER BY grade'
    ).fetchall()
]
```

## Inconsistency: Default Fallback Values

### ✅ WORKING DROPDOWNS (Have Default Fallbacks)

These dropdowns have hardcoded default values that are force-inserted if missing from the database:

1. **Metals** (lines 96-98)
   - Defaults: `['Gold', 'Silver', 'Platinum', 'Palladium']`
   - Currently showing: **4 options**

2. **Product Types** (lines 101-103)
   - Defaults: `['Coin', 'Bar', 'Round']`
   - Currently showing: **3 options**

3. **Product Lines** (lines 106-220)
   - Defaults: 89 product lines (American Eagle, Canadian Maple Leaf, Britannia, etc.)
   - Currently showing: **89 options**

4. **Purities** (lines 223-234)
   - Defaults: `['.9999', '.999', '.995', '.990', '.958', '.925', '.900']`
   - Currently showing: **7 options**

### ❌ BROKEN DROPDOWNS (No Default Fallbacks)

These dropdowns rely **ENTIRELY** on the database and have **NO** hardcoded defaults:

1. **Weights** (lines 44-49)
   - Database query only
   - Currently showing: **0 options** ❌

2. **Mints** (lines 60-65)
   - Database query only
   - Currently showing: **0 options** ❌

3. **Years** (lines 68-73)
   - Database query only
   - Currently showing: **0 options** ❌

4. **Finishes** (lines 76-81)
   - Database query only
   - Currently showing: **0 options** ❌

5. **Grades** (lines 84-89)
   - Database query only
   - Currently showing: **0 options** ❌

## Where These Options Are Used

### 1. Sell Page (`templates/sell.html`)

All dropdowns use Jinja2 `<datalist>` elements:

- **Weight** (lines 90-94): `{% for weight in weights %}`
- **Mint** (lines 131-135): `{% for mint in mints %}`
- **Year** (lines 151-155): `{% for year in years %}`
- **Finish** (lines 171-175): `{% for finish in finishes %}`
- **Grade** (lines 191-195): `{% for grade in grades %}`

### 2. Sell Route (`routes/sell_routes.py`)

**Import:** Line 5
```python
from .category_options import get_dropdown_options
```

**Usage:** Lines 294-308 (GET request rendering)
```python
options = get_dropdown_options()

return render_template(
    'sell.html',
    metals=options['metals'],
    product_lines=options['product_lines'],
    product_types=options['product_types'],
    weights=options['weights'],        # ← EMPTY
    purities=options['purities'],
    mints=options['mints'],            # ← EMPTY
    years=options['years'],            # ← EMPTY
    finishes=options['finishes'],      # ← EMPTY
    grades=options['grades'],          # ← EMPTY
    prefill=prefill
)
```

The function is also called on error cases (lines 74, 78, 83, 103, 116, 132).

### 3. Edit Listing Modal (`templates/modals/edit_listing_modal.html`)

Uses the same Jinja2 variables:
- Lines 88-92: weight_options
- Lines 128-132: mint_options
- Similar patterns for year, finish, grade

### 4. Other Routes

The same `get_dropdown_options()` function is imported in:
- `routes/listings_routes.py`
- `utils/category_manager.py` (for validation)

## Current State After Database Wipe

```
=== DROPDOWN OPTIONS CURRENTLY AVAILABLE ===
Metals: 4 options ✓
Product Lines: 89 options ✓
Product Types: 3 options ✓
Weights: 0 options ✗
Purities: 7 options ✓
Mints: 0 options ✗
Years: 0 options ✗
Finishes: 0 options ✗
Grades: 0 options ✗
```

## Summary

**Files Where Dropdown Specs Are Saved:**

1. **Primary Definition:** `routes/category_options.py`
   - Lines 9-247: `_load_dropdown_options()` function
   - Lines 44-89: Database queries for weights, mints, years, finishes, grades
   - Lines 96-234: Hardcoded defaults for metals, product types, product lines, purities

2. **Database:** `database.db` → `categories` table
   - Contains DISTINCT values from all previously created categories
   - Currently empty after wipe

3. **Template Usage:** `templates/sell.html`
   - Lines 90-195: Dropdown `<datalist>` elements using Jinja2 variables

4. **Route Handler:** `routes/sell_routes.py`
   - Line 5: Import statement
   - Lines 294-308: Passes options to template

**The Inconsistency:**
- Some dropdowns (metals, product_lines, product_types, purities) have hardcoded fallback values
- Other dropdowns (weights, mints, years, finishes, grades) have NO fallback values
- This creates a broken user experience when the database is empty

**Why It's Broken:**
The missing dropdowns rely on data being present in the `categories` table. After wiping all buckets/categories, the database queries return empty lists, and there are no default values to fall back on.
