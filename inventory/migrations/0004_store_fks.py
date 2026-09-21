from django.db import migrations, models
import django.db.models.deletion


def create_bootstrap_store(apps, schema_editor):
    """One Store for all pre-existing rows, so the upgrade is seamless."""
    import os

    Store = apps.get_model("stores", "Store")
    if Store.objects.filter(slug="bootstrap").exists():
        return
    name = os.getenv("STORE_NAME") or "Bootstrap Store"
    Store.objects.create(
        name=name, slug="bootstrap", store_name=name,
        store_address="", store_phone="", receipt_footer="Thank You",
        currency="PKR", timezone="US/Eastern", is_active=True, plan="bootstrap",
    )


def remove_bootstrap_store(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    Store.objects.filter(slug="bootstrap").delete()


class Migration(migrations.Migration):
    """Add `store` FKs to all business models (SaaS multi-tenancy).

    Written by hand because the change is a three-step dance autogenerator
    can't express in one pass:
      1. add nullable store FK + create the bootstrap Store,
      2. backfill every existing row to the bootstrap store,
      3. tighten to non-null and swap global unique -> per-store unique.
    """

    dependencies = [
        ("stores", "0001_initial"),
        ("inventory", "0001_initial"),
    ]

    operations = [
        # -- 1. nullable FKs ------------------------------------------------
        migrations.AddField("product", "store", models.ForeignKey(
            null=True, blank=True, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),
        migrations.AddField("department", "store", models.ForeignKey(
            null=True, blank=True, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),
        migrations.AddField("tax", "store", models.ForeignKey(
            null=True, blank=True, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),
        migrations.AddField("deposit", "store", models.ForeignKey(
            null=True, blank=True, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),

        # -- bootstrap tenant (portable: no SQL-dialect functions) ----------
        migrations.RunPython(create_bootstrap_store, remove_bootstrap_store),

        # -- 2. backfill ------------------------------------------------------
        migrations.RunSQL(
            "UPDATE inventory_product SET store_id = (SELECT id FROM stores_store WHERE slug='bootstrap');",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "UPDATE inventory_department SET store_id = (SELECT id FROM stores_store WHERE slug='bootstrap');",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "UPDATE inventory_tax SET store_id = (SELECT id FROM stores_store WHERE slug='bootstrap');",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "UPDATE inventory_deposit SET store_id = (SELECT id FROM stores_store WHERE slug='bootstrap');",
            reverse_sql=migrations.RunSQL.noop,
        ),

        # -- 3. non-null + per-store uniqueness ------------------------------
        migrations.AlterField("product", "store", models.ForeignKey(
            null=False, blank=False, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),
        migrations.AlterField("department", "store", models.ForeignKey(
            null=False, blank=False, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),
        migrations.AlterField("tax", "store", models.ForeignKey(
            null=False, blank=False, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),
        migrations.AlterField("deposit", "store", models.ForeignKey(
            null=False, blank=False, on_delete=django.db.models.deletion.RESTRICT,
            to="stores.store")),

        migrations.AlterField("product", "barcode", models.CharField(max_length=16, blank=False, null=False)),
        migrations.AlterField("department", "department_name", models.CharField(max_length=32, null=False, blank=False)),
        migrations.AlterField("department", "department_slug", models.SlugField(max_length=32, blank=True)),
        migrations.AlterField("tax", "tax_category", models.CharField(max_length=32, null=False, blank=False)),
        migrations.AlterField("deposit", "deposit_category", models.CharField(max_length=32, null=False, blank=False)),

        migrations.AddConstraint("product", models.UniqueConstraint(fields=["store", "barcode"], name="uniq_product_barcode_per_store")),
        migrations.AddConstraint("department", models.UniqueConstraint(fields=["store", "department_name"], name="uniq_department_name_per_store")),
        migrations.AddConstraint("department", models.UniqueConstraint(fields=["store", "department_slug"], name="uniq_department_slug_per_store")),
        migrations.AddConstraint("tax", models.UniqueConstraint(fields=["store", "tax_category"], name="uniq_tax_category_per_store")),
        migrations.AddConstraint("deposit", models.UniqueConstraint(fields=["store", "deposit_category"], name="uniq_deposit_category_per_store")),
    ]
