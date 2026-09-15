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
        on_read_only_host = (os.getenv('VERCEL') is not None
                             or os.getenv('READ_ONLY_DB', '').lower() in ('1', 'true', 'yes'))
        using_baked_sqlite = os.getenv('NAME_OF_DATABASE', 'sqlite') == 'sqlite'
        if on_read_only_host and using_baked_sqlite:
            auth_signals.user_logged_in.disconnect(dispatch_uid='update_last_login')
