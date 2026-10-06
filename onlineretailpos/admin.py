from django.contrib import admin
from django.contrib.admin.apps import AdminConfig
from django.conf import settings



class MyAdminSite(admin.AdminSite):
    site_header = f"{settings.STORE_NAME} - Data Portal"
    site_title = settings.STORE_NAME
    index_title = "Data Administration"

    def index(self, request, extra_context=None):
        """Admin home: stock and today's-sales figures above the model list."""
        from django.db.models import Count, Sum
        from django.utils import timezone
        from inventory.models import product
        from transaction.models import transaction

        low = settings.LOW_STOCK_THRESHOLD
        products = product.objects.all()
        today = transaction.objects.filter(transaction_dt__date=timezone.localdate()).aggregate(
            receipts=Count("id"), sales=Sum("total_sale"))
        extra_context = {
            **(extra_context or {}),
            "pos_stats": {
                "products": products.count(),
                "low_stock": products.filter(qty__gt=0, qty__lte=low).count(),
                "out_of_stock": products.filter(qty__lte=0).count(),
                "no_cost": products.filter(cost_price__lte=0).count(),
                "today_sales": today["sales"] or 0,
                "today_receipts": today["receipts"] or 0,
            },
            "low_stock_threshold": low,
        }
        return super().index(request, extra_context)


class MyAdminConfig(AdminConfig):
    default_site = 'onlineretailpos.admin.MyAdminSite'

