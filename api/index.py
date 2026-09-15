import os

from django.core.wsgi import get_wsgi_application

# Vercel entrypoint. Keep the dev settings module default so the broken
# empty-DATABASES production.py is never loaded accidentally.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'onlineretailpos.settings.devlopement')

application = get_wsgi_application()

# Vercel's Python runtime looks for `app` in api/index.py
app = application
