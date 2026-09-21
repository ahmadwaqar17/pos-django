"""Tenancy contract: isolation, per-store uniqueness, middleware, signup."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone as dj_timezone

from cart.models import displayed_items
from inventory.models import department, deposit, product, tax
from transaction.models import productTransaction
from .models import Store, StoreMembership

timezone = dj_timezone  # django.utils.timezone.now(), for naive datetime fixtures


def make_store(name, slug):
    return Store.objects.create(name=name, slug=slug, store_name=name)


def make_product(store, barcode="1001", name="Widget"):
    return product.all_objects.create(
        store=store,
        department=department.all_objects.create(store=store, department_name=f"Dept {barcode} {store.slug}"),
        barcode=barcode,
        name=name,
        sales_price=Decimal("100.00"),
        qty=5,
        cost_price=Decimal("50.00"),
        tax_category=tax.all_objects.create(store=store, tax_category=f"T{barcode}{store.slug}", tax_percentage=Decimal("0")),
        deposit_category=deposit.all_objects.create(store=store, deposit_category=f"D{barcode}{store.slug}", deposit_value=Decimal("0")),
    )


class TenantIsolationTests(TestCase):
    """The core SaaS promise: store A can never see or touch store B's rows."""

    @classmethod
    def setUpTestData(cls):
        cls.user_a = get_user_model().objects.create_user(username="ownerA", password="pw")
        cls.user_b = get_user_model().objects.create_user(username="ownerB", password="pw")
        cls.store_a = make_store("Store A", "store-a")
        cls.store_b = make_store("Store B", "store-b")
        StoreMembership.objects.create(store=cls.store_a, user=cls.user_a)
        StoreMembership.objects.create(store=cls.store_b, user=cls.user_b)
        cls.item_a = make_product(cls.store_a, "1001", "A product")
        cls.item_b = make_product(cls.store_b, "1001", "B product")  # same barcode, different store

    def test_same_barcode_allowed_across_stores(self):
        self.assertEqual(self.item_a.barcode, self.item_b.barcode)
        self.assertNotEqual(self.item_a.pk, self.item_b.pk)

    def test_queries_are_scoped_to_the_logged_in_users_store(self):
        self.client.force_login(self.user_a)
        resp = self.client.get(reverse("register"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "A product")

        self.client.force_login(self.user_b)
        resp = self.client.get(reverse("register"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "B product")
        self.assertNotContains(resp, "A product")

    def test_store_a_cannot_add_store_b_barcode_to_cart(self):
        self.client.force_login(self.user_a)
        resp = self.client.get(reverse("cart_add", args=["1001", 1]), follow=True)
        self.assertContains(resp, "A product")   # barcode resolves to A's row only

    def test_price_lookup_is_scoped(self):
        self.client.force_login(self.user_b)
        resp = self.client.post(reverse("product_lookup_default"), {"barcode": "1001"})
        self.assertContains(resp, "B product")
        self.assertNotContains(resp, "A product")

    def test_deactivated_store_redirects_to_login_and_sees_nothing(self):
        self.store_b.is_active = False
        self.store_b.save()
        self.client.force_login(self.user_b)
        resp = self.client.get(reverse("register"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/user/login/", resp.url)

    def test_manager_blocks_writes_without_a_store_in_scope(self):
        with self.assertRaises(Exception):
            product.objects.create(  # no store kwarg, no request in scope
                department=self.item_a.department,
                barcode="9999",
                name="Orphan",
                sales_price=Decimal("1"),
                qty=1,
                tax_category=self.item_a.tax_category,
                deposit_category=self.item_a.deposit_category,
            )

    def test_transaction_lines_are_scoped_for_reports(self):
        from transaction.models import transaction as Transaction

        txn_dt = timezone.now().replace(tzinfo=None)  # naive; model localizes per store tz
        txn = Transaction.all_objects.create(
            store=self.store_a,
            transaction_dt=txn_dt,
            transaction_id="TESTA1",
            user=self.user_a,
            total_sale=Decimal("100"),
            sub_total=Decimal("100"),
            tax_total=Decimal("0"),
            deposit_total=Decimal("0"),
            payment_type="CASH",
            receipt="r",
            products="[]",
        )
        productTransaction.all_objects.create(
            store=self.store_a, transaction=txn, transaction_id_num=txn.transaction_id,
            transaction_date_time=txn.transaction_dt,            barcode="1001", name="A product",
            department="d", sales_price=Decimal("100"), qty=1, cost_price=Decimal("50"),
            tax_category="T", tax_percentage=Decimal("0"), tax_amount=Decimal("0"),
            deposit_category="D", deposit=Decimal("0"), deposit_amount=Decimal("0"),
            payment_type="CASH",
        )
        self.client.force_login(self.user_b)
        resp = self.client.get(reverse("transactionView"))
        self.assertNotContains(resp, "TESTA1")


class SignupTests(TestCase):
    def test_signup_creates_store_owner_membership_and_seed_data(self):
        resp = self.client.post(
            reverse("stores_signup"),
            {
                "store_name": "Ahmad's Corner",
                "username": "ahmad",
                "email": "a@example.com",
                "password1": "s3cure-Passw0rd!",
                "password2": "s3cure-Passw0rd!",
            },
        )
        self.assertRedirects(resp, reverse("home"), fetch_redirect_response=False)
        store = Store.objects.get(slug="ahmads-corner")
        user = get_user_model().objects.get(username="ahmad")
        self.assertEqual(store.store_name, "Ahmad's Corner")
        membership = StoreMembership.objects.get(user=user)
        self.assertEqual(membership.store, store)
        self.assertEqual(membership.role, StoreMembership.ROLE_OWNER)
        # Seed rows exist for this store only
        self.assertTrue(tax.all_objects.filter(store=store, tax_category="Zero Tax").exists())
        self.assertTrue(deposit.all_objects.filter(store=store, deposit_category="No Deposit").exists())
        self.assertTrue(department.all_objects.filter(store=store, department_name="General").exists())

    def test_signup_slug_deconflicts(self):
        make_store("Ahmads Corner", "ahmads-corner")
        self.client.post(
            reverse("stores_signup"),
            {
                "store_name": "Ahmad's Corner!",
                "username": "ahmad2",
                "password1": "s3cure-Passw0rd!",
                "password2": "s3cure-Passw0rd!",
            },
        )
        self.assertTrue(Store.objects.filter(slug="ahmads-corner-2").exists())

    def test_signup_password_mismatch_stays_on_page(self):
        resp = self.client.post(
            reverse("stores_signup"),
            {
                "store_name": "X",
                "username": "x",
                "password1": "s3cure-Passw0rd!",
                "password2": "different",
            },
        )
        self.assertEqual(resp.status_code, 200)
        # No tenant, no owner account, no membership may exist after a failed signup.
        self.assertFalse(Store.objects.filter(name="X").exists())
        self.assertFalse(get_user_model().objects.filter(username="x").exists())
        self.assertFalse(StoreMembership.objects.exists())
