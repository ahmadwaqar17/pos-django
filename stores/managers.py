from django.db import models

from .threadlocal import get_current_store


class StoreScopedManager(models.Manager):
    """Manager that auto-filters by the store of the current request.

    Views keep calling ``product.objects.all()`` / ``.filter(...)`` unchanged —
    isolation is applied here, in one place. Use ``all_objects`` (the plain
    manager installed as ``all_objects`` on scoped models) to bypass scoping,
    e.g. for cross-tenant admin queries, shell work, and data migrations.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        store = get_current_store()
        if store is not None:
            qs = qs.filter(store=store)
        return qs
