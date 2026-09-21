from django.shortcuts import redirect

from .threadlocal import set_current_store
from .models import StoreMembership

PUBLIC_PREFIXES = (
    "/user/login/", "/user/logout/", "/signup/", "/static/", "/staff_portal/login/",
)
PLATFORM_PREFIX = "/platform/"


def is_super_admin(user):
    """Platform operator: membership role super_admin (store is null), or a Django superuser."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    m = getattr(user, "store_membership", None)  # OneToOne, may be cached
    return bool(m and m.role == StoreMembership.ROLE_SUPER_ADMIN)


class StoreMiddleware:
    """Resolve the current user's store once per request.

    Tenant users get ``request.store`` and a thread-local that
    ``StoreScopedManager`` reads. Super admins are platform-level: they have
    no store, so tenant pages redirect them to their own dashboard at
    /platform/ (prevents running the whole app unscoped). Users with no
    membership or a deactivated store are bounced to login.

    The thread-local is always cleared in ``finally`` so a leaked value can
    never outlive the request — including on exceptions.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.store = None
        try:
            path = request.path
            if path.startswith(PUBLIC_PREFIXES) or path == "/favicon.ico":
                return self.get_response(request)

            if request.user.is_authenticated:
                if is_super_admin(request.user):
                    if not path.startswith(PLATFORM_PREFIX):
                        set_current_store(None)
                        return redirect("platform_dashboard")
                    set_current_store(None)
                    return self.get_response(request)

                membership = (
                    StoreMembership.objects.select_related("store")
                    .filter(user=request.user)
                    .first()
                )
                if membership and membership.store.is_active:
                    if path.startswith(PLATFORM_PREFIX):
                        set_current_store(None)
                        return redirect("home")
                    request.store = membership.store
                elif not request.user.is_superuser:
                    set_current_store(None)
                    return redirect("/user/login/")

            set_current_store(request.store)
            return self.get_response(request)
        finally:
            set_current_store(None)
