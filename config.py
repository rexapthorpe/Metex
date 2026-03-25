from dotenv import load_dotenv
load_dotenv()
import os
import stripe


# Flask Session Security
SECRET_KEY = os.getenv('SECRET_KEY', 'your-very-random-fallback-key-here')

# Email Configuration
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS', 'your.email@gmail.com')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', 'your_app_password_here')

# Google OAuth Credentials
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')

# MetalpriceAPI Configuration
METALPRICE_API_KEY = os.getenv('METALPRICE_API_KEY')

# Stripe Connect Configuration
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
# Set by `stripe listen --forward-to ...` locally; set in Stripe Dashboard for production.
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')

# ---------------------------------------------------------------------------
# Stripe initialization — happens once at import time.
# stripe.api_key is a module-level global; setting it here means every
# module that does `import stripe` will already have the key configured.
# ---------------------------------------------------------------------------
_TESTING = os.getenv('FLASK_TESTING', '').lower() in ('1', 'true', 'yes')

if not _TESTING:
    if not STRIPE_SECRET_KEY:
        raise EnvironmentError(
            "Missing required environment variable: STRIPE_SECRET_KEY. "
            "Add it to your .env file or deployment environment."
        )
    if not STRIPE_PUBLISHABLE_KEY:
        raise EnvironmentError(
            "Missing required environment variable: STRIPE_PUBLISHABLE_KEY. "
            "Add it to your .env file or deployment environment."
        )

stripe.api_key = STRIPE_SECRET_KEY or ''  # empty string safe in test mode

# Pricing Configuration
PRICE_LOCK_DURATION_SECONDS = int(os.getenv('PRICE_LOCK_DURATION_SECONDS', '10'))
SPOT_PRICE_CACHE_TTL_MINUTES = int(os.getenv('SPOT_PRICE_CACHE_TTL_MINUTES', '5'))

# Third-Party Grading Service Configuration
GRADING_FEE_PER_UNIT = 70.00  # Flat fee per coin for third-party grading service
GRADING_SERVICE_DEFAULT = 'PCGS'  # Default grading service
GRADING_SERVICE_OPTIONS = ['PCGS', 'NGC', 'ANACS']  # Available grading services

# Grading Status Values
GRADING_STATUS_NOT_REQUESTED = 'not_requested'
GRADING_STATUS_PENDING_SELLER_SHIP = 'pending_seller_ship_to_grader'
GRADING_STATUS_IN_TRANSIT = 'in_transit_to_grader'
GRADING_STATUS_AT_GRADER = 'at_grader'
GRADING_STATUS_COMPLETED = 'completed'

# Grading Service Shipping Addresses
GRADING_SERVICE_ADDRESSES = {
    'PCGS': {
        'name': 'PCGS – Attn: Submissions',
        'line1': 'P.O. Box 9458',
        'line2': '',
        'city': 'Newport Beach',
        'state': 'CA',
        'zip': '92658'
    },
    'NGC': {
        'name': 'NGC – Attn: Submissions',
        'line1': 'P.O. Box 4776',
        'line2': '',
        'city': 'Sarasota',
        'state': 'FL',
        'zip': '34230'
    },
    'ANACS': {
        'name': 'ANACS – Attn: Submissions',
        'line1': '6555 S. Kenton St.',
        'line2': 'Suite 220',
        'city': 'Englewood',
        'state': 'CO',
        'zip': '80111'
    }
}
