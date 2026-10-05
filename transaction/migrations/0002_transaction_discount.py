from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='discount_percent',
            field=models.DecimalField(blank=True, decimal_places=2, default=None,
                                      editable=False, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name='transaction',
            name='discount_amount',
            field=models.DecimalField(blank=True, decimal_places=2, default=None,
                                      editable=False, max_digits=7, null=True),
        ),
    ]
