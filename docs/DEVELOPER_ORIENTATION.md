# Metex Developer Orientation

This document provides an overview of the Metex codebase structure after the maintainability refactor. Use this as your guide when navigating or modifying the code.

## Project Structure Overview

```
metex/
├── app.py                    # Entry point - imports create_app from core
├── core/                     # Main application code (NEW)
│   ├── __init__.py           # create_app() factory, blueprint registration
│   ├── blueprints/           # Route modules organized by domain
│   │   ├── admin/            # Admin dashboard routes
│   │   ├── buy/              # Buy/purchase routes (split into 5 modules)
│   │   ├── bids/             # Bid management routes
│   │   ├── account/          # User account routes
│   │   ├── auth/             # Authentication routes
│   │   ├── cart/             # Cart routes (split into 2 modules)
│   │   ├── checkout/         # Checkout routes
│   │   ├── sell/             # Sell/listing routes (split into 3 modules)
│   │   ├── api/              # General API routes
│   │   ├── listings/         # Listing management routes
│   │   ├── messages/         # Messaging routes
│   │   ├── ratings/          # Rating routes
│   │   └── notifications/    # Notification routes
│   └── services/             # Business logic services
├── routes/                   # Backward-compatibility re-exports ONLY
├── services/                 # Service modules (some split)
├── utils/                    # Utility functions
├── templates/                # Jinja2 templates (partials in subfolders)
│   ├── admin/partials/       # Admin dashboard tab partials
│   └── partials/account/     # Account page partials
├── static/
│   ├── css/                  # Stylesheets
│   └── js/                   # JavaScript
│       ├── sell/             # Sell page JS modules (extracted)
│       └── bucket/           # Bucket page JS modules (extracted)
└── tests/                    # Test files
```

## Key Architectural Decisions

### 1. Blueprint Organization

Routes are organized into domain-specific blueprints under `core/blueprints/`. Each domain has its own folder with an `__init__.py` that creates and exports the blueprint.

**Pattern:**
```python
# core/blueprints/sell/__init__.py
from flask import Blueprint
sell_bp = Blueprint('sell', __name__)

from . import routes  # Imports register routes with sell_bp
```

### 2. Large Route File Splitting

Large route files have been split into focused modules:

| Blueprint | Modules | Purpose |
|-----------|---------|---------|
| `sell/` | `routes.py` | Main dispatcher, tracking upload |
| | `listing_creation.py` | POST handling for new listings |
| | `accept_bid.py` | Bid acceptance route |
| `buy/` | `purchase.py` | Cart add, preview operations |
| | `direct_purchase.py` | Direct buy, price lock refresh |
| `cart/` | `routes.py` | Cart mutation operations |
| | `api.py` | Cart API endpoints |

### 3. Service Layer Splitting

Large service files have been split while maintaining backward compatibility:

| Service | Modules | Purpose |
|---------|---------|---------|
| `notification_service.py` | Core | create_notification, get/mark/delete |
| `notification_types.py` | Types | notify_bid_filled, notify_listing_sold, etc. |

**Backward Compatibility:** `notification_service.py` re-exports all functions from `notification_types.py`, so existing imports continue to work.

### 4. Template Partials

Large templates have been split into partials using Jinja2 includes:

| Template | Partials Location | Contents |
|----------|-------------------|----------|
| `admin/dashboard.html` | `admin/partials/` | 10 tab partials + modals |
| `account.html` | `partials/account/` | Mobile nav partial |

### 5. JavaScript Extraction

Inline JavaScript has been extracted to external files:

| Template | Extracted To | Lines |
|----------|--------------|-------|
| `sell.html` | `js/sell/mode_controller.js` | 1,103 |
| | `js/sell/sidebar_controller.js` | 1,012 |
| `view_bucket.html` | `js/bucket/page_controller.js` | 274 |

## Adding New Code

### Adding a New Route

1. **Add to the appropriate blueprint** in `core/blueprints/[domain]/`
2. **Create a new module** if adding significant functionality
3. **Import in the blueprint's routes.py** to register the route

```python
# core/blueprints/buy/new_feature.py
from . import buy_bp

@buy_bp.route('/new_feature')
def new_feature():
    pass

# Then in core/blueprints/buy/routes.py (or __init__.py):
from . import new_feature  # Registers the route
```

### Adding a New Service

1. **Add to `services/`** directory
2. **Use late binding** for database connections:

```python
from database import get_db_connection

def my_service_function():
    conn = get_db_connection()  # Late binding
    # ...
```

### Adding Template Partials

1. **Create partial** in `templates/partials/[domain]/` or `templates/[domain]/partials/`
2. **Include in parent** using `{% include 'path/to/partial.html' %}`

## File Size Guidelines

| File Type | Target Size | Max Size |
|-----------|-------------|----------|
| Route modules | < 300 lines | 500 lines |
| Service modules | < 400 lines | 600 lines |
| Templates | < 500 lines | 800 lines |
| JS modules | < 500 lines | 800 lines |

## Backward Compatibility

The `routes/` directory contains **re-export wrappers** for backward compatibility. These should NOT contain route logic - only imports.

```python
# routes/sell_routes.py - Example wrapper
from core.blueprints.sell import sell_bp
from core.blueprints.sell.listing_creation import allowed_file
__all__ = ['sell_bp', 'allowed_file']
```

## Testing

Run tests after any changes:
```bash
python -m pytest tests/ -v
```

Core business logic tests (ledger, fees, escrow) should always pass.

## Quick Reference

### Finding Code

| To find... | Look in... |
|------------|------------|
| Sell page routes | `core/blueprints/sell/` |
| Buy/purchase routes | `core/blueprints/buy/` |
| Cart operations | `core/blueprints/cart/` |
| Notification logic | `services/notification_service.py` |
| Admin dashboard | `core/blueprints/admin/` |
| Template partials | `templates/*/partials/` |

### Key Files

| Purpose | File |
|---------|------|
| App factory | `core/__init__.py` |
| Database connection | `database.py` |
| Category options | `routes/category_options.py` |
| Auth decorators | `utils/auth_utils.py` |
| Pricing calculations | `services/pricing_service.py` |

## Refactor History

This codebase underwent a maintainability refactor with these phases:

1. **Phase A**: Inventory and mapping of large files
2. **Phase B**: Test baseline establishment
3. **Phase C-1**: JavaScript extraction from templates
4. **Phase C-2**: Template partial extraction
5. **Phase C-3**: Python route module splitting
6. **Phase C-4**: Documentation and cleanup

**Key Principle**: Zero behavior change - all refactoring was structural only.
