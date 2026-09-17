"""Executable contract for the register → payment → receipt flow.

Kept deliberately small: one fixture set, two helpers, and a table wherever
the cases differ only in their input (payment type, tendered amount).
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import department, deposit, product, tax

from .models import transaction

CART = settings.CART_SESSION_ID
PRICE = Decimal("2500.00")


class RegisterSaleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="cashier", password="pw")
        cls.item = product.objects.create(
            department=department.objects.create(department_name="Clothing"),
            barcode="1001",
            name="Men's Kameez Shalwar",
            sales_price=PRICE,
            qty=10,
            cost_price=Decimal("1000.00"),
            tax_category=tax.objects.create(tax_category="Zero Tax", tax_percentage=Decimal("0")),
            deposit_category=deposit.objects.create(
                deposit_category="No Deposit", deposit_value=Decimal("0.00")
            ),
        )

    def setUp(self):
        self.client.force_login(self.user)

    # ---- helpers -------------------------------------------------------
    def add_to_cart(self, barcode="1001", qty=1):
        self.client.get(reverse("cart_add", args=[barcode, qty]))

    def pay(self, kind, value):
        return self.client.get(reverse("endTransaction", args=[kind, value]))

    def last_sale(self):
        return transaction.objects.latest("date_time")

    def receipt_html(self, trans_no, **query):
        url = reverse("endTransactionReceipt", args=[trans_no])
        return self.client.get(url, query).content.decode()

    # ---- persistence ---------------------------------------------------
    def test_cash_sale_is_persisted_stock_reduced_and_cart_cleared(self):
        self.add_to_cart(qty=2)

        response = self.pay("cash", "6000")

        sale = self.last_sale()
        self.assertEqual(sale.payment_type, "CASH")
        self.assertEqual(sale.total_sale, Decimal("5000.00"))
        self.assertEqual(sale.user, self.user)
        self.item.refresh_from_db()
        self.assertEqual(self.item.qty, 8)                     # one decrement per unit sold
        self.assertEqual(self.client.session[CART], {})        # cart emptied
        self.assertEqual(
            response.url,
            f"/endTransaction/{sale.transaction_id}/?type=cash&value=6000.0&total=5000.0",
        )

    def test_both_card_types_are_persisted(self):
        for value in ("EBT", "DEBIT_CREDIT"):
            self.add_to_cart()
            self.pay("card", value)

        self.assertEqual(
            sorted(transaction.objects.values_list("payment_type", flat=True)),
            ["DEBIT/CREDIT", "EBT"],
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.qty, 8)
        self.assertEqual(self.client.session[CART], {})

    # ---- boundary ------------------------------------------------------
    def test_underpaid_cash_is_refused_and_the_cart_survives(self):
        self.add_to_cart()

        response = self.pay("cash", "2499")

        self.assertRedirects(response, reverse("register"), fetch_redirect_response=False)
        self.assertFalse(transaction.objects.exists())
        self.assertEqual(self.client.session[CART]["1001"]["quantity"], 1)

    # ---- receipt: tendered, total, expected change line, expected badge --
    CHANGE_CASES = [
        ("3500.0", "3300.0", "PKR 200.00", "badge-success"),
        ("3300.0", "3300.0", "PKR 0.00", "badge-success"),
        ("3000.0", "3300.0", "PKR -300.00", "badge-danger"),
    ]

    def test_cash_receipt_shows_the_change_the_customer_is_owed(self):
        self.add_to_cart(qty=2)
        self.pay("cash", "6000")
        sale = self.last_sale()

        for value, total, change, badge in self.CHANGE_CASES:
            with self.subTest(tendered=value, total=total):
                html = self.receipt_html(sale.transaction_id, type="cash", value=value, total=total)
                self.assertIn(change, html)
                self.assertIn(badge, html)

    def test_card_receipt_reports_no_change_row(self):
        self.add_to_cart()
        self.pay("card", "EBT")
        sale = self.last_sale()

        html = self.receipt_html(sale.transaction_id, type="card", value="EBT", total="2500.0")

        self.assertIn("CARD TRANSACTION", html)
        self.assertNotIn("Change :", html)
