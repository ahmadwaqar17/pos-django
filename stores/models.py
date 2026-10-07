"""Branches (stores), who works where, and per-branch stock.

The product catalog (barcode, name, price, department, tax, deposit) stays
global in ``inventory``. What belongs to a branch is its *stock* and its
*sales*. Every stock change goes through ``stores.stock`` and leaves one
``StockMovement`` row, so any branch's quantity can be explained line by line.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Store(models.Model):
    """A shop (branch) or the central warehouse."""

    name = models.CharField(max_length=64, unique=True)
    code = models.SlugField(max_length=16, unique=True,
                            help_text="Short unique code, e.g. MAIN or WH.")
    address = models.CharField(max_length=200, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    receipt_footer = models.CharField(max_length=120, blank=True, default="Thank You")
    is_warehouse = models.BooleanField(
        default=False,
        help_text="The central stock location. It can hold and send stock but cannot sell.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("is_warehouse", "name")
        verbose_name = "Branch"
        verbose_name_plural = "Branches"

    def __str__(self):
        return self.name

    def clean(self):
        if self.is_warehouse and Store.objects.filter(is_warehouse=True).exclude(pk=self.pk).exists():
            raise ValidationError({"is_warehouse": "There is already a warehouse. Only one is allowed."})

    @classmethod
    def warehouse(cls):
        return cls.objects.filter(is_warehouse=True, is_active=True).first()

    @classmethod
    def selling(cls):
        """Active branches that can ring up sales (everything except the warehouse)."""
        return cls.objects.filter(is_active=True, is_warehouse=False)


class StoreMembership(models.Model):
    """Which branch a user works at, and their role.

    Owners have no store: they can switch between every branch and see the
    combined reports. Managers and cashiers are pinned to one branch.
    Superusers are treated as owners even without a membership row.
    """

    ROLE_OWNER = "owner"
    ROLE_MANAGER = "manager"
    ROLE_CASHIER = "cashier"
    ROLES = [
        (ROLE_OWNER, "Owner (all branches)"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_CASHIER, "Cashier"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="store_membership")
    role = models.CharField(max_length=16, choices=ROLES, default=ROLE_CASHIER)
    store = models.ForeignKey(Store, on_delete=models.PROTECT, null=True, blank=True,
                              related_name="memberships",
                              help_text="Leave empty for owners (they work across all branches).")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Staff assignment"
        verbose_name_plural = "Staff assignments"

    def __str__(self):
        return f"{self.user} — {self.get_role_display()} @ {self.store or 'all branches'}"

    def clean(self):
        if self.role == self.ROLE_OWNER and self.store_id:
            raise ValidationError({"store": "Owners work across all branches; leave the branch empty."})
        if self.role != self.ROLE_OWNER and not self.store_id:
            raise ValidationError({"store": "Managers and cashiers must be assigned to a branch."})


class BranchStock(models.Model):
    """On-hand quantity of one product at one branch (may go negative)."""

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="stock")
    product = models.ForeignKey("inventory.product", on_delete=models.CASCADE, related_name="branch_stock")
    qty = models.IntegerField(default=0)
    last_counted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["store", "product"], name="unique_stock_per_branch")]
        verbose_name = "Branch stock"
        verbose_name_plural = "Branch stock"

    def __str__(self):
        return f"{self.product} @ {self.store}: {self.qty}"


class StockTransfer(models.Model):
    """One instant transfer of stock between two locations."""

    source = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="transfers_out")
    destination = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="transfers_in")
    note = models.CharField(max_length=200, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   null=True, related_name="stock_transfers")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Transfer #{self.pk}: {self.source} → {self.destination}"


class StockMovement(models.Model):
    """Ledger: one row for every change to a branch's stock."""

    OPENING = "OPENING"
    RECEIVE = "RECEIVE"
    SALE = "SALE"
    RETURN = "RETURN"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    ADJUST = "ADJUST"
    KINDS = [
        (OPENING, "Opening stock"),
        (RECEIVE, "Received"),
        (SALE, "Sale"),
        (RETURN, "Customer return"),
        (TRANSFER_IN, "Transfer in"),
        (TRANSFER_OUT, "Transfer out"),
        (ADJUST, "Adjustment"),
    ]

    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="movements")
    product = models.ForeignKey("inventory.product", on_delete=models.PROTECT, related_name="stock_movements")
    qty_change = models.IntegerField()
    kind = models.CharField(max_length=16, choices=KINDS)
    transfer = models.ForeignKey(StockTransfer, on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="movements")
    sale = models.ForeignKey("transaction.transaction", on_delete=models.PROTECT, null=True, blank=True,
                             related_name="stock_movements")
    note = models.CharField(max_length=200, blank=True, default="")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                             related_name="stock_movements")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["store", "product"], name="stockmove_store_product_idx")]

    def __str__(self):
        sign = "+" if self.qty_change > 0 else ""
        return f"{self.get_kind_display()} {sign}{self.qty_change} {self.product} @ {self.store}"
