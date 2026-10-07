"""Create the first branches and carry existing data across.

Safe on an empty database and on one with years of sales:
  * "Main Shop" (from STORE_NAME / STORE_ADDRESS / STORE_PHONE / RECEIPT_FOOTER)
    and a "Warehouse" are created if no branches exist yet.
  * Each product's old single quantity becomes Main Shop *opening stock*
    (that's where it physically is today), logged as an OPENING movement.
  * Superusers become owners; every other existing user a Main Shop cashier.
"""
from django.conf import settings
from django.db import migrations


def forwards(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    Membership = apps.get_model("stores", "StoreMembership")
    BranchStock = apps.get_model("stores", "BranchStock")
    Movement = apps.get_model("stores", "StockMovement")
    Product = apps.get_model("inventory", "product")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    main = Store.objects.filter(is_warehouse=False).order_by("id").first()
    if main is None:
        main = Store.objects.create(
            name=(getattr(settings, "STORE_NAME", "") or "Main Shop")[:64],
            code="main",
            address=getattr(settings, "STORE_ADDRESS", "") or "",
            phone=str(getattr(settings, "STORE_PHONE", "") or ""),
            receipt_footer=getattr(settings, "RECEIPT_FOOTER", "") or "Thank You",
        )
    if not Store.objects.filter(is_warehouse=True).exists():
        name = "Warehouse" if not Store.objects.filter(name="Warehouse").exists() else f"{main.name} Warehouse"
        Store.objects.create(name=name[:64], code="warehouse", is_warehouse=True, receipt_footer="")

    stock_rows, movements = [], []
    for product_id, qty in Product.objects.exclude(qty=0).values_list("id", "qty"):
        stock_rows.append(BranchStock(store=main, product_id=product_id, qty=qty))
        movements.append(Movement(store=main, product_id=product_id, qty_change=qty,
                                  kind="OPENING", note="Carried over from single-store stock"))
    BranchStock.objects.bulk_create(stock_rows, ignore_conflicts=True)
    Movement.objects.bulk_create(movements)

    for user in User.objects.all():
        if Membership.objects.filter(user=user).exists():
            continue
        if user.is_superuser:
            Membership.objects.create(user=user, role="owner", store=None)
        else:
            Membership.objects.create(user=user, role="cashier", store=main)


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0001_initial'),
        ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
