"""Admin support for store scoping.

Superusers keep full cross-store visibility. Non-superuser staff see only
their own store's rows, and new objects they create are stamped with their
store automatically.
"""
from django.contrib import admin

from stores.models import StoreMembership


def get_user_store(user):
    if not user.is_authenticated or user.is_superuser:
        return None
    membership = StoreMembership.objects.filter(user=user).select_related("store").first()
    return membership.store if membership else None


class StoreScopedAdmin(admin.ModelAdmin):
    """Inherit (alongside your existing ModelAdmin base) to scope the admin."""

    store_field = "store"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        store = get_user_store(request.user)
        if store is not None:
            return qs.filter(**{f"{self.store_field}": store})
        return qs

    def save_model(self, request, obj, form, change):
        if not change and not getattr(obj, f"{self.store_field}_id", None):
            store = get_user_store(request.user)
            if store is not None:
                setattr(obj, self.store_field, store)
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, request, db_field, **kwargs):
        # Foreign keys to other scoped models shrink to the user's store rows.
        if not request.user.is_superuser and db_field.name in (
            "department", "tax_category", "deposit_category", "store",
        ):
            store = get_user_store(request.user)
            if store is not None:
                kwargs["queryset"] = db_field.related_model.objects.filter(store=store)
        return super().formfield_for_foreignkey(request, db_field, **kwargs)
