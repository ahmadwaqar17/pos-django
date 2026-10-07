"""The one place that changes stock.

Every write goes through ``adjust`` (or ``transfer``, which calls it twice per
line) so ``BranchStock`` and the ``StockMovement`` ledger can never disagree.
Quantities are updated with ``F()`` expressions, so two sales of the same item
at the same moment can't overwrite each other.
"""
from django.db import IntegrityError, transaction as db_transaction
from django.db.models import F, IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from .models import BranchStock, StockMovement, StockTransfer


class StockError(ValueError):
    """A stock operation was rejected (shown to the user as-is)."""


def _stock_row(store, product):
    try:
        return BranchStock.objects.get_or_create(store=store, product=product)[0]
    except IntegrityError:
        # Another request created the row between our SELECT and INSERT.
        return BranchStock.objects.get(store=store, product=product)


def adjust(store, product, delta, kind, user=None, transfer=None, sale=None, note=""):
    """Change ``product``'s stock at ``store`` by ``delta`` and log it.

    Stock may go negative: the business rule is "warn but allow", so a sale is
    never blocked by a wrong count. Returns the new quantity.
    """
    delta = int(delta)
    if delta == 0:
        return branch_qty(store, product)
    with db_transaction.atomic():
        row = _stock_row(store, product)
        BranchStock.objects.filter(pk=row.pk).update(qty=F("qty") + delta)
        StockMovement.objects.create(
            store=store, product=product, qty_change=delta, kind=kind,
            transfer=transfer, sale=sale, user=user, note=note[:200])
    row.refresh_from_db(fields=["qty"])
    return row.qty


def transfer(source, destination, lines, user=None, note=""):
    """Move stock from ``source`` to ``destination`` in one step.

    ``lines`` is an iterable of ``(product, qty)``. All-or-nothing: if any line
    is invalid, nothing moves. Returns the ``StockTransfer``.
    """
    if source is None or destination is None:
        raise StockError("Choose both a source and a destination.")
    if source.pk == destination.pk:
        raise StockError("Source and destination must be different.")
    if not (source.is_active and destination.is_active):
        raise StockError("Both locations must be active.")

    merged = {}
    for product, qty in lines:
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            raise StockError(f"Quantity for {product} must be a whole number.")
        if qty <= 0:
            raise StockError(f"Quantity for {product} must be more than 0.")
        merged.setdefault(product.pk, [product, 0])[1] += qty
    if not merged:
        raise StockError("Add at least one product to transfer.")

    with db_transaction.atomic():
        record = StockTransfer.objects.create(
            source=source, destination=destination, created_by=user, note=note[:200])
        for product, qty in merged.values():
            adjust(source, product, -qty, StockMovement.TRANSFER_OUT, user=user, transfer=record, note=note)
            adjust(destination, product, qty, StockMovement.TRANSFER_IN, user=user, transfer=record, note=note)
    return record


def branch_qty(store, product):
    if store is None:
        return 0
    return (BranchStock.objects.filter(store=store, product=product)
            .values_list("qty", flat=True).first()) or 0


def total_qty(product):
    return BranchStock.objects.filter(product=product).aggregate(t=Sum("qty"))["t"] or 0


def with_stock(queryset, store, name="qty"):
    """Annotate a product queryset with the quantity at ``store`` (0 if none).

    Annotating as ``qty`` keeps templates that show ``p.qty`` working; with no
    store, the total across all branches is used.
    """
    rows = BranchStock.objects.filter(product=OuterRef("pk"))
    if store is not None:
        rows = rows.filter(store=store)
        qty = Subquery(rows.values("qty")[:1], output_field=IntegerField())
    else:
        qty = Subquery(rows.values("product").annotate(t=Sum("qty")).values("t")[:1],
                       output_field=IntegerField())
    return queryset.annotate(**{name: Coalesce(qty, Value(0))})
