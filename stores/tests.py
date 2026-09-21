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


class PlatformSuperAdminTests(TestCase):
    """The platform area: super admins manage stores and assign users."""

    @classmethod
    def setUpTestData(cls):
        cls.super_admin = get_user_model().objects.create_user(username="boss", password="pw")
        StoreMembership.objects.create(user=cls.super_admin, role=StoreMembership.ROLE_SUPER_ADMIN)
        cls.owner = get_user_model().objects.create_user(username="tenant", password="pw")
        cls.store = Store.objects.create(name="Tenant Store", slug="tenant", store_name="Tenant Store")
        StoreMembership.objects.create(store=cls.store, user=cls.owner, role=StoreMembership.ROLE_OWNER)

    def login_as(self, user):
        self.client.force_login(user)

    def test_super_admin_login_lands_on_platform_dashboard(self):
        self.client.force_login(self.super_admin)
        resp = self.client.get("/user/login/", follow=False)  # logged in: public path is fine
        dashboard = self.client.get(reverse("platform_dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Tenant Store")

    def test_tenant_user_cannot_open_platform(self):
        self.login_as(self.owner)
        resp = self.client.get(reverse("platform_dashboard"))
        # Middleware bounces tenants to the home redirect ('/'), which itself
        # resolves to the sales dashboard; either way, no platform content.
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("/platform", resp.url)

    def test_anonymous_cannot_open_platform(self):
        resp = self.client.get(reverse("platform_dashboard"))
        # login_required by the view: redirected to login, or rejected by the
        # permission decorator (403) — both keep the anonymous user out.
        self.assertIn(resp.status_code, (302, 403))
        if resp.status_code == 302:
            self.assertIn("/user/login/", resp.url)

    def test_add_store_creates_store_and_seeds_defaults(self):
        self.login_as(self.super_admin)
        resp = self.client.post(reverse("platform_add_store"), {
            "store_name": "New Corner Shop",
            "store_address": "Main St 1",
            "store_phone": "0300-1234567",
            "currency": "PKR",
            "timezone": "US/Eastern",
            "plan": "trial",
        })
        store = Store.objects.get(slug="new-corner-shop")
        self.assertRedirects(resp, reverse("platform_store_users", args=[store.id]), fetch_redirect_response=False)
        self.assertTrue(tax.all_objects.filter(store=store, tax_category="Zero Tax").exists())
        self.assertTrue(deposit.all_objects.filter(store=store, deposit_category="No Deposit").exists())
        self.assertTrue(department.all_objects.filter(store=store, department_name="General").exists())

    def test_assign_new_user_to_store_with_email_and_password(self):
        self.login_as(self.super_admin)
        resp = self.client.post(reverse("platform_store_users", args=[self.store.id]), {
            "username": "cashier1",
            "email": "cashier1@example.com",
            "password": "s3cure-Passw0rd!",
            "role": "cashier",
        })
        self.assertRedirects(resp, reverse("platform_store_users", args=[self.store.id]), fetch_redirect_response=False)
        user = get_user_model().objects.get(username="cashier1")
        self.assertEqual(user.email, "cashier1@example.com")
        self.assertTrue(user.check_password("s3cure-Passw0rd!"))
        self.assertEqual(user.store_membership.store, self.store)
        self.assertEqual(user.store_membership.role, "cashier")

    def test_assign_existing_user_moves_them_to_this_store(self):
        self.login_as(self.super_admin)
        resp = self.client.post(reverse("platform_store_users", args=[self.store.id]), {
            "username": "tenant",
            "email": "t@example.com",
            "password": "fresh-Passw0rd!",
            "role": "owner",
        })
        self.assertEqual(resp.status_code, 302)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.store_membership.store, self.store)
        self.assertTrue(self.owner.check_password("fresh-Passw0rd!"))

    def test_user_in_another_store_is_rejected_not_stolen(self):
        other = Store.objects.create(name="Other", slug="other", store_name="Other")
        other_owner = get_user_model().objects.create_user(username="otherowner", password="pw")
        StoreMembership.objects.create(store=other, user=other_owner, role=StoreMembership.ROLE_OWNER)
        self.login_as(self.super_admin)
        resp = self.client.post(reverse("platform_store_users", args=[self.store.id]), {
            "username": "otherowner",
            "email": "o@example.com",
            "password": "whatever-Passw0rd!",
            "role": "cashier",
        })
        self.assertEqual(resp.status_code, 200)          # form re-rendered with error
        other_owner.refresh_from_db()
        self.assertEqual(other_owner.store_membership.store, other)   # untouched

    def test_suspended_store_kicks_tenant_but_not_super_admin(self):
        self.store.is_active = False
        self.store.save()
        self.login_as(self.owner)
        self.assertEqual(self.client.get(reverse("register")).status_code, 302)
        self.login_as(self.super_admin)
        self.assertEqual(self.client.get(reverse("platform_dashboard")).status_code, 200)

    def test_super_admin_membership_cannot_belong_to_a_store(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            StoreMembership(store=self.store, user=None, role=StoreMembership.ROLE_SUPER_ADMIN).clean()
