from django.apps import AppConfig
from django.contrib.auth import signals as auth_signals


class OnlineRetailPOSConfig(AppConfig):
    name = 'onlineretailpos'
    label = 'onlineretailpos'
    verbose_name = 'Online Retail POS'

    def ready(self):
        # Read-only-database mode (settings/base.py): logging in normally
        # writes last_login to the DB, which crashes on hosts like Vercel.
        # This config is appended last in INSTALLED_APPS, so ready() runs
        # after django.contrib.auth's ready() has connected the receiver.
        import os
        if os.getenv('VERCEL') or os.getenv('READ_ONLY_DB', '').lower() in ('1', 'true', 'yes'):
            auth_signals.user_logged_in.disconnect(dispatch_uid='update_last_login')
