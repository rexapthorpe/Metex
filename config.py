from dotenv import load_dotenv
load_dotenv()
import os


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

# Pricing Configuration
PRICE_LOCK_DURATION_SECONDS = int(os.getenv('PRICE_LOCK_DURATION_SECONDS', '10'))
SPOT_PRICE_CACHE_TTL_MINUTES = int(os.getenv('SPOT_PRICE_CACHE_TTL_MINUTES', '5'))
