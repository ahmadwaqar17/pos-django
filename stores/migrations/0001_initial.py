from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="Store",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=60, unique=True)),
                ("store_name", models.CharField(max_length=64)),
                ("store_address", models.TextField(blank=True, default="")),
                ("store_phone", models.CharField(blank=True, default="", max_length=32)),
                ("receipt_footer", models.CharField(blank=True, default="Thank You", max_length=120)),
                ("currency", models.CharField(default="PKR", max_length=8)),
                ("timezone", models.CharField(default="US/Eastern", max_length=64)),
                ("is_active", models.BooleanField(default=True)),
                ("plan", models.CharField(default="trial", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "Store", "verbose_name_plural": "Stores"},
        ),
        migrations.CreateModel(
            name="StoreMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("owner", "Owner"), ("cashier", "Cashier")], default="owner", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="stores.store")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="store_membership", to="auth.user")),
            ],
            options={"verbose_name": "Store membership", "verbose_name_plural": "Store memberships"},
        ),
    ]
