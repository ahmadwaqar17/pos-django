from .base import *
import os, socket
# from sshtunnel import SSHTunnelForwarder
from dotenv import load_dotenv
import dj_database_url
load_dotenv()

ip_address = socket.gethostbyname(socket.gethostname())
    
DEBUG = False
SECRET_KEY = os.getenv('SECRET_KEY_DEV', 'django_dev_secret_key_online-retail-pos-1234')

import_env_hosts = os.getenv('ALLOWED_HOSTS', '')
# No module-level print() here: Vercel's Django integration parses stdout of
# settings introspection as JSON, and any print pollutes it and fails the build.
ALLOWED_HOSTS = [ip_address, '127.0.0.1', 'localhost'] \
    + [h.strip() for h in import_env_hosts.split(',') if h.strip()]

# Vercel terminates HTTPS at their proxy; trust their forwarded-proto header
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

import_env_origins = os.getenv('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [f"http://{ip_address}", "http://127.0.0.1", "http://localhost:8080"] \
    + [o.strip() for o in import_env_origins.split(',') if o.strip()]

# # Database sqllite
# # https://docs.djangoproject.com/en/4.0/ref/settings/#databases


def _tune_pooler(db_cfg):
    """Transaction poolers (Supabase ':6543' / '*-pooler*' hosts, Neon pooler)
    break server-side cursors; force them off when we detect one."""
    if db_cfg.get('ENGINE') == 'django.db.backends.postgresql':
        host = str(db_cfg.get('HOST') or '')
        port = str(db_cfg.get('PORT') or '')
        if 'pooler.supabase' in host or host.endswith('-pooler') or port == '6543':
            db_cfg['DISABLE_SERVER_SIDE_CURSORS'] = True
    return db_cfg


database_dict = {
    'sqlite' :  {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3', 
        } ,
    'postgres' : (
            # One-variable setup: DATABASE_URL wins when present.
            # Format: postgresql://user:password@host:port/dbname
            # NOTE: URL-encode special characters in the password
            # (e.g. @ -> %40). Supabase example in the dashboard's
            # connection string already comes URL-encoded.
            dj_database_url.config(
                default=os.getenv('DATABASE_URL', ''),
                conn_max_age=60,
                ssl_require=(os.getenv('DB_SSLMODE', 'prefer') == 'require'),
            )
            if os.getenv('DATABASE_URL') else
            {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', "OnlineRetailPOS"),  # Use environment variable DB_NAME, defaulting to 'default_db_name'
            'USER': os.getenv('DB_USERNAME'),  # Use environment variable DB_USERNAME
            'PASSWORD': os.getenv('DB_PASSWORD'),  # Use environment variable DB_PASSWORD
            'HOST': os.getenv('DB_HOST', "localhost"),  # Use environment variable DB_HOST
            'PORT': os.getenv('DB_PORT', ''),  # By default, PostgreSQL uses port 5432
            'OPTIONS': {
                # Neon/Supabase require TLS; 'prefer' also works with plain local postgres
                'sslmode': os.getenv('DB_SSLMODE', 'prefer'),
            },
            # Required for Supabase/Neon transaction-pooler ports (e.g. 6543):
            # server-side cursors break under pgbouncer transaction pooling.
            'DISABLE_SERVER_SIDE_CURSORS': os.getenv('DB_DISABLE_SERVER_SIDE_CURSORS', '') in ('1', 'true', 'yes'),
            'CONN_MAX_AGE': 60,
        }
    ) ,
    'mysql': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME', "OnlineRetailPOS"),  # Use environment variable DB_NAME
            'USER': os.getenv('DB_USERNAME'),  # Use environment variable DB_USERNAME
            'PASSWORD': os.getenv('DB_PASSWORD'),  # Use environment variable DB_PASSWORD
            'HOST': os.getenv('DB_HOST', "localhost"),  # Use environment variable DB_HOST
            'PORT': os.getenv('DB_PORT', ''),  
            'OPTIONS':{
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"
                }
    }
}

DATABASES = {
    'default':  _tune_pooler(database_dict[os.getenv('NAME_OF_DATABASE', 'sqlite')])
    
}


## COMMENT/UNCOMMENT to switch from  sqllite file to regular cloud database, configuration may differ
##  Database Connection

## SSH Tunnel 
# Connect to a server using the ssh keys. See the sshtunnel documentation for using password authentication
# ssh_tunnel = SSHTunnelForwarder(
#     os.getenv('SSH_HOST'),
#     ssh_username = os.getenv('SSH_USERNAME'),
#     ssh_password = os.getenv('SSH_PASSWORD'),
#     remote_bind_address=(os.getenv('SSH_DB_HOST'), 3306),
# )
# ssh_tunnel.start()

## Database MySQL
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': os.getenv('DB_NAME'),
#         'USER' : os.getenv('DB_USERNAME'),
#         'PASSWORD' : os.getenv('DB_PASSWORD'),
#         'HOST': "127.0.0.1",
#         'PORT' : ssh_tunnel.local_bind_port,
#         'OPTIONS':{
#              'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"
#             }
#     }
# }


# Store Information
# For Line Break add \n
#Can not be more than (RECEIPT_CHAR_COUNT - 2) Characters per line(\n), if wants to add more break it up by \n new line
RECEIPT_CHAR_COUNT = int(os.getenv('RECEIPT_CHAR_COUNT', 32)) 
STORE_NAME = os.getenv('STORE_NAME', "STORE NAME")  #Can not be more than RECEIPT_CHAR_COUNT 
STORE_ADDRESS = os.getenv('STORE_ADDRESS', "STORE ADDRESS")
STORE_PHONE = os.getenv('STORE_PHONE', "")
RECEIPT_HEAD = f"{STORE_NAME}\n{STORE_ADDRESS}"  
RECEIPT_HEAD = RECEIPT_HEAD + f"\n{STORE_PHONE}" if os.getenv('Include_Phone_In_Heading',"False").lower() == "true" else RECEIPT_HEAD
RECEIPT_ADDITIONAL_HEADING = os.getenv('RECEIPT_ADDITIONAL_HEADING', "")
RECEIPT_HEADER = f"{RECEIPT_HEAD}\n{RECEIPT_ADDITIONAL_HEADING}" if RECEIPT_ADDITIONAL_HEADING != "" else RECEIPT_HEAD
RECEIPT_FOOTER = os.getenv('RECEIPT_FOOTER',"Thank You")


# Printer Settings
PRINTER_VENDOR_ID = os.getenv('PRINTER_VENDOR_ID', "")
PRINTER_PRODUCT_ID = os.getenv('PRINTER_PRODUCT_ID', "")
PRINT_RECEIPT = os.getenv('PRINT_RECEIPT', False)
CASH_DRAWER = os.getenv('CASH_DRAWER', False)
