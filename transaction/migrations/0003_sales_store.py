"""Every sale (and sale line) belongs to the branch that rang it up.

Existing sales were all made at the original single shop, so they are
assigned to the first non-warehouse branch created in stores.0002.
The column becomes required in 0004 (a separate migration, so PostgreSQL
doesn't refuse to ALTER a table it just updated in the same transaction).
"""
import django.db.models.deletion
from django.db import migrations, models


def assign_existing_sales(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    Transaction = apps.get_model("transaction", "transaction")
    Line = apps.get_model("transaction", "productTransaction")
    if not (Transaction.objects.exists() or Line.objects.exists()):
        return
    main = Store.objects.filter(is_warehouse=False).order_by("id").first()
    Transaction.objects.filter(store__isnull=True).update(store=main)
    Line.objects.filter(store__isnull=True).update(store=main)


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0002_transaction_discount'),
        ('stores', '0002_bootstrap_branches'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='store',
            field=models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sales', to='stores.store'),
        ),
        migrations.AddField(
            model_name='producttransaction',
            name='store',
            field=models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sale_lines', to='stores.store'),
        ),
        migrations.RunPython(assign_existing_sales, migrations.RunPython.noop),
    ]
