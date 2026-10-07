"""Tests for the manual per-transaction discount feature."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import deposit, department, product, tax
from stores.models import Store, StoreMembership
from transaction.models import transaction


def shop():
    return Store.objects.filter(is_warehouse=False).first()


def make_cashier(username, store=None):
    user = get_user_model().objects.create_user(username=username, password="pw-12345")
    StoreMembership.objects.create(user=user, role=StoreMembership.ROLE_CASHIER, store=store or shop())
    return user


class DiscountFlowTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.cashier = make_cashier("cash")
        dept = department.objects.create(
            department_name="Clothing", department_desc="d"
        )
        zx = tax.objects.create(tax_category="Zero Tax", tax_percentage=Decimal("0.000"))
        nd = deposit.objects.create(deposit_category="No Deposit", deposit_value=Decimal("0.00"))
        product.objects.create(
            barcode="TEST-1", name="Test Tee", department=dept,
            sales_price=Decimal("100.00"),
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


class CartRemoveTests(TestCase):
    """Per-line cart removal: one row gone, totals recompute, discount cleared."""

    @classmethod
    def setUpTestData(cls):
        dept = department.objects.create(department_name="Clothing", department_desc="d")
        zx = tax.objects.create(tax_category="Zero Tax", tax_percentage=Decimal("0.000"))
        nd = deposit.objects.create(deposit_category="No Deposit", deposit_value=Decimal("0.00"))
        product.objects.create(
            barcode="LCR-1", name="Line-Clear Test", department=dept,
            sales_price=Decimal("200.00"), tax_category=zx, deposit_category=nd,
        )
        product.objects.create(
            barcode="TEST-1", name="Test Tee", department=dept,
            sales_price=Decimal("100.00"), tax_category=zx, deposit_category=nd,
        )
        make_cashier("rmadmin")

    def setUp(self):
        self.client.force_login(get_user_model().objects.get(username="rmadmin"))
        self.client.get("/cart/add/LCR-1/2/")   # 2 x 200 = 400
        self.client.get("/cart/add/TEST-1/1/")  # 1 x 100 = 100

    def test_remove_line_clears_that_line_only(self):
        response = self.client.get("/cart/remove/LCR-1/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/register/").status_code, 200)
        cart_data = self.client.session["cart"]
        self.assertNotIn("LCR-1", cart_data)
        self.assertIn("TEST-1", cart_data)

    def test_totals_recompute_after_removal(self):
        before_total = self.client.get("/register/").context["total"]
        self.assertGreater(before_total, 300)

        self.client.get("/cart/remove/LCR-1/")
        after_total = self.client.get("/register/").context["total"]

        # Remaining line: TEST-1 qty 1 @ 100.00 (zero tax/deposit fixture).
        self.assertAlmostEqual(float(after_total), 100.00, places=2)
        self.assertLess(after_total, before_total)

    def test_remove_nonexistent_barcode_is_noop(self):
        response = self.client.get("/cart/remove/DOES-NOT-EXIST-9999/")
        self.assertEqual(response.status_code, 302)
        cart = self.client.session["cart"]
        self.assertIn("LCR-1", cart)
        self.assertIn("TEST-1", cart)

    def test_discount_cleared_when_last_line_removed(self):
        self.client.get("/register/discount/15/")
        self.client.get("/cart/remove/LCR-1/")
        self.client.get("/cart/remove/TEST-1/")
        resp = self.client.get("/register/")
        self.assertEqual(resp.context["discount_percent"], 0)
        self.assertEqual(resp.context["discount_amount"], 0.0)
