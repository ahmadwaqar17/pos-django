from django.db import migrations, models


class Migration(migrations.Migration):
    """Platform super-admin role: membership with role='super_admin' and no store."""

    dependencies = [
        ("stores", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="storemembership",
            name="store",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="memberships",
                to="stores.store",
            ),
        ),
        migrations.AlterField(
            model_name="storemembership",
            name="role",
            field=models.CharField(
                choices=[
                    ("owner", "Owner"),
                    ("cashier", "Cashier"),
                    ("super_admin", "Super Admin"),
                ],
                default="owner",
                max_length=16,
            ),
        ),
    ]
