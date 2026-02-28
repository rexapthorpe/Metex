# routes/bid_routes.py
# Re-export wrapper — canonical implementation is in core/blueprints/bids/

from core.blueprints.bids import (
    bid_bp,
    auto_match_bid_to_listings,
    auto_match_listing_to_bids,
    check_all_pending_matches,
)

__all__ = [
    'bid_bp',
    'auto_match_bid_to_listings',
    'auto_match_listing_to_bids',
    'check_all_pending_matches',
]
