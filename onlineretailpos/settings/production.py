from .base import *
import os
from dotenv import load_dotenv
load_dotenv()

DEBUG = False

# Fall back through env keys so the app always boots; set SECRET_KEY_PROD
# (or SECRET_KEY_DEV) in the environment for real deployments.
SECRET_KEY = (os.getenv('SECRET_KEY_PROD') or os.getenv('SECRET_KEY_DEV')
              or 'django-insecure-deploy-fallback-key')

# Comma-separated, e.g. ".vercel.app,yourdomain.com"
ALLOWED_HOSTS = ['localhost', '127.0.0.1'] + \
    [h.strip() for h in os.getenv('ALLOWED_HOSTS', '').split(',') if h.strip()]

# Comma-separated, e.g. "https://yourdomain.com,https://*.vercel.app"
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]

# The app is served behind HTTPS-terminating proxies (Vercel, Fly, ngrok, etc.)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Database: sqlite by default, postgres when NAME_OF_DATABASE=postgres
if os.getenv('NAME_OF_DATABASE', 'sqlite') == 'postgres':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'OnlineRetailPOS'),
            'USER': os.getenv('DB_USERNAME'),
            'PASSWORD': os.getenv('DB_PASSWORD'),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', ''),
            'OPTIONS': {
                # Neon/Supabase require TLS; 'prefer' also works locally
                'sslmode': os.getenv('DB_SSLMODE', 'prefer'),
            },
            # Required for Supabase/Neon transaction-pooler ports (e.g. 6543)
            'DISABLE_SERVER_SIDE_CURSORS': os.getenv('DB_DISABLE_SERVER_SIDE_CURSORS', '') in ('1', 'true', 'yes'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / os.getenv('SQLITE_PATH', 'db.sqlite3'),
        }
    }

# HTTPS Security - Django (proxy-aware; cookies only over TLS)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Enable once the platform serves HTTPS end-to-end on every host:
# SECURE_SSL_REDIRECT = True

# HSTS Security - Django
SECURE_HSTS_SECONDS = 120
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True


# Store Information (same env contract as devlopement settings)
# For Line Break add \n; can not be more than (RECEIPT_CHAR_COUNT - 2) chars per line
RECEIPT_CHAR_COUNT = int(os.getenv('RECEIPT_CHAR_COUNT', 32))
STORE_NAME = os.getenv('STORE_NAME', "STORE NAME")
STORE_ADDRESS = os.getenv('STORE_ADDRESS', "STORE ADDRESS")
STORE_PHONE = os.getenv('STORE_PHONE', "")
RECEIPT_HEAD = f"{STORE_NAME}\n{STORE_ADDRESS}"
RECEIPT_HEAD = RECEIPT_HEAD + f"\n{STORE_PHONE}" if os.getenv('Include_Phone_In_Heading', "False").lower() == "true" else RECEIPT_HEAD
RECEIPT_ADDITIONAL_HEADING = os.getenv('RECEIPT_ADDITIONAL_HEADING', "")
RECEIPT_HEADER = f"{RECEIPT_HEAD}\n{RECEIPT_ADDITIONAL_HEADING}" if RECEIPT_ADDITIONAL_HEADING != "" else RECEIPT_HEAD
RECEIPT_FOOTER = os.getenv('RECEIPT_FOOTER', "Thank You")


# Printer Settings
PRINTER_VENDOR_ID = os.getenv('PRINTER_VENDOR_ID', "")
PRINTER_PRODUCT_ID = os.getenv('PRINTER_PRODUCT_ID', "")
PRINT_RECEIPT = os.getenv('PRINT_RECEIPT', False)
CASH_DRAWER = os.getenv('CASH_DRAWER', False)
