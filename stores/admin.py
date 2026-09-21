from django.contrib import admin

from .models import Store, StoreMembership


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "plan", "is_active", "created_at")
    list_filter = ("is_active", "plan")
    search_fields = ("name", "slug", "store_name")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(StoreMembership)
class StoreMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "store", "role", "created_at")
    list_filter = ("role", "store")
    search_fields = ("user__username", "store__name")
