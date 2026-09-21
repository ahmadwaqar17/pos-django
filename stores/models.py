from django.db import models
from django.conf import settings


class Store(models.Model):
    """One SaaS customer = one store. All business rows hang off this FK."""

    # Identity
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=60, unique=True)

    # Branding / receipt (moved out of env vars so each tenant has their own)
    store_name = models.CharField(max_length=64)
    store_address = models.TextField(blank=True, default="")
    store_phone = models.CharField(max_length=32, blank=True, default="")
    receipt_footer = models.CharField(max_length=120, blank=True, default="Thank You")
    currency = models.CharField(max_length=8, default="PKR")
    timezone = models.CharField(max_length=64, default="US/Eastern")

    # Control
    is_active = models.BooleanField(default=True)
    plan = models.CharField(max_length=32, default="trial")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class StoreMembership(models.Model):
    """Links a user to their store. v1: one membership per user.

    ``super_admin`` is the platform operator role: their membership has no
    store — they manage every store from /platform/ instead of selling.
    """

    ROLE_OWNER = "owner"
    ROLE_CASHIER = "cashier"
    ROLE_SUPER_ADMIN = "super_admin"
    ROLES = [
        (ROLE_OWNER, "Owner"),
        (ROLE_CASHIER, "Cashier"),
        (ROLE_SUPER_ADMIN, "Super Admin"),
    ]

    store = models.ForeignKey(
        Store, on_delete=models.CASCADE, related_name="memberships",
        null=True, blank=True,  # null only for platform super admins
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="store_membership"
    )
    role = models.CharField(max_length=16, choices=ROLES, default=ROLE_OWNER)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.role == self.ROLE_SUPER_ADMIN and self.store_id:
            raise ValidationError("Super admins are platform-level and cannot belong to a store.")
        if self.role != self.ROLE_SUPER_ADMIN and not self.store_id:
            raise ValidationError("Store roles (owner/cashier) require a store.")

    def __str__(self) -> str:
        target = self.store if self.store_id else "platform"
        return f"{self.user} @ {target} ({self.role})"
