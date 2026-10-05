"""Tests for the manual per-transaction discount feature."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import deposit, department, product, tax
from transaction.models import transaction


class DiscountFlowTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.cashier = get_user_model().objects.create_user(
            username="cash", password="pw-12345"
        )
        dept = department.objects.create(
            department_name="Clothing", department_desc="d"
        )
        zx = tax.objects.create(tax_category="Zero Tax", tax_percentage=Decimal("0.000"))
        nd = deposit.objects.create(deposit_category="No Deposit", deposit_value=Decimal("0.00"))
        product.objects.create(
            barcode="TEST-1", name="Test Tee", department=dept,
            sales_price=Decimal("100.00"), qty=50,
            tax_category=zx, deposit_category=nd,
        )

    def setUp(self):
        self.client.force_login(get_user_model().objects.get(username="cash"))

    def _fill_cart(self):
        self.client.get("/cart/add/TEST-1/3/")  # 3 x 100 = 300 gross

    def test_set_discount_updates_register_totals(self):
        self._fill_cart()
        resp = self.client.get("/register/discount/10/")
        self.assertEqual(resp.status_code, 302)

        resp = self.client.get("/register/")
        self.assertContains(resp, "Discount (10%)")
        self.assertContains(resp, "-30.00")
        # Payment buttons carry the discounted total.
        self.assertContains(resp, "270.0")

    def test_discount_out_of_range_is_clamped_to_zero(self):
        self._fill_cart()
        self.client.get("/register/discount/150/")
        self.assertEqual(self.client.session["Discount_Percent"], 0)
        self.client.get("/register/discount/-5/")
        self.assertEqual(self.client.session["Discount_Percent"], 0)
        self.client.get("/register/discount/10.5/")
        self.assertEqual(self.client.session["Discount_Percent"], 10.5)

    def test_cash_checkout_applies_discount_end_to_end(self):
        self._fill_cart()
        self.client.get("/register/discount/10/")

        resp = self.client.get("/endTransaction/cash/300/")
        self.assertEqual(resp.status_code, 302)
        txn = transaction.objects.get()
        self.assertEqual(txn.total_sale, Decimal("270.00"))
        self.assertEqual(float(txn.discount_percent), 10.0)
        self.assertEqual(float(txn.discount_amount), 30.00)

        # Receipt shows subtotal, discount line and discounted total.
        self.assertIn("Subtotal:", txn.receipt)
        self.assertIn("Discount 10%:", txn.receipt)
        self.assertIn("PKR   270.00", txn.receipt)
        # Session discount resets after the sale.
        self.assertEqual(self.client.session["Discount_Percent"], 0)

    def test_card_checkout_applies_discount(self):
        self._fill_cart()
        self.client.get("/register/discount/25/")
        self.client.get("/endTransaction/card/DEBIT_CREDIT/")
        txn = transaction.objects.get()
        self.assertEqual(txn.total_sale, Decimal("225.00"))
        self.assertEqual(float(txn.discount_amount), 75.0)

    def test_no_discount_transaction_has_null_fields(self):
        self._fill_cart()
        self.client.get("/endTransaction/cash/300/")
        txn = transaction.objects.get()
        self.assertIsNone(txn.discount_percent)
        self.assertIsNone(txn.discount_amount)
        self.assertNotIn("Discount", txn.receipt)

    def test_clearing_cart_resets_discount(self):
        self._fill_cart()
        self.client.get("/register/discount/10/")
        self.client.get("/register/cart_clear/")
        self.assertEqual(self.client.session["Discount_Percent"], 0)

    def test_change_is_calculated_on_discounted_total(self):
        self._fill_cart()
        self.client.get("/register/discount/10/")
        self.client.get("/endTransaction/cash/500/")
        txn = transaction.objects.get()
        # Receipt CHANGE line = 500 - 270.
        self.assertIn("PKR   230.00", txn.receipt)
