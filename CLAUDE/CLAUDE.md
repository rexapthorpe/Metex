# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MetEx (Metals Exchange) is a Flask-based marketplace application for buying and selling precious metals (coins, bars, rounds). The platform supports direct purchases via shopping cart, bidding on categories, seller ratings, messaging between users, and order tracking.

## Development Commands

### Running the Application
```bash
python app.py
```
The app runs on `http://127.0.0.1:5000` by default with debug mode enabled.

### Virtual Environment
The project uses a Python virtual environment in `venv/`:
```bash
# Windows
venv\Scripts\activate

# Unix/Mac
source venv/bin/activate
```

### Database
- SQLite database: `database.db` (ignored in git)
- Connection utility: `database.py` provides `get_db_connection()`
- No migrations folder is actively used; schema changes are manual

## Architecture

### Application Structure

**Entry Point**: `app.py`
- Flask app initialization
- Blueprint registration for all route modules
- Root route redirects to `/buy`

**Routes** (`routes/`):
All routes are implemented as Flask Blueprints:
- `auth_routes.py` - Registration, login, logout, password reset
- `buy_routes.py` - Browse listings (buckets), view individual buckets, cart management
- `sell_routes.py` - Create/edit/delete listings with photo uploads
- `bid_routes.py` - Place, accept, cancel bids on categories
- `checkout_routes.py` - Process purchases from cart or direct bucket buys
- `cart_routes.py` - Add/remove items from cart
- `account_routes.py` - User profile, orders history, bids, listings
- `messages_routes.py` - API endpoints for messaging between buyers/sellers
- `ratings_routes.py` - Submit and edit ratings for users
- `api_routes.py` - JSON endpoints for dynamic dropdowns (product_lines, etc.)
- `listings_routes.py` - View and manage individual listings
- `tracking_routes.py` - Update/view order tracking information

**Services** (`services/`):
- `order_service.py` - Order creation logic, cart total calculation

**Utils** (`utils/`):
- `cart_utils.py` - Fetch cart items for logged-in users or guests
- `messaging_utils.py` - Message thread utilities
- `ratings_utils.py` - Rating calculations and queries
- `tracking_utils.py` - Tracking status helpers

**Configuration**: `config.py`
- Loads environment variables from `.env` (not in git)
- Required env vars: `SECRET_KEY`, `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`

### Key Data Model Concepts

**Categories (Buckets)**:
- A category represents a unique combination of: metal, product_type, weight, mint, year, finish, grade, coin_series, purity, product_line
- Multiple listings can belong to the same category
- The buy page groups listings by category, showing the lowest price and total quantity available per category

**Listings**:
- Individual items for sale by a specific seller
- Fields: `category_id`, `seller_id`, `quantity`, `price_per_coin`, `graded`, `grading_service`, `photo_filename`, `active`
- A listing can be graded (PCGS, NGC, etc.) or ungraded

**Cart**:
- For logged-in users: stored in `cart` table with `user_id`, `listing_id`, `quantity`, `grading_preference`
- For guests: stored in Flask session as `guest_cart`
- Merges guest cart into user cart upon registration

**Bids**:
- Buyers can place bids on a category (bucket) if no acceptable listing exists
- Bids have: `category_id`, `buyer_id`, `quantity_requested`, `price_per_coin`, `remaining_quantity`, `requires_grading`, `preferred_grader`, `delivery_address`, `status`
- Sellers can accept bids, which creates an order and deducts from listing inventory

**Orders**:
- Created on checkout
- Contains: `buyer_id`, `total_price`, `shipping_address`, `created_at`
- Related `order_items` link to specific listings with quantity and price_each
- Tracking info stored separately in `tracking` table

### Frontend Structure

**Templates** (`templates/`):
- `base.html` - Base layout with header, flash messages, common CSS/JS
- Page templates: `buy.html`, `sell.html`, `view_bucket.html`, `view_cart.html`, `checkout.html`, `account.html`, `login.html`, etc.
- `modals/` - Reusable modal templates
- `tabs/` - Tab components for account page

**Static Assets** (`static/`):
- `css/` - Stylesheets (base.css, header.css, forms.css, grid.css, bucket.css, modals/, etc.)
- `js/` - JavaScript for interactivity (sell.js, view_bucket.js, view_cart.js, account.js, modals/, tabs/)
- `images/` - Static images
- `uploads/` - User-uploaded listing photos (gitignored)

**JavaScript Patterns**:
- Dynamic form updates based on dropdowns (e.g., sell.js fetches product lines via API)
- Modal open/close logic with outside-click-to-close
- Cart quantity updates, bid submission, tracking info display

### Session Management

- Flask sessions store `user_id` for logged-in users
- Guest users have `guest_cart` in session
- Login/logout managed in `auth_routes.py`

### Authentication Flow

1. User registers via `/register` (creates user, hashes password, merges guest cart)
2. User logs in via `/login` (checks password hash, sets `session['user_id']`)
3. Logout clears session
4. Password reset uses email confirmation (SMTP configured in `config.py`)

### Grading System

Listings can be graded or ungraded:
- Graded coins have a `grading_service` (PCGS, NGC, etc.)
- Filters on buy page allow users to filter by graded-only and specific grading services
- Bids can specify grading requirements

### Photo Uploads

- Listing photos uploaded to `static/uploads/listings/`
- Filenames are secured and stored in `listings.photo_filename`
- Allowed extensions: png, jpg, jpeg, gif

## Important Notes

- The database file `database.db` is very large (5GB) and excluded from version control
- No active migration system; schema changes are applied manually to `database.db`
- The app uses SQLite's `Row` factory for dict-like row access
- Email functionality requires valid SMTP credentials in `.env`
- Google OAuth credentials are configured but login flow may not be fully implemented
- Session secret key should be set in `.env` for production security
