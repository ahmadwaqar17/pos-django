"""Which branch a request works in, and what the user may do there.

``StoreMiddleware`` sets on every request:
  * ``request.membership``   the user's StoreMembership (or None)
  * ``request.is_owner``     owners/superusers can switch branches
  * ``request.store``        the active branch (where the register sells)
  * ``request.all_branches`` owner chose "All branches" for reports
"""
from django.contrib import messages
from functools import wraps

from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

from .models import Store, StoreMembership

SESSION_STORE = "active_store_id"
SESSION_ALL = "all_branches"

# Paths that work without a branch (login, admin so staff can fix assignments, assets).
EXEMPT_PREFIXES = ("/user/login", "/user/logout", "/staff_portal/", "/static/", "/favicon.ico")


def _membership(user):
    try:
        return user.store_membership
    except StoreMembership.DoesNotExist:
        return None


def is_owner(user, membership=None):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    membership = membership if membership is not None else _membership(user)
    return bool(membership and membership.role == StoreMembership.ROLE_OWNER)


def can_manage_stock(request):
    """Owners and managers can receive, transfer and view stock across branches."""
    m = getattr(request, "membership", None)
    return getattr(request, "is_owner", False) or bool(m and m.role == StoreMembership.ROLE_MANAGER)


def role_of(request):
    """"owner", "manager" or "cashier" for templates and checks."""
    if getattr(request, "is_owner", False):
        return StoreMembership.ROLE_OWNER
    m = getattr(request, "membership", None)
    return m.role if m else StoreMembership.ROLE_CASHIER


def manager_required(view):
    """Owners and managers only; cashiers are sent back to the register."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), "/user/login/")
        if not can_manage_stock(request):
            messages.warning(request, "That page is for managers and owners.")
            return redirect("register")
        return view(request, *args, **kwargs)
    return wrapper


def owner_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), "/user/login/")
        if not getattr(request, "is_owner", False):
            messages.warning(request, "Only owners can do that.")
            return redirect("home")
        return view(request, *args, **kwargs)
    return wrapper


def visible_stores(request):
    """Branches whose sales/stock this user may see."""
    if getattr(request, "is_owner", False):
        return Store.objects.filter(is_active=True)
    store = getattr(request, "store", None)
    return Store.objects.filter(pk=store.pk) if store else Store.objects.none()


def scope_sales(queryset, request, field="store"):
    """Limit a sales queryset to the active branch, unless an owner chose All branches."""
    if getattr(request, "all_branches", False) and getattr(request, "is_owner", False):
        return queryset
    store = getattr(request, "store", None)
    if store is None:
        return queryset.none()
    return queryset.filter(**{field: store})


class StoreMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.membership = None
        request.is_owner = False
        request.store = None
        request.all_branches = False

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            membership = _membership(user)
            request.membership = membership
            request.is_owner = is_owner(user, membership)

            if request.is_owner:
                stores = Store.objects.filter(is_active=True)
                store = stores.filter(pk=request.session.get(SESSION_STORE)).first() \
                    or Store.selling().first() or stores.first()
                request.store = store
                request.all_branches = bool(request.session.get(SESSION_ALL))
            elif membership and membership.store and membership.store.is_active:
                request.store = membership.store

            if request.store is None and not request.path.startswith(EXEMPT_PREFIXES):
                # Logged in but not assigned to an active branch: nothing safe to show.
                logout(request)
                messages.error(request, "Your account isn't assigned to a branch yet. "
                                        "Ask the owner to assign you in Admin → Staff assignments.")
                return redirect("user_login")

        return self.get_response(request)


def branch_context(request):
    """Template variables for the branch badge, switcher and Stock menu."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    return {
        "active_store": getattr(request, "store", None),
        "is_owner": getattr(request, "is_owner", False),
        "all_branches": getattr(request, "all_branches", False),
        "can_manage_stock": can_manage_stock(request),
        "user_role": role_of(request),
        "switchable_stores": Store.objects.filter(is_active=True) if getattr(request, "is_owner", False) else [],
    }
