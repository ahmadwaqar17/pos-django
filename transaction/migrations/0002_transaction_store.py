from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """SaaS multi-tenancy: tag transactions and their lines with the owning store."""

    dependencies = [
        ("inventory", "0004_store_fks"),   # after the bootstrap Store exists
        ("transaction", "0001_initial"),
    ]

    operations = [
        migrations.AddField("transaction", "store", models.ForeignKey(
            null=True, blank=True, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),
        migrations.AddField("productTransaction", "store", models.ForeignKey(
            null=True, blank=True, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),
        migrations.RunSQL(
            "UPDATE transaction_transaction SET store_id = (SELECT id FROM stores_store WHERE slug='bootstrap');",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "UPDATE transaction_producttransaction SET store_id = "
            "(SELECT store_id FROM transaction_transaction t WHERE t.id = transaction_producttransaction.transaction_id);",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "UPDATE transaction_producttransaction SET store_id = (SELECT id FROM stores_store WHERE slug='bootstrap') "
            "WHERE store_id IS NULL;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField("transaction", "store", models.ForeignKey(
            null=False, blank=False, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),
        migrations.AlterField("productTransaction", "store", models.ForeignKey(
            null=False, blank=False, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),
        migrations.AlterField("transaction", "transaction_id", models.CharField(max_length=50, editable=False, null=False)),
        migrations.AddConstraint("transaction", models.UniqueConstraint(
            fields=["store", "transaction_id"], name="uniq_transaction_id_per_store")),
    ]
