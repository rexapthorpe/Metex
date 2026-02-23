"""
Bids Blueprint Package

This package contains all bid-related routes, split by domain for maintainability.
The bid_bp Blueprint is defined here and routes are registered by importing sub-modules.

Structure:
- __init__.py: Blueprint definition and assembly
- place_bid.py: Place and create bid routes
- edit_bid.py: Edit bid routes
- view_bids.py: View bids pages
- accept_bid.py: Accept bid route
- bid_form.py: Bid form route
- auto_match.py: Auto-match helper functions
- api.py: Bidder info API

IMPORTANT: This split preserves ALL original route URLs, endpoint names, and behavior.
The blueprint name remains 'bid' with url_prefix='/bids' for compatibility.
"""

from flask import Blueprint

# Create the bid blueprint - MUST keep name='bid' and url_prefix='/bids' for URL compatibility
bid_bp = Blueprint('bid', __name__, url_prefix='/bids')

# Import all route modules to register routes with bid_bp
# Note: auto_match must be imported first since other modules may use its functions
from . import auto_match
from . import place_bid
from . import edit_bid
from . import view_bids
from . import accept_bid
from . import bid_form
from . import api

# Re-export auto_match functions for external use
from .auto_match import (
    auto_match_bid_to_listings,
    auto_match_listing_to_bids,
    check_all_pending_matches,
)

# Re-export for compatibility
__all__ = [
    'bid_bp',
    'auto_match_bid_to_listings',
    'auto_match_listing_to_bids',
    'check_all_pending_matches',
]
