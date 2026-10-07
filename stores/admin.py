from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import BranchStock, StockMovement, StockTransfer, Store, StoreMembership


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_warehouse", "is_active", "address", "phone")
    list_editable = ("is_active",)
    prepopulated_fields = {"code": ("name",)}


@admin.register(StoreMembership)
class StoreMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "store")
    list_filter = ("role", "store")
    search_fields = ("user__username",)


class MembershipInline(admin.StackedInline):
    model = StoreMembership
    can_delete = False
    verbose_name_plural = "Branch & role"


User = get_user_model()
admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = (MembershipInline,)
    list_display = ("username", "first_name", "last_name", "is_staff", "branch_role")

    @admin.display(description="Branch / role")
    def branch_role(self, obj):
        m = getattr(obj, "store_membership", None)
        return str(m).split(" — ", 1)[-1] if m else "—"


@admin.register(BranchStock)
class BranchStockAdmin(admin.ModelAdmin):
    list_display = ("product", "store", "qty")
    list_filter = ("store",)
    search_fields = ("product__barcode", "product__name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False  # stock changes go through Receive / Transfer / sales


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "store", "product", "kind", "qty_change", "user")
    list_filter = ("store", "kind")
    search_fields = ("product__barcode", "product__name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "source", "destination", "created_by", "note")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
