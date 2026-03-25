"""
Stripe Connect Blueprint

Handles seller payout onboarding via Stripe Express accounts.
Routes: /stripe/create-account, /stripe/create-account-link,
        /stripe/return, /stripe/refresh
"""

from flask import Blueprint

stripe_bp = Blueprint('stripe_connect', __name__, url_prefix='/stripe')

from . import routes  # noqa: E402, F401

__all__ = ['stripe_bp']
