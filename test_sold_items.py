import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onlineretailpos.settings.devlopement")
import django
django.setup()

from decimal import Decimal
from datetime import date, datetime

from django.test import Client
from django.urls import reverse

from transaction.models import transaction, productTransaction
from django.contrib.auth import get_user_model

# The stores table must exist for transaction.store_id.
try:
    from stores.models import Store
except Exception:
    Store = None

if Store is not None and not Store.objects.exists():
    Store.objects.create(
        id=1, name="PRIMARY", slug="primary", store_name="PRIMARY",
        store_address="", store_phone="", receipt_footer="",
        currency="PKR", timezone="US/Eastern", is_active=True,
        plan="bootstrap", created_at=datetime.now(),
    )

u = get_user_model().objects.create_user(username="rptuser7", password="pw-12345")
t = transaction.objects.create(
    user=u, transaction_id="TEST-1007", total_sale=250, sub_total=250,
    payment_type="CASH", receipt="", products="[]",
    transaction_dt=datetime.combine(date.today(), datetime.min.time()),
    store_id=1,
)
productTransaction.objects.create(
    transaction=t, transaction_id_num=t.transaction_id,
    transaction_date_time=t.transaction_dt,
    barcode="RPT-7", name="Report Test Tee 7", department="Clothing",
    sales_price=Decimal("250.00"), qty=2, cost_price=Decimal("150.00"),
    tax_category="Zero Tax", tax_percentage=Decimal("0.000"), tax_amount=0,
    deposit_category="No Deposit", deposit=Decimal("0.00"),
    deposit_amount=0, payment_type=t.payment_type, store_id=1,
)

c = Client()
c.force_login(u)
resp = c.get(reverse("sold_items_report"))

print("status:", resp.status_code)
print("rows count:", len(resp.context["rows"]))
print("total_qty:", resp.context["total_qty"])
print("total_revenue:", resp.context["total_revenue"])
print("form present:", "form" in resp.context)
print("html has table header:", b"Receipt #" in resp.content)
print("html cashier col:", b"Cashier" in resp.content)
print("html store col:", b"Store" in resp.content)
print("url:", reverse("sold_items_report"))
print("first row store field present:", "transaction__store_id" in resp.context["rows"][0] if resp.context["rows"] else None)
print("first row store_name field present:", "transaction__store__store_name" in resp.context["rows"][0] if resp.context["rows"] else None)
