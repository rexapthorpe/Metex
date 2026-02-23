# Isolated & Set Listings Implementation Guide

## ✅ COMPLETED: Step 1 - Database Migration

**File:** `migrations/010_add_isolated_and_set_listings.sql`

### Added to `listings` table:
- `is_isolated` (INTEGER, default 0) - Whether listing has dedicated bucket
- `isolated_type` (TEXT, nullable) - Type: 'one_of_a_kind' or 'set'
- `issue_number` (INTEGER, nullable) - X in "X out of Y"
- `issue_total` (INTEGER, nullable) - Y in "X out of Y"

### Added to `categories` table (buckets):
- `is_isolated` (INTEGER, default 0) - Prevents other listings from joining

### New table `listing_set_items`:
```sql
CREATE TABLE listing_set_items (
    id INTEGER PRIMARY KEY,
    listing_id INTEGER NOT NULL,
    position_index INTEGER DEFAULT 0,

    -- All category/spec fields
    metal, product_line, product_type, weight, purity,
    mint, year, finish, grade, coin_series,
    special_designation, graded, grading_service,

    FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
);
```

**Status:** ✅ Migration applied successfully

---

## 🔨 TODO: Step 2 - Sell Page UI Updates

**Files to modify:**
- `templates/sell.html`
- `static/js/sell.js` (or inline `<script>` in sell.html)
- `static/css/sell.css`

### UI Components to Add:

#### 2.1 Isolated Toggle (add after line ~12, before metal input)

```html
<!-- Isolated/Numismatic Listing Toggle -->
<div class="input-group special-listing-controls">
    <label class="checkbox-label">
        <input type="checkbox" name="is_isolated" id="isIsolatedToggle" value="1">
        <span>List as isolated / numismatic item (dedicated bucket)</span>
    </label>
    <div id="isolatedWarning" class="warning-message" style="display: none;">
        ⚠️ This listing will be placed in its own isolated bucket. No other sellers
        will be able to add items to this bucket. This may reduce liquidity for your item.
    </div>
</div>
```

#### 2.2 Set Toggle and Builder (add after isolated toggle)

```html
<!-- Set Listing Toggle -->
<div class="input-group special-listing-controls">
    <label class="checkbox-label">
        <input type="checkbox" name="is_set" id="isSetToggle" value="1">
        <span>List as part of a set (multiple items sold together)</span>
    </label>
</div>

<!-- Set Items Container (hidden initially) -->
<div id="setItemsContainer" style="display: none;">
    <h3 class="section-header">Set Items</h3>
    <div id="setItemsList">
        <!-- Set item #1 will be the main form fields -->
        <!-- Additional set items will be added here dynamically -->
    </div>
    <button type="button" id="addSetItemBtn" class="btn btn-secondary">
        + Add Another Item to Set
    </button>
</div>
```

#### 2.3 Numismatic X-of-Y Inputs (add near isolated toggle)

```html
<!-- Numismatic Issue Fields -->
<div class="input-group numismatic-fields">
    <label>Numismatic Issue (optional)</label>
    <div class="inline-inputs">
        <span>Issue #</span>
        <input type="number" name="issue_number" id="issueNumber"
               min="1" placeholder="X" style="width: 80px;">
        <span>out of</span>
        <input type="number" name="issue_total" id="issueTotal"
               min="1" placeholder="Y" style="width: 80px;">
    </div>
    <small class="example-text">Example: #5 out of 100</small>
</div>
```

### JavaScript Logic (add to sell.html or sell.js):

```javascript
// Toggle isolated warning
document.getElementById('isIsolatedToggle').addEventListener('change', function(e) {
    document.getElementById('isolatedWarning').style.display =
        e.target.checked ? 'block' : 'none';
});

// Auto-check isolated when numismatic fields are filled
['issueNumber', 'issueTotal'].forEach(id => {
    document.getElementById(id).addEventListener('input', function() {
        const num = document.getElementById('issueNumber').value;
        const total = document.getElementById('issueTotal').value;
        if (num && total) {
            document.getElementById('isIsolatedToggle').checked = true;
            document.getElementById('isolatedWarning').style.display = 'block';
        }
    });
});

// Set listing toggle
document.getElementById('isSetToggle').addEventListener('change', function(e) {
    const container = document.getElementById('setItemsContainer');
    const isolated = document.getElementById('isIsolatedToggle');

    if (e.target.checked) {
        container.style.display = 'block';
        isolated.checked = true;
        isolated.disabled = true;
        document.getElementById('isolatedWarning').style.display = 'block';
    } else {
        container.style.display = 'none';
        isolated.disabled = false;
        // Remove all extra set items
        const extras = container.querySelectorAll('.set-item-extra');
        extras.forEach(item => item.remove());
    }
});

// Add set item functionality
let setItemCount = 1;
document.getElementById('addSetItemBtn').addEventListener('click', function() {
    setItemCount++;
    const itemDiv = document.createElement('div');
    itemDiv.className = 'set-item-extra';
    itemDiv.innerHTML = `
        <div class="set-item-header">
            <h4>Set Item #${setItemCount}</h4>
            <button type="button" class="remove-set-item" data-index="${setItemCount}">Remove</button>
        </div>
        <div class="input-grid">
            <input type="text" name="set_items[${setItemCount}][metal]"
                   class="validated-datalist" placeholder="Metal" required>
            <input type="text" name="set_items[${setItemCount}][product_line]"
                   placeholder="Product Line" required>
            <input type="text" name="set_items[${setItemCount}][product_type]"
                   placeholder="Product Type" required>
            <input type="text" name="set_items[${setItemCount}][weight]"
                   placeholder="Weight" required>
            <!-- Add all other category fields similarly -->
        </div>
    `;
    document.getElementById('setItemsList').appendChild(itemDiv);
});

// Remove set item
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('remove-set-item')) {
        e.target.closest('.set-item-extra').remove();
    }
});

// Form validation before submit
document.getElementById('sellForm').addEventListener('submit', function(e) {
    const isSet = document.getElementById('isSetToggle').checked;
    const setItems = document.querySelectorAll('.set-item-extra');

    if (isSet && setItems.length < 1) {
        e.preventDefault();
        alert('A set listing must contain at least 2 items (main item + at least 1 additional item)');
        return false;
    }

    // Validate numismatic fields (both or neither)
    const issueNum = document.getElementById('issueNumber').value;
    const issueTotal = document.getElementById('issueTotal').value;
    if ((issueNum && !issueTotal) || (!issueNum && issueTotal)) {
        e.preventDefault();
        alert('Please fill both issue number and total, or leave both empty');
        return false;
    }
});
```

---

## 🔨 TODO: Step 3 - Sell Page Backend

**File to modify:** `routes/sell_routes.py`

### Update the POST handler:

```python
@sell_bp.route('/sell', methods=['POST'])
def sell():
    # ... existing code for authentication ...

    # Get isolated/numismatic fields
    is_isolated = request.form.get('is_isolated') == '1'
    is_set = request.form.get('is_set') == '1'
    issue_number = request.form.get('issue_number')
    issue_total = request.form.get('issue_total')

    # Determine isolated_type
    isolated_type = None
    if is_set:
        is_isolated = True
        isolated_type = 'set'
    elif is_isolated:
        isolated_type = 'one_of_a_kind'

    # Force isolated if numismatic fields are filled
    if issue_number and issue_total:
        is_isolated = True
        if not isolated_type:
            isolated_type = 'one_of_a_kind'

    # Validate numismatic fields (both or neither)
    if (issue_number and not issue_total) or (not issue_number and issue_total):
        flash("Both issue number and total must be provided, or leave both empty", "error")
        return redirect(url_for('sell.sell'))

    # Convert to int if valid
    issue_number = int(issue_number) if issue_number else None
    issue_total = int(issue_total) if issue_total else None

    # ... existing code for category creation/lookup ...

    # MODIFIED: Bucket assignment for isolated listings
    if is_isolated:
        # Create new isolated bucket
        cursor.execute('''
            INSERT INTO categories (
                metal, product_line, product_type, weight, purity,
                mint, year, finish, grade, coin_series, bucket_id, is_isolated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ''', (metal, product_line, product_type, weight, purity,
              mint, year, finish, grade, coin_series, bucket_id))
        category_id = cursor.lastrowid
    else:
        # Existing logic: find or create non-isolated bucket
        # IMPORTANT: Add filter to exclude isolated buckets
        existing = cursor.execute('''
            SELECT id FROM categories
            WHERE metal=? AND product_line=? AND product_type=? AND weight=?
              AND purity=? AND mint=? AND year=? AND finish=?
              AND grade=? AND coin_series=?
              AND is_isolated = 0  -- ADDED: Exclude isolated buckets
        ''', (metal, product_line, ...)).fetchone()

        if existing:
            category_id = existing['id']
        else:
            # Create new non-isolated bucket
            cursor.execute('INSERT INTO categories (..., is_isolated) VALUES (..., 0)')
            category_id = cursor.lastrowid

    # Create listing with isolated fields
    cursor.execute('''
        INSERT INTO listings (
            category_id, seller_id, quantity, price_per_coin,
            is_isolated, isolated_type, issue_number, issue_total,
            ... other fields ...
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ...)
    ''', (category_id, seller_id, quantity, price_per_coin,
          1 if is_isolated else 0, isolated_type, issue_number, issue_total,
          ... other values ...))

    listing_id = cursor.lastrowid

    # If set listing, create set items
    if is_set:
        # Item #1 is the main form fields
        cursor.execute('''
            INSERT INTO listing_set_items (
                listing_id, position_index, metal, product_line, product_type,
                weight, purity, mint, year, finish, grade, coin_series
            ) VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (listing_id, metal, product_line, product_type, weight,
              purity, mint, year, finish, grade, coin_series))

        # Additional set items from form
        position = 1
        for key in request.form.keys():
            if key.startswith('set_items[') and key.endswith('][metal]'):
                # Extract index
                import re
                match = re.search(r'set_items\[(\d+)\]', key)
                if match:
                    idx = match.group(1)

                    # Get all fields for this set item
                    set_metal = request.form.get(f'set_items[{idx}][metal]')
                    set_product_line = request.form.get(f'set_items[{idx}][product_line]')
                    # ... get all other fields ...

                    cursor.execute('''
                        INSERT INTO listing_set_items (
                            listing_id, position_index, metal, ...
                        ) VALUES (?, ?, ?, ...)
                    ''', (listing_id, position, set_metal, ...))

                    position += 1

    conn.commit()
    conn.close()

    flash("Listing created successfully!", "success")
    return redirect(url_for('buy.buy'))
```

---

## 🔨 TODO: Step 4 - Buy Page Updates

**File to modify:** `routes/buy_routes.py`

### Update buy() route to fetch isolated and set listings:

```python
@buy_bp.route('/buy')
def buy():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Existing: Fetch standard (non-isolated) buckets
    standard_buckets = cursor.execute('''
        SELECT DISTINCT c.* FROM categories c
        JOIN listings l ON c.id = l.category_id
        WHERE l.active = 1 AND l.quantity > 0
          AND c.is_isolated = 0
        ORDER BY c.metal, c.product_line
    ''').fetchall()

    # NEW: Fetch isolated one-of-a-kind / numismatic listings
    isolated_listings = cursor.execute('''
        SELECT l.*, c.bucket_id, c.metal, c.product_line, c.product_type,
               c.weight, c.purity, c.mint, c.year, c.finish, c.grade
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
          AND l.is_isolated = 1
          AND (l.isolated_type = 'one_of_a_kind'
               OR l.issue_number IS NOT NULL)
        ORDER BY c.metal, c.product_line
    ''').fetchall()

    # NEW: Fetch set listings
    set_listings = cursor.execute('''
        SELECT l.*, c.bucket_id, c.metal, c.product_line
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE l.active = 1 AND l.quantity > 0
          AND l.is_isolated = 1
          AND l.isolated_type = 'set'
        ORDER BY c.metal, c.product_line
    ''').fetchall()

    # For each set listing, fetch its components
    set_listings_with_items = []
    for set_listing in set_listings:
        set_dict = dict(set_listing)

        # Get set components
        components = cursor.execute('''
            SELECT * FROM listing_set_items
            WHERE listing_id = ?
            ORDER BY position_index
        ''', (set_listing['id'],)).fetchall()

        set_dict['components'] = [dict(c) for c in components]
        set_dict['component_count'] = len(components)
        set_listings_with_items.append(set_dict)

    conn.close()

    return render_template('buy.html',
        standard_buckets=standard_buckets,
        isolated_listings=isolated_listings,
        set_listings=set_listings_with_items
    )
```

### Update buy.html template:

Add new sections after standard buckets:

```html
<!-- Existing standard buckets section -->
<section class="buckets-section">
    <h2>Standard Listings</h2>
    <!-- existing bucket tiles -->
</section>

<!-- NEW: One-of-a-kind & Numismatic section -->
{% if isolated_listings %}
<section class="buckets-section isolated-section">
    <h2>One-of-a-Kind & Numismatic Listings</h2>
    <div class="buckets-grid">
        {% for listing in isolated_listings %}
        <div class="bucket-tile isolated-tile">
            <span class="isolated-badge">Isolated</span>

            {% if listing.issue_number and listing.issue_total %}
            <span class="numismatic-badge">
                Issue #{{ listing.issue_number }} of {{ listing.issue_total }}
            </span>
            {% endif %}

            <h3>{{ listing.weight }} {{ listing.product_line }} {{ listing.year }}</h3>
            <p>{{ listing.metal }} • {{ listing.product_type }}</p>
            <p class="price">${{ '{:,.2f}'.format(listing.price_per_coin) }}</p>
            <a href="{{ url_for('buy.view_bucket', bucket_id=listing.bucket_id) }}"
               class="btn btn-primary">View Details</a>
        </div>
        {% endfor %}
    </div>
</section>
{% endif %}

<!-- NEW: Set Listings section -->
{% if set_listings %}
<section class="buckets-section set-section">
    <h2>Set Listings</h2>
    <div class="buckets-grid">
        {% for set_listing in set_listings %}
        <div class="bucket-tile set-tile">
            <span class="set-badge">Set of {{ set_listing.component_count }} items</span>

            <h3>{{ set_listing.metal }} {{ set_listing.product_line }} Set</h3>

            <div class="set-components-preview">
                <strong>Set contains:</strong>
                <ul>
                    {% for comp in set_listing.components[:3] %}
                    <li>{{ comp.weight }} {{ comp.product_line }} {{ comp.year }}</li>
                    {% endfor %}
                    {% if set_listing.component_count > 3 %}
                    <li>... and {{ set_listing.component_count - 3 }} more</li>
                    {% endif %}
                </ul>
            </div>

            <p class="price">${{ '{:,.2f}'.format(set_listing.price_per_coin) }} per set</p>
            <a href="{{ url_for('buy.view_bucket', bucket_id=set_listing.bucket_id) }}"
               class="btn btn-primary">View Details</a>
        </div>
        {% endfor %}
    </div>
</section>
{% endif %}
```

---

## 🔨 TODO: Step 5 - Bucket ID Page Updates

**File to modify:** `routes/buy_routes.py` (view_bucket function) and `templates/view_bucket.html`

### In view_bucket route, add:

```python
@buy_bp.route('/bucket/<int:bucket_id>')
def view_bucket(bucket_id):
    # ... existing code ...

    # Check if this bucket is isolated/contains set listings
    bucket_info = cursor.execute('''
        SELECT c.*,
               l.is_isolated, l.isolated_type,
               l.issue_number, l.issue_total
        FROM categories c
        LEFT JOIN listings l ON c.id = l.category_id
        WHERE c.bucket_id = ?
        LIMIT 1
    ''', (bucket_id,)).fetchone()

    # If set listing, get components
    set_components = []
    if bucket_info and bucket_info['isolated_type'] == 'set':
        listing_id = cursor.execute('''
            SELECT id FROM listings
            WHERE category_id = ? AND is_isolated = 1
        ''', (bucket_info['id'],)).fetchone()

        if listing_id:
            set_components = cursor.execute('''
                SELECT * FROM listing_set_items
                WHERE listing_id = ?
                ORDER BY position_index
            ''', (listing_id['id'],)).fetchall()

    return render_template('view_bucket.html',
        bucket=bucket_info,
        set_components=set_components,
        # ... other existing context ...
    )
```

### In view_bucket.html, add near top:

```html
<!-- Isolated/Numismatic Labels -->
{% if bucket.is_isolated %}
<div class="bucket-special-labels">
    <span class="label label-isolated">Isolated Listing</span>

    {% if bucket.isolated_type == 'set' %}
    <span class="label label-set">Set Listing</span>
    {% endif %}

    {% if bucket.issue_number and bucket.issue_total %}
    <span class="label label-numismatic">
        Issue #{{ bucket.issue_number }} of {{ bucket.issue_total }}
    </span>
    {% endif %}
</div>
{% endif %}

<!-- Set Components Breakdown -->
{% if set_components %}
<div class="set-components-detail">
    <h3>Set Contents ({{ set_components|length }} items)</h3>
    <div class="components-list">
        {% for comp in set_components %}
        <div class="component-item">
            <strong>Item {{ loop.index }}:</strong>
            {{ comp.weight }} {{ comp.product_line }} {{ comp.product_type }}
            {{ comp.year }} {{ comp.mint }} {{ comp.finish }}
            {% if comp.grade %} - {{ comp.grade }}{% endif %}
            {% if comp.graded %} ({{ comp.grading_service }}){% endif %}
        </div>
        {% endfor %}
    </div>
</div>
{% endif %}
```

---

## 🔨 TODO: Step 6 - Orders/Sold/Portfolio Updates

**Files to modify:**
- `templates/tabs/orders_tab.html`
- `templates/tabs/sold_tab.html`
- `templates/tabs/portfolio_tab.html`
- Item details modals in each

### Add to each item tile/card display:

```html
<!-- In order/sold/portfolio item display -->
<div class="item-card">
    <!-- Existing item info -->

    <!-- NEW: Isolated/Set labels -->
    {% if item.is_isolated %}
        <span class="label label-sm label-isolated">Isolated</span>
    {% endif %}

    {% if item.isolated_type == 'set' %}
        <span class="label label-sm label-set">Set</span>
    {% endif %}

    {% if item.issue_number and item.issue_total %}
        <div class="item-issue">
            Issue #{{ item.issue_number }} of {{ item.issue_total }}
        </div>
    {% endif %}
</div>
```

### In item details modals, add:

```html
<!-- Item Details Modal -->
<div class="modal-body">
    <!-- Existing details -->

    <!-- NEW: Set components if applicable -->
    {% if item.isolated_type == 'set' and item.components %}
    <div class="detail-section">
        <h4>Set Contents</h4>
        <ul class="set-components-list">
            {% for comp in item.components %}
            <li>
                {{ comp.weight }} {{ comp.metal }} {{ comp.product_line }}
                {{ comp.product_type }} {{ comp.year }}
                {% if comp.grade %}({{ comp.grade }}){% endif %}
            </li>
            {% endfor %}
        </ul>
    </div>
    {% endif %}
</div>
```

---

## 📋 Implementation Checklist

- [x] Database migration created and applied
- [ ] Sell page UI: Isolated toggle + warning
- [ ] Sell page UI: Set toggle + dynamic item builder
- [ ] Sell page UI: Numismatic X-of-Y inputs
- [ ] Sell page backend: Handle isolated/set/numismatic fields
- [ ] Sell page backend: Create listing_set_items rows
- [ ] Bucket assignment: Create isolated buckets
- [ ] Bucket assignment: Prevent joining isolated buckets
- [ ] Buy page: Query isolated and set listings
- [ ] Buy page: Display isolated listings section
- [ ] Buy page: Display set listings section
- [ ] Bucket ID page: Show isolated/set labels
- [ ] Bucket ID page: Show set components
- [ ] Orders tab: Show isolated/set labels
- [ ] Sold tab: Show isolated/set labels
- [ ] Portfolio tab: Show isolated/set labels
- [ ] Item modals: Show set components breakdown

---

## 🎨 CSS Styles to Add

```css
/* Isolated/Set Listing Styles */
.isolated-badge, .set-badge, .numismatic-badge {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
}

.isolated-badge {
    background: #ff9800;
    color: white;
}

.set-badge {
    background: #9c27b0;
    color: white;
}

.numismatic-badge {
    background: #2196f3;
    color: white;
}

.warning-message {
    background: #fff3cd;
    border: 1px solid #ffc107;
    padding: 12px;
    border-radius: 4px;
    margin-top: 8px;
    font-size: 13px;
}

.set-item-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.remove-set-item {
    color: #f44336;
    background: none;
    border: none;
    cursor: pointer;
    font-size: 13px;
}

.set-components-preview ul {
    list-style: none;
    padding-left: 0;
    font-size: 13px;
}

.set-components-detail {
    background: #f5f5f5;
    padding: 16px;
    border-radius: 8px;
    margin: 16px 0;
}

.component-item {
    padding: 8px;
    border-bottom: 1px solid #ddd;
}

.component-item:last-child {
    border-bottom: none;
}
```

---

## 🧪 Testing Scenarios

1. **Create One-of-a-Kind Listing:**
   - Check isolated toggle
   - Submit listing
   - Verify new bucket created with `is_isolated=1`
   - Verify listing appears in "One-of-a-Kind" section on Buy page

2. **Create Numismatic Listing:**
   - Fill issue #5 of 100
   - Verify isolated toggle auto-checks
   - Submit
   - Verify badge shows "Issue #5 of 100" on all displays

3. **Create Set Listing:**
   - Check "List as part of a set"
   - Add 2 additional items (total 3)
   - Submit
   - Verify 3 rows in `listing_set_items`
   - Verify set appears in "Set Listings" section
   - Verify component breakdown shows all 3 items

4. **Bucket Isolation:**
   - Create isolated listing
   - Try to create similar non-isolated listing
   - Verify it creates separate bucket, doesn't join isolated one

5. **Display Verification:**
   - Check Bucket ID page shows labels and set components
   - Check Orders tab shows labels
   - Check Sold tab shows labels
   - Check Portfolio shows labels
   - Check all item modals show set components

---

## 📝 Notes

- All isolated listings (one-of-a-kind, numismatic, sets) always create their own bucket
- Set listings are always isolated
- Numismatic items (with X/Y) are always isolated
- Standard (non-isolated) listings never join isolated buckets
- Set components are stored separately in `listing_set_items` table
- The parent listing represents the sellable unit (price, quantity of sets)
- Components describe what's in each set instance

