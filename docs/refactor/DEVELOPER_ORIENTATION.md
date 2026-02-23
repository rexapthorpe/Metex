# Developer Orientation Guide

**Updated**: 2026-01-15
**Status**: Post-Refactor Phase 1 (Tier 1 CSS/JS Complete)

This document provides guidance on where to find things in the codebase after the maintainability refactor.

---

## Quick Reference: Where to Make Changes

### Adding a New Route

| Domain | Location | Example |
|--------|----------|---------|
| Admin | `core/blueprints/admin/` | `core/blueprints/admin/new_feature.py` |
| Buy | `core/blueprints/buy/` | `core/blueprints/buy/new_feature.py` |
| Account | `core/blueprints/account/` | `core/blueprints/account/new_feature.py` |
| Listings | `core/blueprints/listings/` | `core/blueprints/listings/new_feature.py` |
| Sell | `core/blueprints/sell/` | `core/blueprints/sell/new_feature.py` |
| Cart | `core/blueprints/cart/` | `core/blueprints/cart/new_feature.py` |
| Checkout | `core/blueprints/checkout/` | `core/blueprints/checkout/new_feature.py` |

### Adding Business Logic (Services)

| Domain | Location |
|--------|----------|
| Ledger | `core/services/ledger/` |
| Analytics | `core/services/analytics/` |
| Notifications | `services/notification_service.py` |
| Pricing | `services/pricing_service.py` |
| Spot Prices | `services/spot_price_service.py` |

### Editing Templates

| Page | Template Location |
|------|-------------------|
| Account | `templates/account.html` |
| Sell | `templates/sell.html` |
| Bucket | `templates/view_bucket.html` |
| Cart | `templates/view_cart.html` |
| Buy | `templates/buy.html` |
| Checkout | `templates/checkout.html`, `templates/checkout_page.html` |
| Admin Dashboard | `templates/admin/dashboard.html` |
| Admin Analytics | `templates/admin/analytics.html` |
| Base Layout | `templates/base.html` |
| Modals | `templates/modals/*.html` |
| Tabs | `templates/tabs/*.html` |

### Editing CSS

| Component | Location |
|-----------|----------|
| **Admin Dashboard** | `static/css/admin/dashboard/` (15 partials) |
| Admin Analytics | `static/css/admin/analytics.css` |
| Account Page | `static/css/account.css` |
| **Bucket Page** | `static/css/bucket/` (8 partials) |
| **Sell Page** | `static/css/sell/` (10 partials) |
| **Base Styles** | `static/css/base/` (6 partials) |
| Modals | `static/css/modals/*.css` |
| Tabs | `static/css/tabs/*.css` |
| Header | `static/css/header.css` |
| Footer | `static/css/footer.css` |

### Editing JavaScript

| Component | Location |
|-----------|----------|
| **Admin Dashboard** | `static/js/admin/dashboard/` (13 modules) |
| **Admin Analytics** | `static/js/admin/analytics/` (6 modules) |
| Account | `static/js/account.js` |
| Bucket | `static/js/view_bucket.js` |
| Sell | `static/js/sell.js` |
| Cart | `static/js/view_cart.js` |
| Checkout | `static/js/checkout_page.js` |
| Modals | `static/js/modals/*.js` |
| Tabs | `static/js/tabs/*.js` |

---

## Refactored Module Structure

### Admin Dashboard CSS (`static/css/admin/dashboard/`)

```
dashboard/
├── _header.css           # Header, navigation, action buttons (137 lines)
├── _stats_cards.css      # Stats grid, metrics cards (990 lines)
├── _modals_base.css      # Base modal styles (451 lines)
├── _user_management.css  # User freeze states (137 lines)
├── _danger_zone.css      # Danger zone styling (72 lines)
├── _modals_clear_data.css # Clear data modal (461 lines)
├── _modals_confirm.css   # Confirm action modal (124 lines)
├── _modals_freeze.css    # Freeze user modal (124 lines)
├── _disputes_reports.css # Disputes tab (761 lines)
├── _messages_tab.css     # Messages tab (136 lines)
├── _modals_conversation.css # Conversation modal (138 lines)
├── _ledger_tab.css       # Ledger tab (87 lines)
├── _bucket_management.css # Bucket management (371 lines)
├── _responsive.css       # Media queries (626 lines)
└── _metrics_modal.css    # Metrics modal (388 lines)
```

**Main entry point**: `static/css/admin/dashboard.css` (imports all partials)

### Admin Dashboard JS (`static/js/admin/dashboard/`)

```
dashboard/
├── tabs.js               # Tab switching, global state (68 lines)
├── search-filters.js     # Search and filtering (159 lines)
├── users-tab.js          # User details, messaging (274 lines)
├── messages-tab.js       # Admin conversations (75 lines)
├── user-actions.js       # Freeze/delete actions (235 lines)
├── orders-modal.js       # Order details modal (113 lines)
├── modals.js             # Modal management (115 lines)
├── clear-data.js         # Data clearing (161 lines)
├── window-exports-1.js   # Window function exports (40 lines)
├── disputes-tab.js       # Disputes management (540 lines)
├── ledger-tab.js         # Ledger tracking (391 lines)
├── buckets-tab.js        # Bucket management (704 lines)
└── metrics.js            # Metrics display (393 lines)
```

**Load order**: Modules loaded in order via `templates/admin/dashboard.html`

### Admin Analytics JS (`static/js/admin/analytics/`)

```
analytics/
├── init.js               # Global state, filters (195 lines)
├── kpis.js               # KPI loading (88 lines)
├── charts.js             # Timeseries chart (184 lines)
├── tables-metrics.js     # Tables, metrics (233 lines)
├── drilldown.js          # Drilldown modals (655 lines)
└── user-detail.js        # User detail modal (193 lines)
```

**Load order**: Modules loaded in order via `templates/admin/analytics.html`

---

## Code Conventions

### Python Routes

```python
# Good: Route handlers are thin
@listings_bp.route('/edit_listing/<int:listing_id>', methods=['GET', 'POST'])
def edit_listing(listing_id):
    # 1. Auth check
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    # 2. Call service/helper
    result = listing_service.edit_listing(listing_id, request.form)

    # 3. Return response
    return render_template('edit_listing.html', **result)
```

### CSS Organization

```css
/* Use @import for modular CSS */
@import 'dashboard/_header.css';
@import 'dashboard/_stats_cards.css';
/* ... */
```

### JavaScript Organization

```javascript
// Each module should be self-contained
// Global state defined in first-loaded module (tabs.js or init.js)
// Functions exported to window for onclick handlers

// Example: module pattern with window export
function myFunction() {
    // implementation
}
window.myFunction = myFunction;
```

---

## Testing

### Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Specific test file
python -m pytest tests/test_security_p0.py -v

# Quick summary
python -m pytest tests/ -q
```

### Test Baseline (as of 2026-01-15)

- **Passed**: 218
- **Failed**: 82 (pre-existing environment issues)
- **Total**: 300

After any refactoring, test results should remain identical.

---

## File Size Guidelines

| File Type | Target | Maximum |
|-----------|--------|---------|
| Python routes | < 400 lines | 600 lines |
| Python services | < 500 lines | 800 lines |
| CSS partials | < 400 lines | 600 lines |
| JS modules | < 400 lines | 600 lines |
| HTML templates | < 500 lines | Assemble from partials |

---

## Backward Compatibility

### Import Paths

Original import paths still work via re-export wrappers in `routes/` directory:

```python
# Both work:
from routes.buy_routes import buy_bp
from core.blueprints.buy import buy_bp
```

### Template Names

Original template names preserved. Large templates internally include partials.

### Static File Paths

CSS/JS main files remain at original paths (`dashboard.css`, `analytics.js`).
Main files now use `@import` (CSS) or are loaded after modules (JS).

---

## Current Refactor Status

### Completed (Phases 1 & 2)

**Tier 1 - Admin (JS/CSS):**
- [x] Admin Dashboard CSS: 5,003 → 52 lines + 15 partials
- [x] Admin Dashboard JS: 3,248 → 26 lines + 13 modules
- [x] Admin Analytics JS: 1,548 → 20 lines + 6 modules

**Tier 2 - Page CSS:**
- [x] Bucket CSS: 2,460 → 31 lines + 8 partials
- [x] Sell CSS: 1,803 → 37 lines + 10 partials
- [x] Base CSS: 1,163 → 25 lines + 6 partials

**Total Lines Refactored:** 15,225 lines split into 58 modules/partials

### Pending (Phase 3+)

- [ ] Python routes (listings, sell, cart, checkout - each ~900+ lines)
- [ ] Large templates (sell.html 2,880 lines, view_bucket.html 1,180 lines)
- [ ] Large modal JS files (bid_modal.js 1,156 lines, buy_item_modal.js 1,066 lines)
- [ ] Large tab CSS files (bids_tab.css 1,677 lines, portfolio_tab.css 1,123 lines)

---

## Getting Help

For questions about the codebase structure:
1. Check this document
2. Review `docs/refactor/PHASE_A_INVENTORY.md` for the complete file inventory
3. Run `wc -l` on files to check current sizes

