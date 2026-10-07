"""Stock now lives per branch in stores.BranchStock.

Runs after stores.0002, which copied every product's old quantity into
Main Shop opening stock, so nothing is lost.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0001_initial'),
        ('stores', '0002_bootstrap_branches'),
    ]

    operations = [
        migrations.RemoveField(model_name='product', name='qty'),
    ]
