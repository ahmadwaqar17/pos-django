import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0003_sales_store'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='store',
            field=models.ForeignKey(editable=False, on_delete=django.db.models.deletion.PROTECT, related_name='sales', to='stores.store'),
        ),
        migrations.AlterField(
            model_name='producttransaction',
            name='store',
            field=models.ForeignKey(editable=False, on_delete=django.db.models.deletion.PROTECT, related_name='sale_lines', to='stores.store'),
        ),
    ]
