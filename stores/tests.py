"""Multi-branch stock and sales: stock helper, sale flow, roles, transfers, migration."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from inventory.models import deposit, department, product, tax
from transaction.models import productTransaction, transaction

from . import stock
from .models import BranchStock, StockMovement, StockTransfer, Store, StoreMembership

User = get_user_model()


class BranchFixture(TestCase):
    """Main shop + warehouse (from the bootstrap migration) + a second shop."""

    @classmethod
    def setUpTestData(cls):
        cls.main = Store.objects.filter(is_warehouse=False).first()
        cls.wh = Store.warehouse()
        cls.gulberg = Store.objects.create(name="Gulberg", code="gulberg")
        dept = department.objects.create(department_name="Clothing")
        zt = tax.objects.create(tax_category="Zero Tax", tax_percentage=Decimal("0"))
        nd = deposit.objects.create(deposit_category="No Deposit", deposit_value=Decimal("0"))
        cls.shirt = product.objects.create(barcode="SH-1", name="Shirt", sales_price=Decimal("1000"),
                                           department=dept, tax_category=zt, deposit_category=nd)
        cls.owner = User.objects.create_superuser("boss", "b@example.com", "pw")
        cls.cashier = User.objects.create_user("cash", password="pw")
        StoreMembership.objects.create(user=cls.cashier, role="cashier", store=cls.gulberg)
        cls.manager = User.objects.create_user("mgr", password="pw")
        StoreMembership.objects.create(user=cls.manager, role="manager", store=cls.gulberg)

    def login(self, user):
        self.client.force_login(user)


class StockHelperTests(BranchFixture):

    def test_adjust_creates_row_and_logs_movement(self):
        new = stock.adjust(self.wh, self.shirt, 10, StockMovement.RECEIVE, user=self.owner)
        self.assertEqual(new, 10)
        self.assertEqual(stock.branch_qty(self.wh, self.shirt), 10)
        self.assertEqual(stock.branch_qty(self.gulberg, self.shirt), 0)
        m = StockMovement.objects.get()
        self.assertEqual((m.store, m.qty_change, m.kind), (self.wh, 10, StockMovement.RECEIVE))

    def test_stock_can_go_negative(self):
        stock.adjust(self.gulberg, self.shirt, -2, StockMovement.SALE)
        self.assertEqual(stock.branch_qty(self.gulberg, self.shirt), -2)

    def test_transfer_moves_stock_atomically(self):
        stock.adjust(self.wh, self.shirt, 10, StockMovement.RECEIVE)
        t = stock.transfer(self.wh, self.gulberg, [(self.shirt, 4)], user=self.owner, note="restock")
        self.assertEqual(stock.branch_qty(self.wh, self.shirt), 6)
        self.assertEqual(stock.branch_qty(self.gulberg, self.shirt), 4)
        self.assertEqual(t.movements.count(), 2)

    def test_invalid_transfer_moves_nothing(self):
        stock.adjust(self.wh, self.shirt, 10, StockMovement.RECEIVE)
        for src, dst, lines in [
            (self.wh, self.wh, [(self.shirt, 1)]),      # same location
            (self.wh, self.gulberg, [(self.shirt, 0)]),  # zero qty
            (self.wh, self.gulberg, []),                 # nothing to move
        ]:
            with self.assertRaises(stock.StockError):
                stock.transfer(src, dst, lines)
        self.assertEqual(stock.branch_qty(self.wh, self.shirt), 10)
        self.assertEqual(StockTransfer.objects.count(), 0)

    def test_with_stock_annotation(self):
        stock.adjust(self.wh, self.shirt, 7, StockMovement.RECEIVE)
        stock.adjust(self.gulberg, self.shirt, 3, StockMovement.RECEIVE)
        qs = product.objects.filter(pk=self.shirt.pk)
        self.assertEqual(stock.with_stock(qs, self.gulberg).get().qty, 3)
        self.assertEqual(stock.with_stock(qs, self.main).get().qty, 0)
        self.assertEqual(stock.with_stock(qs, None).get().qty, 10)


class SaleFlowTests(BranchFixture):

    def setUp(self):
        stock.adjust(self.gulberg, self.shirt, 5, StockMovement.RECEIVE)
        self.login(self.cashier)

    def test_sale_records_branch_and_reduces_that_branch_only(self):
        stock.adjust(self.main, self.shirt, 5, StockMovement.RECEIVE)
        self.client.get("/cart/add/SH-1/2/")
        self.client.get("/endTransaction/cash/5000/")
        sale = transaction.objects.get()
        self.assertEqual(sale.store, self.gulberg)
        self.assertEqual(productTransaction.objects.get().store, self.gulberg)
        self.assertEqual(stock.branch_qty(self.gulberg, self.shirt), 3)
        self.assertEqual(stock.branch_qty(self.main, self.shirt), 5)
        self.assertTrue(StockMovement.objects.filter(kind=StockMovement.SALE, sale=sale, qty_change=-2).exists())
        self.assertIn("Gulberg", sale.receipt)

    def test_return_adds_stock_back(self):
        self.client.get("/cart/add/SH-1/1/")
        self.client.get("/register/returns_transaction/")
        self.client.get("/endTransaction/card/DEBIT_CREDIT/")
        self.assertEqual(stock.branch_qty(self.gulberg, self.shirt), 6)
        self.assertTrue(StockMovement.objects.filter(kind=StockMovement.RETURN).exists())

    def test_overselling_warns_but_allows(self):
        self.client.get("/cart/add/SH-1/7/")
        resp = self.client.get("/register/")
        self.assertContains(resp, "Low stock")
        self.client.get("/endTransaction/cash/10000/")
        self.assertEqual(transaction.objects.count(), 1)
        self.assertEqual(stock.branch_qty(self.gulberg, self.shirt), -2)


class RoleAndScopeTests(BranchFixture):

    def _sale_at(self, store):
        user = User.objects.create_user(f"c-{store.code}", password="pw")
        StoreMembership.objects.create(user=user, role="cashier", store=store)
        self.client.force_login(user)
        self.client.get("/cart/add/SH-1/1/")
        self.client.get("/endTransaction/cash/1000/")
        self.client.logout()
        return transaction.objects.filter(store=store).latest("id")

    def test_cashier_is_kept_to_the_till(self):
        self.login(self.cashier)
        self.assertEqual(self.client.get("/").url, "/register/")
        for url in ["/dashboard_sales/", "/stock/", "/stock/transfers/new/", "/inventory/"]:
            self.assertEqual(self.client.get(url).url, "/register/", url)
        self.assertEqual(self.client.get("/register/").status_code, 200)

    def test_manager_and_owner_can_open_stock_pages(self):
        for user in (self.manager, self.owner):
            self.login(user)
            for url in ["/stock/", "/stock/transfers/", "/stock/transfers/new/", "/stock/movements/", "/inventory/"]:
                self.assertEqual(self.client.get(url).status_code, 200, (user, url))

    def test_cashier_only_sees_own_branch_sales(self):
        mine = self._sale_at(self.gulberg)
        other = self._sale_at(self.main)
        self.login(self.cashier)
        html = self.client.get("/transaction/").content.decode()
        self.assertIn(mine.transaction_id, html)
        self.assertNotIn(other.transaction_id, html)
        self.assertEqual(self.client.get(f"/transaction_receipt/{other.transaction_id}/").status_code, 404)

    def test_owner_switches_branch_and_all_branches(self):
        mine = self._sale_at(self.gulberg)
        self.login(self.owner)
        self.client.post("/branch/switch/", {"store": self.main.pk})
        self.assertNotIn(mine.transaction_id, self.client.get("/transaction/").content.decode())
        self.client.post("/branch/switch/", {"store": "all"})
        self.assertIn(mine.transaction_id, self.client.get("/transaction/").content.decode())

    def test_warehouse_cannot_sell(self):
        self.login(self.owner)
        self.client.post("/branch/switch/", {"store": self.wh.pk})
        self.assertEqual(self.client.get("/register/").url, "/stock/")
        self.client.get("/cart/add/SH-1/1/")
        self.client.get("/endTransaction/cash/1000/")
        self.assertEqual(transaction.objects.count(), 0)

    def test_unassigned_user_is_logged_out(self):
        User.objects.create_user("drifter", password="pw")
        self.client.force_login(User.objects.get(username="drifter"))
        self.assertEqual(self.client.get("/register/").url, "/user/login/")


class TransferViewTests(BranchFixture):

    def setUp(self):
        stock.adjust(self.wh, self.shirt, 10, StockMovement.RECEIVE)

    def test_owner_transfers_from_warehouse(self):
        self.login(self.owner)
        resp = self.client.post("/stock/transfers/new/", {
            "source": self.wh.pk, "destination": self.gulberg.pk, "barcode": ["SH-1"], "qty": ["4"]})
        t = StockTransfer.objects.get()
        self.assertRedirects(resp, f"/stock/transfers/{t.pk}/")
        self.assertEqual(stock.branch_qty(self.gulberg, self.shirt), 4)
        self.assertEqual(stock.branch_qty(self.wh, self.shirt), 6)

    def test_manager_cannot_send_from_warehouse(self):
        self.login(self.manager)
        self.client.post("/stock/transfers/new/", {
            "source": self.wh.pk, "destination": self.gulberg.pk, "barcode": ["SH-1"], "qty": ["4"]})
        self.assertEqual(StockTransfer.objects.count(), 0)
        self.assertEqual(stock.branch_qty(self.wh, self.shirt), 10)

    def test_unknown_barcode_moves_nothing(self):
        self.login(self.owner)
        self.client.post("/stock/transfers/new/", {
            "source": self.wh.pk, "destination": self.gulberg.pk,
            "barcode": ["SH-1", "NOPE"], "qty": ["4", "1"]})
        self.assertEqual(StockTransfer.objects.count(), 0)
        self.assertEqual(stock.branch_qty(self.wh, self.shirt), 10)

    def test_stock_search_lists_source_stock(self):
        self.login(self.owner)
        data = self.client.get(f"/stock/api/search/?store={self.wh.pk}&available=1&limit=500").json()
        self.assertEqual(data["products"], [{"barcode": "SH-1", "name": "Shirt", "qty": 10, "department": "Clothing"}])
        data = self.client.get(f"/stock/api/search/?store={self.gulberg.pk}&available=1").json()
        self.assertEqual(data["products"], [])


class BootstrapMigrationTests(TransactionTestCase):
    """Old single-store data survives the move to branches."""

    before = [("inventory", "0001_initial"), ("transaction", "0002_transaction_discount"),
              ("cart", "0001_initial"), ("stores", None)]
    after = [("inventory", "0002_remove_product_qty"), ("transaction", "0004_sales_store_required"),
             ("stores", "0002_bootstrap_branches")]

    def test_stock_sales_and_users_are_carried_over(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old = executor.loader.project_state([t for t in self.before if t[1]]).apps

        Product = old.get_model("inventory", "product")
        dept = old.get_model("inventory", "department").objects.create(department_name="Clothing", department_slug="clothing")
        zt = old.get_model("inventory", "tax").objects.create(tax_category="Zero", tax_percentage=0)
        nd = old.get_model("inventory", "deposit").objects.create(deposit_category="None", deposit_value=0)
        for code, qty in [("A", 3), ("B", 0), ("C", 4)]:
            Product.objects.create(barcode=code, name=code, sales_price=10, qty=qty,
                                   department=dept, tax_category=zt, deposit_category=nd)
        OldUser = old.get_model("auth", "User")
        boss = OldUser.objects.create(username="boss", is_superuser=True, is_staff=True)
        OldUser.objects.create(username="cashier")
        sale = old.get_model("transaction", "transaction").objects.create(
            transaction_dt="2026-10-06T10:00:00Z", user=boss, transaction_id="T1", total_sale=10,
            sub_total=10, payment_type="CASH", receipt="r", products="[]")
        old.get_model("transaction", "productTransaction").objects.create(
            transaction=sale, transaction_id_num="T1", transaction_date_time="2026-10-06T10:00:00Z",
            barcode="A", name="A", sales_price=10, qty=1, tax_category="Zero", tax_percentage=0,
            deposit_category="None", deposit=0, payment_type="CASH")

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.after)
        new = executor.loader.project_state(self.after).apps

        NewStore = new.get_model("stores", "Store")
        main = NewStore.objects.get(is_warehouse=False)
        self.assertTrue(NewStore.objects.filter(is_warehouse=True).exists())
        stock_rows = new.get_model("stores", "BranchStock").objects.filter(store=main)
        self.assertEqual(sorted(stock_rows.values_list("product__barcode", "qty")), [("A", 3), ("C", 4)])
        self.assertEqual(new.get_model("stores", "StockMovement").objects.filter(kind="OPENING").count(), 2)
        self.assertEqual(new.get_model("transaction", "transaction").objects.get().store_id, main.pk)
        self.assertEqual(new.get_model("transaction", "productTransaction").objects.get().store_id, main.pk)
        roles = dict(new.get_model("stores", "StoreMembership").objects.values_list("user__username", "role"))
        self.assertEqual(roles, {"boss": "owner", "cashier": "cashier"})
