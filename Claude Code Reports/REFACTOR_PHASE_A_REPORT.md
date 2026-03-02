# Phase A: Inventory & Mapping Report

## Industrial-Grade Maintainability Refactor

**Date**: 2026-01-21
**Status**: Phase A Complete - Awaiting Approval

---

## Executive Summary

This report inventories all files exceeding 600 lines in the Metex codebase and proposes a split strategy to achieve industrial-grade maintainability. The goal is to reduce all mega-files to cohesive, focused modules while maintaining **zero behavior change**.

### Current State
- **56 files** exceed 600 lines
- Largest file: `templates/sell.html` at 2,880 lines
- Heavy mixing of HTML + inline JS in templates
- CSS already well-modularized (some files large but cohesive)
- Python routes already in `core/blueprints/` structure (good foundation)

### Key Findings
1. **Templates** are the primary problem - sell.html contains ~1,500 lines of inline JavaScript
2. **Python routes** are already modular but some modules exceed targets
3. **CSS** files are large but mostly cohesive (page/component-scoped)
4. **JavaScript** modals need extraction from templates into external files

---

## 1. Files Over 600 Lines (Excluding venv/tests)

### TEMPLATES (6 files)

| Lines | File | Responsibility |
|-------|------|----------------|
| **2,880** | `templates/sell.html` | Sell form + 3 large inline JS IIFEs |
| **1,680** | `templates/admin/dashboard.html` | Admin dashboard + tab panels |
| **1,345** | `templates/account.html` | Account page + modal includes + mobile nav |
| **1,180** | `templates/view_bucket.html` | Bucket detail page + gallery + inline JS |
| **704** | `templates/modals/edit_listing_modal.html` | Edit listing modal form |
| **621** | `templates/base.html` | Base layout + header/footer/flash |

### PYTHON - Core Routes (10 files)

| Lines | File | Responsibility |
|-------|------|----------------|
| **961** | `core/blueprints/sell/routes.py` | Sell endpoint + photo handling + set items |
| **887** | `core/blueprints/buy/purchase.py` | Purchase operations + autofill + price lock |
| **849** | `core/blueprints/cart/routes.py` | Cart CRUD + quantity updates |
| **821** | `core/blueprints/listings/routes.py` | Edit/cancel listings + photo handling |
| **790** | `core/blueprints/account/account_page.py` | Account page data aggregation |
| **730** | `core/blueprints/admin/reports.py` | Admin reports/disputes |
| **708** | `core/blueprints/admin/users.py` | Admin user management |
| **709** | `core/__init__.py` | App factory + blueprint registration |
| **667** | `core/blueprints/checkout/routes.py` | Checkout flow + ledger |
| **620** | `core/blueprints/admin/analytics.py` | Analytics KPIs + time series |

### PYTHON - Services (3 files)

| Lines | File | Responsibility |
|-------|------|----------------|
| **806** | `services/notification_service.py` | All notification types + email |
| **697** | `core/services/ledger/escrow_control.py` | Escrow hold/release/refund |
| **603** | `services/pricing_service.py` | Pricing calculations |

### PYTHON - Other (3 files)

| Lines | File | Responsibility |
|-------|------|----------------|
| **1,075** | `scripts/create_schema.py` | DB schema creation (acceptable) |
| **648** | `utils/security.py` | Security utilities |
| **645** | `routes/cancellation_routes.py` | Order cancellation |

### CSS (20 files over 600 lines)

| Lines | File | Responsibility |
|-------|------|----------------|
| **1,677** | `static/css/tabs/bids_tab.css` | Bids tab styling |
| **1,476** | `static/css/checkout_page.css` | Checkout page |
| **1,432** | `static/css/modals/bid_modal.css` | Bid modal |
| **1,175** | `static/css/view_cart.css` | Cart view |
| **1,123** | `static/css/tabs/portfolio_tab.css` | Portfolio tab |
| **1,110** | `static/css/modals/edit_listing_modal.css` | Edit listing modal |
| **1,085** | `static/css/modals/accept_bid_modals.css` | Accept bid modals |
| **1,065** | `static/css/bucket/_responsive.css` | Bucket responsive |
| **1,032** | `static/css/tabs/orders_tab.css` | Orders tab |
| **1,016** | `static/css/tabs/sold_tab.css` | Sold tab |
| **990** | `static/css/admin/dashboard/_stats_cards.css` | Admin stats |
| **960** | `static/css/admin/analytics.css` | Admin analytics |
| **948** | `static/css/account.css` | Account page |
| **932** | `static/css/modals/cancel_order_modal.css` | Cancel order modal |
| **787** | `static/css/header.css` | Header styles |
| **761** | `static/css/admin/dashboard/_disputes_reports.css` | Admin disputes |
| **759** | `static/css/tabs/account_details_tab.css` | Account details |
| **739** | `static/css/admin/ledger.css` | Admin ledger |
| **690** | `static/css/login.css` | Login page |
| **626** | `static/css/admin/dashboard/_responsive.css` | Admin responsive |

### JAVASCRIPT (12 files over 600 lines)

| Lines | File | Responsibility |
|-------|------|----------------|
| **1,156** | `static/js/modals/bid_modal.js` | Bid create/edit modal |
| **1,066** | `static/js/modals/buy_item_modal.js` | Buy item modal |
| **987** | `static/js/modals/edit_listing_modal.js` | Edit listing modal |
| **937** | `static/js/tabs/portfolio_tab.js` | Portfolio charts |
| **838** | `static/js/modals/bid_confirm_modal.js` | Bid confirmation |
| **724** | `static/js/sell.js` | Sell page form logic |
| **704** | `static/js/admin/dashboard/buckets-tab.js` | Admin buckets |
| **668** | `static/js/modals/edit_listing_confirmation_modals.js` | Edit confirmation |
| **655** | `static/js/admin/analytics/drilldown.js` | Analytics drilldown |
| **644** | `static/js/bucket_price_chart.js` | Price chart |
| **627** | `static/js/checkout_page.js` | Checkout logic |
| **620** | `static/js/modals/accept_bid_modals.js` | Accept bid logic |

---

## 2. Split Maps for Mega-Files

### TEMPLATE: `templates/sell.html` (2,880 lines) - CRITICAL

**Current Structure:**
- Lines 1-850: HTML form structure (listing mode, fields, photo uploads)
- Lines 851-1100: First JS IIFE (mode switching, UI updates)
- Lines 1101-1800: Second JS IIFE (set item builder, photo handling)
- Lines 1801-2500: Third JS IIFE (sidebar, checklist, validation)
- Lines 2501-2880: Fourth JS IIFE (form submission, final validation)

**Split Map:**

| New File | Content | Lines (approx) |
|----------|---------|----------------|
| `templates/sell.html` | Form shell + includes | ~300 |
| `templates/partials/sell/_listing_mode_selector.html` | Mode selector HTML | ~80 |
| `templates/partials/sell/_item_fields.html` | Item spec fields | ~200 |
| `templates/partials/sell/_photo_upload.html` | Photo upload UI | ~100 |
| `templates/partials/sell/_pricing_section.html` | Pricing fields | ~100 |
| `templates/partials/sell/_sidebar.html` | Sticky sidebar | ~150 |
| `static/js/sell/mode_switcher.js` | Mode switching logic | ~200 |
| `static/js/sell/set_item_builder.js` | Set item management | ~400 |
| `static/js/sell/photo_handler.js` | Photo upload handling | ~300 |
| `static/js/sell/sidebar_controller.js` | Sidebar & checklist | ~400 |
| `static/js/sell/form_submission.js` | Validation & submit | ~300 |

**Rationale:** The inline JS has distinct responsibilities that can be extracted to external files. The HTML can be split into Jinja partials that the main template includes.

---

### TEMPLATE: `templates/admin/dashboard.html` (1,680 lines)

**Current Structure:**
- Lines 1-70: Tab navigation
- Lines 71-500: Overview tab (stat cards, charts)
- Lines 501-800: Users tab
- Lines 801-1000: Listings tab
- Lines 1001-1200: Buckets tab
- Lines 1201-1400: Transactions tab
- Lines 1401-1500: Ledger tab
- Lines 1501-1600: Disputes tab
- Lines 1601-1680: Messages & System tabs

**Split Map:**

| New File | Content | Lines (approx) |
|----------|---------|----------------|
| `templates/admin/dashboard.html` | Tab shell + includes | ~150 |
| `templates/admin/partials/_tab_nav.html` | Tab navigation | ~50 |
| `templates/admin/partials/_overview_tab.html` | Overview content | ~350 |
| `templates/admin/partials/_users_tab.html` | Users table + modals | ~300 |
| `templates/admin/partials/_listings_tab.html` | Listings management | ~200 |
| `templates/admin/partials/_buckets_tab.html` | Buckets management | ~200 |
| `templates/admin/partials/_transactions_tab.html` | Transactions | ~200 |
| `templates/admin/partials/_disputes_tab.html` | Disputes/reports | ~150 |

**Rationale:** Each tab is a self-contained UI section with no cross-dependencies.

---

### TEMPLATE: `templates/account.html` (1,345 lines)

**Current Structure:**
- Lines 1-80: Modal includes + CSS links
- Lines 81-200: Mobile navigation
- Lines 201-400: Desktop sidebar
- Lines 401-1345: Tab content panels (embedded via includes already)

**Split Map:**

| New File | Content | Lines (approx) |
|----------|---------|----------------|
| `templates/account.html` | Layout shell | ~150 |
| `templates/partials/account/_mobile_nav.html` | Mobile nav overlay | ~150 |
| `templates/partials/account/_desktop_sidebar.html` | Desktop sidebar | ~100 |
| `templates/partials/account/_modal_includes.html` | Modal include block | ~50 |
| `templates/partials/account/_css_links.html` | CSS link tags | ~40 |

**Rationale:** Mobile nav and sidebar are reusable patterns; CSS/modal includes are boilerplate.

---

### TEMPLATE: `templates/view_bucket.html` (1,180 lines)

**Current Structure:**
- Lines 1-200: Gallery and main content
- Lines 201-500: Item specs display
- Lines 501-700: Price history chart
- Lines 701-900: Bidder/seller info
- Lines 901-1180: Inline JS for chart/modals

**Split Map:**

| New File | Content | Lines (approx) |
|----------|---------|----------------|
| `templates/view_bucket.html` | Main layout | ~200 |
| `templates/partials/bucket/_gallery.html` | Image gallery | ~100 |
| `templates/partials/bucket/_item_specs.html` | Specs table | ~150 |
| `templates/partials/bucket/_price_chart.html` | Chart container | ~50 |
| `templates/partials/bucket/_seller_info.html` | Seller section | ~100 |
| `static/js/bucket/gallery.js` | Gallery interactions | ~100 |
| `static/js/bucket/chart_init.js` | Chart initialization | ~150 |

**Rationale:** Gallery, specs, and chart are distinct visual components.

---

### PYTHON: `core/blueprints/sell/routes.py` (961 lines)

**Current Structure:**
- Lines 1-30: Imports + constants
- Lines 31-400: Main sell() POST handler
- Lines 401-600: Photo processing helpers
- Lines 601-800: Set item processing
- Lines 801-961: Bid matching logic

**Split Map:**

| New File | Content | Lines (approx) |
|----------|---------|----------------|
| `core/blueprints/sell/routes.py` | Route handlers only | ~300 |
| `core/blueprints/sell/photo_handler.py` | Photo upload logic | ~200 |
| `core/blueprints/sell/set_items.py` | Set item processing | ~200 |
| `core/blueprints/sell/bid_matching.py` | Bid match on listing | ~200 |
| `core/blueprints/sell/validation.py` | Form validation | ~100 |

**Rationale:** Routes should parse request + delegate; business logic in helpers.

---

### PYTHON: `core/blueprints/buy/purchase.py` (887 lines)

**Current Structure:**
- Lines 1-50: Imports
- Lines 51-300: purchase_preview()
- Lines 301-500: autofill_bucket_purchase()
- Lines 501-700: process_purchase()
- Lines 701-887: price lock refresh

**Split Map:**

| New File | Content | Lines (approx) |
|----------|---------|----------------|
| `core/blueprints/buy/purchase.py` | Route handlers | ~200 |
| `core/blueprints/buy/purchase_preview.py` | Preview logic | ~200 |
| `core/blueprints/buy/autofill_purchase.py` | Autofill logic | ~250 |
| `core/blueprints/buy/price_lock.py` | Price lock helpers | ~200 |

**Rationale:** Each purchase operation is independent.

---

### PYTHON: `core/blueprints/cart/routes.py` (849 lines)

**Current Structure:**
- Lines 1-200: Add to cart endpoints
- Lines 201-400: Remove from cart
- Lines 401-600: Update quantities
- Lines 601-849: Cart data retrieval

**Split Map:**

| New File | Content | Lines (approx) |
|----------|---------|----------------|
| `core/blueprints/cart/routes.py` | Main routes | ~200 |
| `core/blueprints/cart/add_to_cart.py` | Add operations | ~200 |
| `core/blueprints/cart/remove_from_cart.py` | Remove operations | ~200 |
| `core/blueprints/cart/cart_data.py` | Data retrieval | ~250 |

**Rationale:** CRUD operations are distinct concerns.

---

### PYTHON: `services/notification_service.py` (806 lines)

**Current Structure:**
- Lines 1-60: Base notification creation
- Lines 61-200: notify_bid_filled()
- Lines 201-400: notify_listing_sold()
- Lines 401-600: notify_order_confirmed()
- Lines 601-806: Other notification types

**Split Map:**

| New File | Content | Lines (approx) |
|----------|---------|----------------|
| `services/notification_service.py` | Core + re-exports | ~100 |
| `services/notifications/base.py` | create_notification() | ~60 |
| `services/notifications/bid_notifications.py` | Bid-related | ~200 |
| `services/notifications/order_notifications.py` | Order-related | ~200 |
| `services/notifications/listing_notifications.py` | Listing-related | ~200 |

**Rationale:** Each notification type has distinct logic and metadata.

---

### CSS Strategy

Most CSS files are large but **cohesive** (single responsibility). Recommendation:

1. **Keep as-is but organize imports**: Files like `bids_tab.css` (1,677 lines) handle one component thoroughly
2. **Split only if responsibilities are mixed**: e.g., if a file has both layout and component styles
3. **Create index files** for easier imports:

```
static/css/
├── base.css                  # Site-wide
├── components/
│   └── index.css            # @import all component CSS
├── modals/
│   └── index.css            # @import all modal CSS
├── tabs/
│   └── index.css            # @import all tab CSS
└── pages/
    └── index.css            # @import all page CSS
```

**Rationale:** CSS files are already scoped correctly; reorganizing imports is sufficient.

---

### JavaScript Strategy

JS modals are already well-modularized. Largest concern is inline JS in templates.

**Split Priority:**
1. Extract inline JS from `sell.html` → `static/js/sell/*.js`
2. Extract inline JS from `view_bucket.html` → `static/js/bucket/*.js`
3. Keep modal JS files as-is (already modular)

---

## 3. Proposed Target Structure

```
metex/
├── core/
│   ├── __init__.py                    # App factory (keep ~400 lines max)
│   ├── blueprints/
│   │   ├── sell/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py              # Route handlers only (~300)
│   │   │   ├── photo_handler.py       # Photo processing (~200)
│   │   │   ├── set_items.py           # Set item logic (~200)
│   │   │   ├── bid_matching.py        # Auto-match (~200)
│   │   │   └── validation.py          # Form validation (~100)
│   │   ├── buy/
│   │   │   ├── __init__.py
│   │   │   ├── purchase.py            # Main route (~200)
│   │   │   ├── purchase_preview.py    # Preview (~200)
│   │   │   ├── autofill_purchase.py   # Autofill (~250)
│   │   │   └── price_lock.py          # Price lock (~200)
│   │   ├── cart/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py              # Main route (~200)
│   │   │   ├── add_to_cart.py         # Add ops (~200)
│   │   │   ├── remove_from_cart.py    # Remove ops (~200)
│   │   │   └── cart_data.py           # Data retrieval (~250)
│   │   └── [other blueprints...]
│   └── services/
│       ├── notifications/
│       │   ├── __init__.py            # Re-exports
│       │   ├── base.py                # Core creation
│       │   ├── bid_notifications.py   # Bid types
│       │   ├── order_notifications.py # Order types
│       │   └── listing_notifications.py
│       └── [other services...]
│
├── templates/
│   ├── base.html                      # (~400 lines after split)
│   ├── partials/
│   │   ├── _header.html
│   │   ├── _footer.html
│   │   ├── _flash_messages.html
│   │   ├── sell/
│   │   │   ├── _listing_mode_selector.html
│   │   │   ├── _item_fields.html
│   │   │   ├── _photo_upload.html
│   │   │   ├── _pricing_section.html
│   │   │   └── _sidebar.html
│   │   ├── account/
│   │   │   ├── _mobile_nav.html
│   │   │   ├── _desktop_sidebar.html
│   │   │   └── _modal_includes.html
│   │   ├── bucket/
│   │   │   ├── _gallery.html
│   │   │   ├── _item_specs.html
│   │   │   └── _seller_info.html
│   │   └── admin/
│   │       ├── _tab_nav.html
│   │       ├── _overview_tab.html
│   │       ├── _users_tab.html
│   │       └── [other tabs...]
│   ├── modals/                        # Already good structure
│   ├── tabs/                          # Already good structure
│   └── [page templates...]
│
├── static/
│   ├── css/
│   │   ├── base.css
│   │   ├── components/
│   │   ├── modals/                    # Keep existing structure
│   │   ├── tabs/                      # Keep existing structure
│   │   └── pages/
│   │       └── index.css              # Import aggregator
│   └── js/
│       ├── sell/                      # NEW - extracted from sell.html
│       │   ├── mode_switcher.js
│       │   ├── set_item_builder.js
│       │   ├── photo_handler.js
│       │   ├── sidebar_controller.js
│       │   └── form_submission.js
│       ├── bucket/                    # NEW - extracted from view_bucket.html
│       │   ├── gallery.js
│       │   └── chart_init.js
│       ├── modals/                    # Keep existing
│       ├── tabs/                      # Keep existing
│       └── admin/                     # Keep existing
│
├── services/                          # Re-export wrappers for backward compat
├── routes/                            # Re-export wrappers for backward compat
└── utils/                             # Keep existing
```

---

## 4. Refactor Priority Order

### Phase C-1: Extract Inline JavaScript (Highest Impact)
1. `templates/sell.html` → External JS files
2. `templates/view_bucket.html` → External JS files
3. Any remaining inline JS in other templates

### Phase C-2: Split Template Partials
1. `templates/sell.html` → Partials
2. `templates/admin/dashboard.html` → Tab partials
3. `templates/account.html` → Nav/sidebar partials
4. `templates/view_bucket.html` → Component partials

### Phase C-3: Split Python Routes
1. `core/blueprints/sell/routes.py` → Helpers
2. `core/blueprints/buy/purchase.py` → Operation modules
3. `core/blueprints/cart/routes.py` → CRUD modules
4. `services/notification_service.py` → Type-specific modules

### Phase C-4: Final Cleanup
1. Update imports throughout codebase
2. Add re-export wrappers for backward compatibility
3. Create DEVELOPER_ORIENTATION.md

---

## 5. Risk Assessment

| Risk | Mitigation |
|------|------------|
| Circular imports | Extract shared utilities first; use late imports |
| Broken template includes | Test each partial extraction individually |
| JS load order issues | Document dependencies; use DOMContentLoaded |
| Missing CSS selectors | No class renames; split only |
| Route endpoint changes | Preserve all endpoint names and URLs |

---

## 6. Files That Should NOT Be Split

| File | Lines | Reason |
|------|-------|--------|
| `scripts/create_schema.py` | 1,075 | Schema is cohesive; splitting breaks migration logic |
| Most CSS tab files | 600-1700 | Single responsibility (one tab); already scoped |
| Test files | varies | Tests should be comprehensive per feature |

---

## Approval Request

Please review this Phase A report and confirm:

1. **Split map accuracy** - Does the proposed split for each mega-file make sense?
2. **Priority order** - Should JS extraction (Phase C-1) come first?
3. **CSS strategy** - Is "keep but organize" acceptable for CSS?
4. **Any files to exclude** from refactoring?

Once approved, I will proceed to **Phase B** (Safety Net - test baseline + smoke tests).
