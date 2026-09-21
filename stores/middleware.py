from django.shortcuts import redirect

from .threadlocal import set_current_store
from .models import StoreMembership

PUBLIC_PREFIXES = (
    "/user/login/", "/user/logout/", "/signup/", "/static/", "/staff_portal/login/",
)


class StoreMiddleware:
    """Resolve the current user's store once per request.

    Sets ``request.store`` (None on public/anonymous/superuser requests) and
    installs it into the thread-local that ``StoreScopedManager`` reads.
    Cleared in ``finally`` so a leaked value can never outlive the request —
    including on exceptions.

    A user with no membership or a deactivated store is bounced to login:
    running views unscoped would expose every tenant's rows. Superusers skip
    scoping on purpose (cross-store admin access).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.store = None
        try:
            if request.path.startswith(PUBLIC_PREFIXES) or request.path == "/favicon.ico":
                return self.get_response(request)

            if request.user.is_authenticated:
                membership = (
                    StoreMembership.objects.select_related("store")
                    .filter(user=request.user)
                    .first()
                )
                if membership and membership.store.is_active:
                    request.store = membership.store
                elif not request.user.is_superuser:
                    set_current_store(None)
                    return redirect("/user/login/")

            set_current_store(request.store)
            return self.get_response(request)
        finally:
            set_current_store(None)
