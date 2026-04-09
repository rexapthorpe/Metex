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

# Site URL (used for Stripe Connect onboarding pre-fill)
SITE_URL = os.getenv('SITE_URL', 'https://metex.com')

# Pricing Configuration
PRICE_LOCK_DURATION_SECONDS = int(os.getenv('PRICE_LOCK_DURATION_SECONDS', '10'))
SPOT_PRICE_CACHE_TTL_MINUTES = int(os.getenv('SPOT_PRICE_CACHE_TTL_MINUTES', '5'))

