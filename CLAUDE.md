# Metex Development Guidelines for Claude

## Project Structure (Post-Refactor)

This codebase follows an industrial-grade modular structure. **Always maintain this structure when making changes.**

For detailed orientation, see: `docs/DEVELOPER_ORIENTATION.md`

### Directory Layout

```
metex/
├── app.py                    # Entry point (imports from core)
├── core/                     # Main application code
│   ├── __init__.py           # create_app() factory
│   ├── blueprints/           # Route modules by domain
│   │   ├── admin/            # Admin routes (8 modules)
│   │   ├── buy/              # Buy routes - split into:
│   │   │   ├── purchase.py       # Cart add, preview
│   │   │   └── direct_purchase.py # Direct buy, price locks
│   │   ├── bids/             # Bid routes (7 modules)
│   │   ├── account/          # Account routes (8 modules)
│   │   ├── auth/             # Auth routes
│   │   ├── cart/             # Cart routes - split into:
│   │   │   ├── routes.py         # Cart mutations
│   │   │   └── api.py            # Cart API endpoints
│   │   ├── checkout/         # Checkout routes
│   │   ├── api/              # General API routes
│   │   ├── listings/         # Listings routes
│   │   ├── sell/             # Sell routes - split into:
│   │   │   ├── routes.py         # Main dispatcher
│   │   │   ├── listing_creation.py # POST handling
│   │   │   └── accept_bid.py     # Bid acceptance
│   │   ├── messages/         # Messages routes
│   │   ├── ratings/          # Ratings routes
│   │   └── notifications/    # Notification routes
│   └── services/             # Business logic services
│       ├── ledger/           # Ledger service (8 modules)
│       └── analytics/        # Analytics service (6 modules)
├── routes/                   # Re-export wrappers ONLY (backward compat)
├── services/                 # Service modules
│   ├── notification_service.py  # Core + re-exports
│   └── notification_types.py    # notify_* functions
├── utils/                    # Utility functions
├── templates/                # Jinja2 templates
│   ├── admin/partials/       # Admin dashboard partials (10 files)
│   └── partials/account/     # Account page partials
├── static/
│   ├── css/                  # Stylesheets
│   └── js/
│       ├── sell/             # Extracted from sell.html
│       │   ├── mode_controller.js
│       │   └── sidebar_controller.js
│       └── bucket/           # Extracted from view_bucket.html
│           └── page_controller.js
└── docs/                     # Documentation
    └── DEVELOPER_ORIENTATION.md
```

## Rules for Code Changes

### Adding New Routes

1. **Add to `core/blueprints/[domain]/`** - NOT to `routes/`
2. Create new module if adding significant functionality
3. Import blueprint from `__init__.py`: `from . import [domain]_bp`
4. Register route with: `@[domain]_bp.route('/path')`

Example:
```python
# core/blueprints/buy/new_feature.py
from . import buy_bp

@buy_bp.route('/new_feature')
def new_feature():
    pass
```

### Adding New Services

1. **Add to `core/services/[domain]/`** - NOT to `services/`
2. Use late binding for database connections:
```python
import database

def get_db_connection():
    """Wrapper for late binding in tests"""
    return database.get_db_connection()
```

### File Size Limits

- Keep modules under 500 lines
- Split large files into focused sub-modules
- Each module should have a single responsibility

### Import Patterns

```python
# Good - explicit imports
from core.blueprints.buy import buy_bp
from core.services.ledger import LedgerService

# Bad - star imports
from core.blueprints.buy import *
```

### Backward Compatibility

- Keep `routes/` and `services/` files as thin re-export wrappers
- Original import paths must continue to work
- Example re-export wrapper:
```python
# routes/buy_routes.py
from core.blueprints.buy import buy_bp
__all__ = ['buy_bp']
```

## Testing

- Run tests after every change: `python -m pytest tests/ -v`
- All 186 tests must pass
- Test files are in `tests/`

## Key Files Reference

| Purpose | Location |
|---------|----------|
| App factory | `core/__init__.py` |
| Blueprint registration | `core/__init__.py` (in create_app) |
| Database connection | `database.py` |
| Route category options | `routes/category_options.py` |
| Auth decorators | `utils/auth_utils.py` |
