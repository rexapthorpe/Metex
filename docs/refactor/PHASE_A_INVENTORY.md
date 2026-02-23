# PHASE A: Inventory & Mapping

**Generated**: 2026-01-15
**Status**: Industrial-Grade Maintainability Refactor

This document provides the complete inventory of all files > 600 lines and detailed split maps for each mega-file.

---

## Executive Summary

| Category | Files > 600 Lines | Largest File | Target After Refactor |
|----------|-------------------|--------------|----------------------|
| CSS | 24 files | `admin/dashboard.css` (5,003 lines) | < 600 lines each |
| JavaScript | 15 files | `admin/dashboard.js` (3,248 lines) | < 600 lines each |
| Python | 15 files | `test_security_p0.py` (1,477 lines) | < 400 lines each |
| HTML Templates | 6 files | `sell.html` (2,880 lines) | Assembled from partials |

**Total: 60 files requiring refactoring**

---

## Current Directory Structure

```
metex/
├── app.py                      # Entry point
├── core/
│   ├── __init__.py             # App factory (709 lines) - OVER LIMIT
│   ├── blueprints/
│   │   ├── admin/              # 8 modules
│   │   ├── buy/                # 6 modules
│   │   ├── bids/               # 7 modules
│   │   ├── account/            # 8 modules
│   │   ├── listings/           # routes.py (968 lines) - OVER LIMIT
│   │   ├── sell/               # routes.py (961 lines) - OVER LIMIT
│   │   ├── cart/               # routes.py (849 lines) - OVER LIMIT
│   │   ├── checkout/           # routes.py (667 lines) - OVER LIMIT
│   │   └── ...
│   └── services/ledger/        # escrow_control.py (697 lines) - OVER LIMIT
├── routes/                     # Re-export wrappers (OK)
├── services/
│   ├── notification_service.py # (806 lines) - OVER LIMIT
│   └── pricing_service.py      # (603 lines) - OVER LIMIT
├── utils/
│   └── security.py             # (648 lines) - OVER LIMIT
├── templates/
│   ├── base.html               # (621 lines) - OVER LIMIT
│   ├── sell.html               # (2,880 lines) - MEGA FILE
│   ├── account.html            # (1,345 lines) - MEGA FILE
│   ├── view_bucket.html        # (1,180 lines) - MEGA FILE
│   ├── admin/dashboard.html    # (1,665 lines) - MEGA FILE
│   ├── modals/                 # 39 modal files (most OK)
│   └── tabs/                   # 11 tab files (most OK)
├── static/
│   ├── css/
│   │   ├── base.css            # (1,163 lines) - OVER LIMIT
│   │   ├── bucket.css          # (2,460 lines) - MEGA FILE
│   │   ├── sell.css            # (1,803 lines) - MEGA FILE
│   │   ├── admin/dashboard.css # (5,003 lines) - MEGA FILE
│   │   ├── modals/             # 33 files, several over limit
│   │   └── tabs/               # 11 files, several over limit
│   └── js/
│       ├── sell.js             # (724 lines) - OVER LIMIT
│       ├── admin/dashboard.js  # (3,248 lines) - MEGA FILE
│       ├── modals/             # 39 files, several over limit
│       └── tabs/               # 10 files
└── tests/                      # Several large test files (acceptable)
```

---

## Target Directory Structure (Post-Refactor)

```
metex/
├── app.py                           # Entry point (unchanged)
├── core/
│   ├── __init__.py                  # App factory (<400 lines)
│   ├── config.py                    # NEW: Config loading extracted
│   ├── extensions.py                # NEW: Flask extensions setup
│   ├── blueprints/
│   │   ├── admin/                   # 8+ modules (each <400 lines)
│   │   ├── listings/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py            # GET/render routes (<300 lines)
│   │   │   ├── api.py               # JSON API routes (<300 lines)
│   │   │   └── helpers.py           # Shared helpers (<200 lines)
│   │   ├── sell/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py            # Page routes (<300 lines)
│   │   │   ├── api.py               # API routes (<300 lines)
│   │   │   └── validation.py        # Form validation (<200 lines)
│   │   ├── cart/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py            # Main cart routes (<300 lines)
│   │   │   ├── api.py               # Cart API (<300 lines)
│   │   │   └── operations.py        # Cart logic (<200 lines)
│   │   └── checkout/
│   │       ├── __init__.py
│   │       ├── routes.py            # Checkout pages (<300 lines)
│   │       └── api.py               # Checkout API (<200 lines)
│   └── services/ledger/
│       ├── escrow_control.py        # (<400 lines)
│       └── escrow_operations.py     # NEW: Extracted operations
├── services/
│   ├── notification_service.py      # (<400 lines)
│   ├── notification_helpers.py      # NEW: Extracted helpers
│   ├── pricing_service.py           # (<400 lines)
│   └── pricing_calculations.py      # NEW: Extracted calculations
├── utils/
│   ├── security.py                  # (<400 lines)
│   └── authorization.py             # NEW: Extracted auth helpers
├── templates/
│   ├── base.html                    # (<300 lines, uses partials)
│   ├── partials/                    # NEW: Extracted components
│   │   ├── header.html
│   │   ├── footer.html
│   │   ├── flash_messages.html
│   │   ├── mobile_nav.html
│   │   └── scripts_footer.html
│   ├── components/                  # NEW: Reusable UI blocks
│   │   ├── gallery.html
│   │   ├── specs_grid.html
│   │   ├── price_display.html
│   │   └── quantity_dial.html
│   ├── pages/
│   │   ├── sell/                    # NEW: Sell page sections
│   │   │   ├── sell.html            # Main (assembles partials)
│   │   │   ├── _mode_selector.html
│   │   │   ├── _category_fields.html
│   │   │   ├── _pricing_section.html
│   │   │   ├── _photos_section.html
│   │   │   └── _set_items_section.html
│   │   ├── bucket/                  # NEW: Bucket page sections
│   │   │   ├── view_bucket.html
│   │   │   ├── _gallery.html
│   │   │   ├── _specs_tile.html
│   │   │   ├── _price_chart.html
│   │   │   └── _purchase_panel.html
│   │   └── account/                 # NEW: Account page sections
│   │       ├── account.html
│   │       └── _sidebar.html
│   ├── admin/
│   │   ├── dashboard.html           # (<400 lines, uses partials)
│   │   ├── _overview_tab.html
│   │   ├── _users_tab.html
│   │   ├── _listings_tab.html
│   │   └── ...
│   ├── modals/                      # Existing (mostly OK)
│   └── tabs/                        # Existing (mostly OK)
├── static/
│   ├── css/
│   │   ├── base/                    # NEW: Core styles split
│   │   │   ├── reset.css
│   │   │   ├── typography.css
│   │   │   ├── colors.css
│   │   │   └── layout.css
│   │   ├── components/              # NEW: Component styles
│   │   │   ├── buttons.css
│   │   │   ├── forms.css
│   │   │   ├── cards.css
│   │   │   ├── gallery.css
│   │   │   └── dialogs.css
│   │   ├── pages/
│   │   │   ├── bucket/              # NEW: Bucket page split
│   │   │   │   ├── bucket.css       # Main imports
│   │   │   │   ├── _gallery.css
│   │   │   │   ├── _specs.css
│   │   │   │   ├── _pricing.css
│   │   │   │   └── _purchase.css
│   │   │   ├── sell/                # NEW: Sell page split
│   │   │   │   ├── sell.css
│   │   │   │   ├── _mode_selector.css
│   │   │   │   ├── _form_fields.css
│   │   │   │   └── _photos.css
│   │   │   └── ...
│   │   ├── admin/
│   │   │   ├── dashboard/           # NEW: Admin split
│   │   │   │   ├── dashboard.css    # Main imports
│   │   │   │   ├── _header.css
│   │   │   │   ├── _tabs.css
│   │   │   │   ├── _stats.css
│   │   │   │   ├── _tables.css
│   │   │   │   └── _modals.css
│   │   │   └── ...
│   │   ├── modals/                  # Existing
│   │   └── tabs/                    # Existing
│   └── js/
│       ├── core/                    # NEW: Core utilities
│       │   ├── csrf.js
│       │   ├── api.js
│       │   └── utils.js
│       ├── components/              # NEW: Reusable components
│       │   ├── gallery.js
│       │   ├── quantity-dial.js
│       │   └── modal-base.js
│       ├── pages/
│       │   ├── sell/                # NEW: Sell page split
│       │   │   ├── sell.js          # Main orchestrator
│       │   │   ├── mode-selector.js
│       │   │   ├── category-cascade.js
│       │   │   ├── pricing-mode.js
│       │   │   ├── photo-upload.js
│       │   │   └── set-items.js
│       │   └── ...
│       ├── admin/
│       │   ├── dashboard/           # NEW: Admin split
│       │   │   ├── dashboard.js     # Main orchestrator
│       │   │   ├── overview-tab.js
│       │   │   ├── users-tab.js
│       │   │   ├── listings-tab.js
│       │   │   └── ...
│       │   └── analytics.js
│       ├── modals/                  # Existing
│       └── tabs/                    # Existing
└── tests/                           # Keep as-is (test files can be longer)
```

---

## Detailed Split Maps

### 1. Python Routes

#### 1.1 `core/blueprints/listings/routes.py` (968 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `routes.py` | ~300 | `edit_listing()`, `cancel_listing()`, page renders | Page routes |
| `api.py` | ~350 | `get_listing_details()`, JSON endpoints | API separation |
| `helpers.py` | ~200 | `save_uploaded_photo()`, `update_set_items()`, `handle_set_item_photos()`, validation | Reusable helpers |

**Migration Pattern:**
```python
# api.py
from . import listings_bp
from .helpers import save_uploaded_photo, update_set_items

@listings_bp.route('/api/listings/<int:listing_id>/details')
def get_listing_details(listing_id):
    ...
```

#### 1.2 `core/blueprints/sell/routes.py` (961 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `routes.py` | ~300 | `sell()` main route (slim), page render | Page handler |
| `validation.py` | ~250 | Form validation, numismatic rules, set validation | Validation logic |
| `create_listing.py` | ~300 | Listing creation logic, DB inserts | Business logic |

#### 1.3 `core/blueprints/cart/routes.py` (849 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `routes.py` | ~300 | Page routes, cart view | Page handlers |
| `api.py` | ~300 | `get_cart_sellers()`, `get_price_breakdown()` | JSON API |
| `operations.py` | ~200 | `remove_seller_from_cart()` logic, refill logic | Cart operations |

#### 1.4 `core/blueprints/checkout/routes.py` (667 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `routes.py` | ~350 | Page routes, confirmation | Page handlers |
| `api.py` | ~250 | Address updates, payment API | JSON API |

#### 1.5 `core/blueprints/buy/purchase.py` (887 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `purchase.py` | ~400 | Main purchase routes | Page handlers |
| `price_lock.py` | ~300 | Price lock logic, refresh | Price locking |
| `direct_buy.py` | ~200 | Direct purchase flow | Separate flow |

#### 1.6 `core/blueprints/account/account_page.py` (790 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `account_page.py` | ~400 | Main page render, tab data | Page handler |
| `account_api.py` | ~300 | Settings updates, JSON endpoints | API routes |

#### 1.7 `core/blueprints/admin/reports.py` (730 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `reports.py` | ~400 | Report viewing, listing | Report pages |
| `reports_api.py` | ~250 | Status updates, actions | Report actions |

#### 1.8 `core/blueprints/admin/users.py` (708 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `users.py` | ~400 | User listing, details | User management |
| `users_actions.py` | ~250 | Ban, freeze, delete actions | User actions |

#### 1.9 `core/__init__.py` (709 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `__init__.py` | ~300 | `create_app()`, blueprint registration | App factory |
| `config.py` | ~150 | Config loading, env vars | Configuration |
| `extensions.py` | ~100 | CSRF, Limiter, ProxyFix setup | Extensions |
| `security_headers.py` | ~100 | `@app.after_request` security headers | Security |

---

### 2. Services

#### 2.1 `services/notification_service.py` (806 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `notification_service.py` | ~400 | Main notify functions | Core service |
| `notification_templates.py` | ~200 | Message templates, formatting | Templates |
| `notification_delivery.py` | ~150 | Email sending, DB writes | Delivery |

#### 2.2 `services/pricing_service.py` (603 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `pricing_service.py` | ~350 | `get_effective_price()`, main functions | Core pricing |
| `pricing_calculations.py` | ~200 | Spread calculations, fee logic | Calculations |

#### 2.3 `core/services/ledger/escrow_control.py` (697 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `escrow_control.py` | ~350 | Main escrow functions | Escrow control |
| `escrow_operations.py` | ~300 | Hold, release, refund operations | Operations |

---

### 3. Utilities

#### 3.1 `utils/security.py` (648 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `security.py` | ~300 | Core security, `AuthorizationError` | Core security |
| `authorization.py` | ~300 | All `authorize_*()` helpers | Authorization |

---

### 4. HTML Templates

#### 4.1 `templates/sell.html` (2,880 lines) - HIGHEST PRIORITY

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `pages/sell/sell.html` | ~200 | Shell: extends base, includes partials | Main template |
| `pages/sell/_mode_selector.html` | ~100 | Listing mode radio buttons | Mode selection |
| `pages/sell/_title_description.html` | ~80 | Title/description fields | Isolated fields |
| `pages/sell/_category_fields.html` | ~300 | Metal, product, weight, etc. dropdowns | Category spec |
| `pages/sell/_grading_section.html` | ~150 | Grading fields | Grading |
| `pages/sell/_pricing_section.html` | ~200 | Pricing mode, premium to spot | Pricing |
| `pages/sell/_photos_section.html` | ~150 | Photo upload grid | Photos |
| `pages/sell/_quantity_dial.html` | ~100 | Quantity selector | Quantity |
| `pages/sell/_set_items_section.html` | ~400 | Set item builder | Set listings |
| `pages/sell/_sidebar.html` | ~200 | Right sidebar preview | Preview |
| `pages/sell/_hidden_fields.html` | ~50 | Hidden form inputs | Form data |
| `pages/sell/_scripts.html` | ~400 | Page-specific JS includes | Scripts |

**Template Assembly Pattern:**
```jinja2
{# pages/sell/sell.html #}
{% extends "base.html" %}
{% block content %}
<form id="sellForm" ...>
  {% include 'pages/sell/_mode_selector.html' %}
  {% include 'pages/sell/_title_description.html' %}
  {% include 'pages/sell/_category_fields.html' %}
  {% include 'pages/sell/_grading_section.html' %}
  {% include 'pages/sell/_pricing_section.html' %}
  {% include 'pages/sell/_photos_section.html' %}
  {% include 'pages/sell/_quantity_dial.html' %}
  {% include 'pages/sell/_set_items_section.html' %}
  {% include 'pages/sell/_hidden_fields.html' %}
</form>
{% include 'pages/sell/_sidebar.html' %}
{% endblock %}
{% block page_scripts %}
{% include 'pages/sell/_scripts.html' %}
{% endblock %}
```

#### 4.2 `templates/admin/dashboard.html` (1,665 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `admin/dashboard.html` | ~150 | Shell, tab navigation | Main template |
| `admin/_header.html` | ~50 | Admin header | Header |
| `admin/_tab_nav.html` | ~50 | Tab buttons | Navigation |
| `admin/_overview_tab.html` | ~200 | Stats cards, charts | Overview |
| `admin/_users_tab.html` | ~200 | Users table, search | Users |
| `admin/_listings_tab.html` | ~150 | Listings table | Listings |
| `admin/_buckets_tab.html` | ~100 | Buckets view | Buckets |
| `admin/_transactions_tab.html` | ~150 | Transactions | Transactions |
| `admin/_ledger_tab.html` | ~150 | Ledger entries | Ledger |
| `admin/_disputes_tab.html` | ~150 | Disputes | Disputes |
| `admin/_messages_tab.html` | ~100 | Admin messages | Messages |
| `admin/_system_tab.html` | ~100 | System settings | System |
| `admin/_modals.html` | ~200 | Admin modals | Modals |

#### 4.3 `templates/account.html` (1,345 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `account.html` | ~200 | Shell, modal includes, CSS links | Main template |
| `pages/account/_mobile_nav.html` | ~150 | Mobile navigation drawer | Mobile nav |
| `pages/account/_sidebar.html` | ~150 | Desktop sidebar | Sidebar |
| `pages/account/_tab_content.html` | ~100 | Tab container structure | Tab area |

Note: Most content is already in `tabs/*.html` files - just need to extract includes and nav.

#### 4.4 `templates/view_bucket.html` (1,180 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `pages/bucket/view_bucket.html` | ~150 | Shell, layout structure | Main template |
| `pages/bucket/_gallery.html` | ~150 | Image gallery, thumbs | Gallery |
| `pages/bucket/_specs_tile.html` | ~200 | Item specifications | Specs |
| `pages/bucket/_set_items_list.html` | ~100 | Set items (if applicable) | Set items |
| `pages/bucket/_price_chart.html` | ~100 | Price history chart | Chart |
| `pages/bucket/_purchase_panel.html` | ~200 | Buy/bid panel, quantity | Purchase |
| `pages/bucket/_sellers_section.html` | ~100 | Sellers list | Sellers |
| `pages/bucket/_related.html` | ~100 | Related items | Related |

#### 4.5 `templates/base.html` (621 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `base.html` | ~200 | Core structure | Main base |
| `partials/head.html` | ~80 | `<head>` content, meta, CSS | Head section |
| `partials/header.html` | ~100 | Site header (extracted) | Header |
| `partials/footer.html` | ~50 | Site footer (extracted) | Footer |
| `partials/flash_messages.html` | ~30 | Flash message display | Flash |
| `partials/scripts_footer.html` | ~100 | Common JS includes | Scripts |

---

### 5. CSS Files

#### 5.1 `static/css/admin/dashboard.css` (5,003 lines) - HIGHEST PRIORITY

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `admin/dashboard/dashboard.css` | ~100 | Imports all partials | Main file |
| `admin/dashboard/_variables.css` | ~80 | CSS variables, colors | Variables |
| `admin/dashboard/_layout.css` | ~150 | Grid, flex layouts | Layout |
| `admin/dashboard/_header.css` | ~150 | Admin header styles | Header |
| `admin/dashboard/_tabs.css` | ~200 | Tab navigation | Tabs |
| `admin/dashboard/_stats.css` | ~400 | Stat cards, metrics | Stats |
| `admin/dashboard/_tables.css` | ~500 | Data tables | Tables |
| `admin/dashboard/_users.css` | ~400 | Users tab styles | Users |
| `admin/dashboard/_listings.css` | ~300 | Listings tab | Listings |
| `admin/dashboard/_transactions.css` | ~300 | Transactions | Transactions |
| `admin/dashboard/_ledger.css` | ~300 | Ledger styles | Ledger |
| `admin/dashboard/_disputes.css` | ~300 | Disputes | Disputes |
| `admin/dashboard/_messages.css` | ~200 | Messages | Messages |
| `admin/dashboard/_system.css` | ~200 | System settings | System |
| `admin/dashboard/_modals.css` | ~400 | Admin modals | Modals |
| `admin/dashboard/_forms.css` | ~300 | Form elements | Forms |
| `admin/dashboard/_responsive.css` | ~400 | Media queries | Responsive |

**CSS Import Pattern:**
```css
/* admin/dashboard/dashboard.css */
@import '_variables.css';
@import '_layout.css';
@import '_header.css';
@import '_tabs.css';
@import '_stats.css';
@import '_tables.css';
/* ... etc */
```

#### 5.2 `static/css/bucket.css` (2,460 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `pages/bucket/bucket.css` | ~100 | Imports | Main file |
| `pages/bucket/_layout.css` | ~200 | Page layout, columns | Layout |
| `pages/bucket/_gallery.css` | ~300 | Gallery, thumbs | Gallery |
| `pages/bucket/_specs.css` | ~300 | Specs tile styles | Specs |
| `pages/bucket/_pricing.css` | ~300 | Price display, badges | Pricing |
| `pages/bucket/_purchase.css` | ~400 | Purchase panel, dial | Purchase |
| `pages/bucket/_sellers.css` | ~200 | Sellers list | Sellers |
| `pages/bucket/_responsive.css` | ~400 | Media queries | Responsive |

#### 5.3 `static/css/sell.css` (1,803 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `pages/sell/sell.css` | ~100 | Imports | Main file |
| `pages/sell/_layout.css` | ~150 | Page layout | Layout |
| `pages/sell/_mode_selector.css` | ~200 | Mode cards | Mode |
| `pages/sell/_form_fields.css` | ~400 | Input styling | Forms |
| `pages/sell/_photos.css` | ~250 | Photo upload grid | Photos |
| `pages/sell/_sidebar.css` | ~200 | Preview sidebar | Sidebar |
| `pages/sell/_set_items.css` | ~300 | Set builder | Sets |
| `pages/sell/_responsive.css` | ~200 | Media queries | Responsive |

#### 5.4 `static/css/base.css` (1,163 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `base/base.css` | ~100 | Imports | Main file |
| `base/_reset.css` | ~100 | CSS reset | Reset |
| `base/_typography.css` | ~150 | Fonts, text styles | Typography |
| `base/_colors.css` | ~100 | Color variables | Colors |
| `base/_layout.css` | ~200 | Container, grid | Layout |
| `base/_utilities.css` | ~200 | Utility classes | Utilities |
| `base/_animations.css` | ~100 | Transitions, keyframes | Animations |

#### 5.5 Large Modal CSS Files

| File | Lines | Split Into |
|------|-------|------------|
| `modals/bid_modal.css` | 1,432 | `_layout.css`, `_steps.css`, `_pricing.css`, `_responsive.css` |
| `modals/edit_listing_modal.css` | 1,110 | `_layout.css`, `_form.css`, `_photos.css`, `_responsive.css` |
| `modals/accept_bid_modals.css` | 1,085 | `_base.css`, `_confirm.css`, `_success.css` |
| `modals/cancel_order_modal.css` | 932 | `_layout.css`, `_form.css`, `_status.css` |

#### 5.6 Large Tab CSS Files

| File | Lines | Split Into |
|------|-------|------------|
| `tabs/bids_tab.css` | 1,677 | `_layout.css`, `_cards.css`, `_filters.css`, `_responsive.css` |
| `tabs/portfolio_tab.css` | 1,123 | `_layout.css`, `_chart.css`, `_items.css`, `_responsive.css` |
| `tabs/orders_tab.css` | 1,032 | `_layout.css`, `_cards.css`, `_actions.css`, `_responsive.css` |
| `tabs/sold_tab.css` | 1,016 | `_layout.css`, `_cards.css`, `_shipping.css`, `_responsive.css` |

---

### 6. JavaScript Files

#### 6.1 `static/js/admin/dashboard.js` (3,248 lines) - HIGHEST PRIORITY

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `admin/dashboard/dashboard.js` | ~200 | Init, tab switching, orchestration | Main file |
| `admin/dashboard/overview-tab.js` | ~400 | Stats loading, charts | Overview |
| `admin/dashboard/users-tab.js` | ~400 | User table, search, actions | Users |
| `admin/dashboard/listings-tab.js` | ~300 | Listings management | Listings |
| `admin/dashboard/buckets-tab.js` | ~200 | Buckets view | Buckets |
| `admin/dashboard/transactions-tab.js` | ~300 | Transaction table | Transactions |
| `admin/dashboard/ledger-tab.js` | ~300 | Ledger entries | Ledger |
| `admin/dashboard/disputes-tab.js` | ~300 | Dispute handling | Disputes |
| `admin/dashboard/messages-tab.js` | ~200 | Message management | Messages |
| `admin/dashboard/system-tab.js` | ~200 | System settings | System |
| `admin/dashboard/modals.js` | ~300 | Modal handlers | Modals |
| `admin/dashboard/api.js` | ~200 | API calls | API |

#### 6.2 `static/js/admin/analytics.js` (1,548 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `admin/analytics/analytics.js` | ~200 | Init, orchestration | Main file |
| `admin/analytics/charts.js` | ~500 | Chart.js configurations | Charts |
| `admin/analytics/metrics.js` | ~300 | Metrics calculations | Metrics |
| `admin/analytics/data-loading.js` | ~300 | API fetching | Data |
| `admin/analytics/filters.js` | ~200 | Date range, filters | Filters |

#### 6.3 `static/js/modals/bid_modal.js` (1,156 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `modals/bid_modal/bid_modal.js` | ~200 | Init, orchestration | Main file |
| `modals/bid_modal/steps.js` | ~300 | Step navigation | Steps |
| `modals/bid_modal/pricing.js` | ~300 | Price calculations | Pricing |
| `modals/bid_modal/validation.js` | ~200 | Form validation | Validation |
| `modals/bid_modal/submit.js` | ~150 | Submit handling | Submit |

#### 6.4 `static/js/modals/buy_item_modal.js` (1,066 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `modals/buy_item_modal.js` | ~400 | Core modal logic | Main |
| `modals/buy_item_quantity.js` | ~300 | Quantity dial, updates | Quantity |
| `modals/buy_item_pricing.js` | ~300 | Price display, refresh | Pricing |

#### 6.5 `static/js/modals/edit_listing_modal.js` (987 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `modals/edit_listing_modal.js` | ~400 | Core modal | Main |
| `modals/edit_listing_photos.js` | ~300 | Photo management | Photos |
| `modals/edit_listing_form.js` | ~250 | Form handling | Form |

#### 6.6 `static/js/sell.js` (724 lines)

| New File | Lines | What Moves | Rationale |
|----------|-------|------------|-----------|
| `pages/sell/sell.js` | ~150 | Init, orchestration | Main |
| `pages/sell/mode-selector.js` | ~100 | Mode switching | Mode |
| `pages/sell/category-cascade.js` | ~150 | Dropdown cascades | Categories |
| `pages/sell/pricing-mode.js` | ~100 | Pricing UI | Pricing |
| `pages/sell/photo-upload.js` | ~100 | Photo handling | Photos |
| `pages/sell/set-items.js` | ~150 | Set builder | Sets |

#### 6.7 Other Large JS Files

| File | Lines | Split Into |
|------|-------|------------|
| `tabs/portfolio_tab.js` | 937 | `_init.js`, `_chart.js`, `_items.js`, `_exclusions.js` |
| `modals/bid_confirm_modal.js` | 838 | `_init.js`, `_display.js`, `_submit.js` |
| `bucket_price_chart.js` | 644 | `_init.js`, `_data.js`, `_render.js`, `_interactions.js` |
| `checkout_page.js` | 627 | `_init.js`, `_address.js`, `_payment.js`, `_submit.js` |
| `modals/accept_bid_modals.js` | 620 | `_init.js`, `_accept.js`, `_success.js` |

---

## Refactoring Priorities

### Tier 1: Highest Impact (Do First)
1. **`admin/dashboard.css`** - 5,003 lines, blocks admin work
2. **`admin/dashboard.js`** - 3,248 lines, blocks admin work
3. **`sell.html`** - 2,880 lines, most complex form
4. **`bucket.css`** - 2,460 lines, main buyer page
5. **`admin/dashboard.html`** - 1,665 lines, admin UI

### Tier 2: High Impact
6. `sell.css` - 1,803 lines
7. `bids_tab.css` - 1,677 lines
8. `admin/analytics.js` - 1,548 lines
9. `checkout_page.css` - 1,476 lines
10. `bid_modal.css` - 1,432 lines

### Tier 3: Medium Impact (Python Routes)
11. `listings/routes.py` - 968 lines
12. `sell/routes.py` - 961 lines
13. `cart/routes.py` - 849 lines
14. `notification_service.py` - 806 lines
15. `account_page.py` - 790 lines

### Tier 4: Clean-up
- Remaining modal CSS/JS files
- Tab CSS files
- Service files
- Utility files

---

## Backward Compatibility Requirements

### Python
- All blueprint names must remain unchanged
- All route URLs must remain unchanged
- Re-export from original module paths:
```python
# core/blueprints/listings/routes.py (original)
from .api import get_listing_details  # Re-export for compatibility
```

### Templates
- Keep original template names, add partials internally:
```jinja2
{# templates/sell.html - keep this file #}
{% extends "base.html" %}
{% block content %}
{% include 'pages/sell/_content.html' %}
{% endblock %}
```

### CSS/JS
- Keep original filenames as entry points
- Use `@import` for CSS
- Use module pattern or maintain global scope for JS

---

## Test Requirements Before Refactor

1. **Route smoke tests**: Verify all routes return expected status codes
2. **Template render tests**: Ensure templates render without error
3. **JSON shape tests**: Verify API endpoints return expected structure
4. **Critical flow tests**: Login, buy, sell, checkout paths work

---

## Next Steps

**PHASE B**: Run test suite baseline and add minimal safety net tests
**PHASE C**: Execute refactors in priority order, one module at a time

