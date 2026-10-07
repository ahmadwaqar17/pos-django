import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0001_initial'),
        ('transaction', '0002_transaction_discount'),
    ]

    operations = [
        migrations.CreateModel(
            name='Store',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=64, unique=True)),
                ('code', models.SlugField(help_text='Short unique code, e.g. MAIN or WH.', max_length=16, unique=True)),
                ('address', models.CharField(blank=True, default='', max_length=200)),
                ('phone', models.CharField(blank=True, default='', max_length=32)),
                ('receipt_footer', models.CharField(blank=True, default='Thank You', max_length=120)),
                ('is_warehouse', models.BooleanField(default=False, help_text='The central stock location. It can hold and send stock but cannot sell.')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'verbose_name': 'Branch', 'verbose_name_plural': 'Branches', 'ordering': ('is_warehouse', 'name')},
        ),
        migrations.CreateModel(
            name='StockTransfer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='stock_transfers', to=settings.AUTH_USER_MODEL)),
                ('destination', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers_in', to='stores.store')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers_out', to='stores.store')),
            ],
            options={'ordering': ('-created_at',)},
        ),
        migrations.CreateModel(
            name='StoreMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('owner', 'Owner (all branches)'), ('manager', 'Manager'), ('cashier', 'Cashier')], default='cashier', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('store', models.ForeignKey(blank=True, help_text='Leave empty for owners (they work across all branches).', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='memberships', to='stores.store')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='store_membership', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Staff assignment', 'verbose_name_plural': 'Staff assignments'},
        ),
        migrations.CreateModel(
            name='StockMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('qty_change', models.IntegerField()),
                ('kind', models.CharField(choices=[('OPENING', 'Opening stock'), ('RECEIVE', 'Received'), ('SALE', 'Sale'), ('RETURN', 'Customer return'), ('TRANSFER_IN', 'Transfer in'), ('TRANSFER_OUT', 'Transfer out'), ('ADJUST', 'Adjustment')], max_length=16)),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='inventory.product')),
                ('sale', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='transaction.transaction')),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='movements', to='stores.store')),
                ('transfer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='movements', to='stores.stocktransfer')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-created_at', '-id'), 'indexes': [models.Index(fields=['store', 'product'], name='stockmove_store_product_idx')]},
        ),
        migrations.CreateModel(
            name='BranchStock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('qty', models.IntegerField(default=0)),
                ('last_counted_at', models.DateTimeField(blank=True, null=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branch_stock', to='inventory.product')),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock', to='stores.store')),
            ],
            options={'verbose_name': 'Branch stock', 'verbose_name_plural': 'Branch stock',
                     'constraints': [models.UniqueConstraint(fields=('store', 'product'), name='unique_stock_per_branch')]},
        ),
    ]
