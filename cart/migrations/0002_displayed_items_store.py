from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """SaaS multi-tenancy: tag displayed_items with the owning store."""

    dependencies = [
        ("inventory", "0004_store_fks"),   # after the bootstrap Store exists
        ("cart", "0001_initial"),
    ]

    operations = [
        migrations.AddField("displayed_items", "store", models.ForeignKey(
            null=True, blank=True, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),
        migrations.RunSQL(
            "UPDATE cart_displayed_items SET store_id = (SELECT id FROM stores_store WHERE slug='bootstrap');",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField("displayed_items", "store", models.ForeignKey(
            null=False, blank=False, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),
        migrations.AlterField("displayed_items", "barcode", models.CharField(max_length=16, blank=False, null=False)),
        migrations.AddConstraint("displayed_items", models.UniqueConstraint(
            fields=["store", "barcode"], name="uniq_displayed_barcode_per_store")),
    ]
