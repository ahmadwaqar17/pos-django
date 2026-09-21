"""Per-request tenant scoping.

Two pieces:
  * ``threadlocal.py``  — a tiny request-scoped holder for the active Store.
  * ``managers.StoreScopedManager`` — auto-filters every queryset by it.

The middleware (stores.middleware.StoreMiddleware) sets the store before the
view runs and clears it afterwards (also on error), so a leaked value can never
outlive its request.
"""
import threading

_local = threading.local()


def set_current_store(store):
    _local.store = store


def get_current_store():
    return getattr(_local, "store", None)
