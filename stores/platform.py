"""Platform (super admin) permission helpers."""
from django.core.exceptions import PermissionDenied

from .middleware import is_super_admin


def super_admin_required(view):
    def wrapped(request, *args, **kwargs):
        if not is_super_admin(request.user):
            raise PermissionDenied("Platform access requires the super admin role.")
        return view(request, *args, **kwargs)

    wrapped.__name__ = view.__name__
    return wrapped
