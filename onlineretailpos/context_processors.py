from django.conf import settings


def branding(request):
    """Store/company name for page titles and headers (``STORE_NAME`` env var)."""
    return {'brand_name': settings.STORE_NAME}
