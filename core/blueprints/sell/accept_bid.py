# core/blueprints/sell/accept_bid.py
"""
DECOMMISSIONED — this module no longer registers any routes.

The canonical bid acceptance route is:
  POST /bids/accept_bid/<bucket_id>   (core/blueprints/bids/accept_bid.py)

This file was previously imported by sell/routes.py and registered a duplicate
/sell/accept_bid/<bucket_id> route that was unreachable from the UI.  It has
been decommissioned as part of the payment-safety audit to eliminate divergent
payment implementations.  Do not re-add routes here.
"""
