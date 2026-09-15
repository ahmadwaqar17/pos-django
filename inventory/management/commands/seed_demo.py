"""
Seed demo users, a Clothing department, zero-tax / no-deposit categories,
and ~15 clothing products.

Idempotent: safe to run repeatedly (get_or_create everywhere). Run with:

    python manage.py seed_demo            # everything
    python manage.py seed_demo --products # products only
    python manage.py seed_demo --users    # users only
"""
import random
from datetime import datetime, timedelta
from decimal import Decimal

import pytz

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from inventory.models import deposit, department, product, tax

USERS = [
    # username, password, email, is_superuser, is_staff
    ("admin", "admin123", "admin@example.com", True, True),
    ("staff", "common123", "staff@example.com", False, True),
    ("cashier", "cashier123", "cashier@example.com", False, False),
]

PRODUCTS = [
    # name, barcode, sales_price, cost_price, qty
    ("Classic White T-Shirt", "8801000000017", 1499.00, 900.00, 40),
    ("Black Graphic T-Shirt", "8801000000024", 1699.00, 1000.00, 35),
    ("Slim Fit Blue Jeans", "8801000000031", 3499.00, 2200.00, 25),
    ("Regular Fit Black Jeans", "8801000000048", 3299.00, 2100.00, 25),
    ("Cotton Casual Shirt", "8801000000055", 2799.00, 1700.00, 20),
    ("Formal White Dress Shirt", "8801000000062", 3199.00, 1950.00, 18),
    ("Hooded Sweatshirt", "8801000000079", 2999.00, 1850.00, 22),
    ("Zip-Up Hoodie", "8801000000086", 3299.00, 2000.00, 18),
    ("Summer Floral Dress", "8801000000093", 3899.00, 2400.00, 15),
    ("Embroidered Kurti", "8801000000109", 2599.00, 1550.00, 30),
    ("Men's Chino Pants", "8801000000116", 2899.00, 1750.00, 20),
    ("Women's Leggings", "8801000000123", 1799.00, 1050.00, 35),
    ("Polo Shirt (Navy)", "8801000000130", 1999.00, 1200.00, 28),
    ("Denim Jacket", "8801000000147", 4999.00, 3200.00, 12),
    ("Fleece Track Suit", "8801000000154", 4299.00, 2700.00, 14),
]


class Command(BaseCommand):
    help = "Seed demo users (admin/staff/cashier), Clothing department, and clothing products"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--users", action="store_true", help="Only seed users")
        group.add_argument("--products", action="store_true", help="Only seed products")
        group.add_argument("--sales", action="store_true", help="Only seed sample sales history (12 past days)")

    def handle(self, *args, **options):
        seed_users = not (options["products"] or options["sales"])
        seed_products = not (options["users"] or options["sales"])

        if seed_users:
            self._seed_users()
        if seed_products:
            self._seed_products()
        if options["sales"]:
            self._seed_sales()

    def _seed_users(self):
        User = get_user_model()
        for username, password, email, is_superuser, is_staff in USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": email, "is_superuser": is_superuser, "is_staff": is_staff},
            )
            # Always (re)set the password so the documented credentials work.
            user.set_password(password)
            user.is_superuser = is_superuser
            user.is_staff = is_staff
            user.save()
            self.stdout.write(f"  user '{username}' {'created' if created else 'updated'}")

    def _seed_products(self):
        clothing, _ = department.objects.get_or_create(
            department_name="Clothing",
            defaults={"department_desc": "Apparel and garments"},
        )

        zero_tax, _ = tax.objects.get_or_create(
            tax_category="Zero Tax",
            defaults={"tax_desc": "No sales tax applied", "tax_percentage": Decimal("0.000")},
        )

        no_deposit, _ = deposit.objects.get_or_create(
            deposit_category="No Deposit",
            defaults={"deposit_desc": "No container deposit", "deposit_value": Decimal("0.00")},
        )

        created_count = 0
        for name, barcode, sales_price, cost_price, qty in PRODUCTS:
            _, created = product.objects.get_or_create(
                barcode=barcode,
                defaults={
                    "name": name,
                    "department": clothing,
                    "sales_price": Decimal(str(sales_price)),
                    "cost_price": Decimal(str(cost_price)),
                    "qty": qty,
                    "tax_category": zero_tax,
                    "deposit_category": no_deposit,
                    "product_desc": f"{name} — Clothing department demo item",
                },
            )
            created_count += 1 if created else 0

        self.stdout.write(
            f"  products: {created_count} created, "
            f"{len(PRODUCTS) - created_count} already existed"
        )

    def _seed_sales(self):
        """Create ~40 realistic past transactions (12 days) so the sales and
        department dashboards, transactions list, and receipts have data.
        Skips everything if the transaction table already has rows."""
        from transaction.models import transaction

        if transaction.objects.exists():
            self.stdout.write("  sales: transactions already exist, skipping")
            return

        User = get_user_model()
        staff_user = User.objects.filter(username="staff").first() or User.objects.filter(is_superuser=True).first()
        products = list(product.objects.all())
        if not products:
            self.stdout.write("  sales: no products found, run --products first")
            return

        payment_types = ["CASH", "CASH", "DEBIT/CREDIT", "DEBIT/CREDIT", "EBT"]
        today = datetime.now().date()
        created = 0
        for days_ago in range(1, 13):
            for _ in range(random.randint(2, 5)):
                # 1-4 random line items per sale
                chosen = random.sample(products, k=random.randint(1, 4))
                cart = {}
                for p in chosen:
                    qty = random.randint(1, 3)
                    tax_v = float(p.sales_price) * qty * (float(p.tax_category.tax_percentage) / 100)
                    dep_v = float(p.deposit_category.deposit_value) * qty
                    cart[p.barcode] = {
                        "barcode": p.barcode,
                        "name": p.name,
                        "price": str(p.sales_price),
                        "quantity": qty,
                        "tax_value": f"{tax_v:.2f}",
                        "deposit_value": f"{dep_v:.2f}",
                        "line_total": f"{float(p.sales_price) * qty + tax_v + dep_v:.2f}",
                    }
                total = round(sum(float(v["line_total"]) for v in cart.values()), 2)
                payment = random.choice(payment_types)
                pay_value = total if payment != "CASH" else random.choice([1000, 2000, 5000, total])
                pay_value = max(pay_value, total)

                stamp = datetime(today.year, today.month, today.day) - timedelta(
                    days=days_ago, hours=random.randint(9, 20), minutes=random.randint(0, 59),
                )
                # Naive on purpose: transaction.save() localizes to US/Eastern
                # itself (same contract as addTransaction).
                transaction_id = stamp.strftime('%Y%m%d%H%M%S') + f"{random.randint(0, 999999):06d}"
                receipt = (
                    f"{'='*32}\n{settings.STORE_NAME.center(32)}\n"
                    f"{settings.STORE_ADDRESS.center(32)}\n{'='*32}\n"
                    f"{stamp.strftime('%d %b %Y  %I:%M %p').center(32)}\n"
                    f"{('Receipt #' + transaction_id[:14]).center(24)}\n{'-'*32}\n"
                )
                for barcode, v in cart.items():
                    receipt += f" {v['name'][:20]:<20} x{v['quantity']:<3} PKR {v['price']}\n"
                receipt += (
                    f"{'-'*32}\n {'TOTAL:':<15}PKR {total:>8.2f}\n"
                    f" {payment:<15}PKR {pay_value:>8.2f}\n{'='*32}\nThank You".center(32) + f"\n{'='*32}"
                )

                txn = transaction.objects.create(
                    transaction_id=transaction_id,
                    transaction_dt=stamp,
                    user=staff_user,
                    total_sale=Decimal(str(total)),
                    sub_total=Decimal(str(round(total - 0, 2))),
                    tax_total=Decimal("0.00"),
                    deposit_total=Decimal("0.00"),
                    payment_type=payment,
                    receipt=receipt,
                    products=str([dict(v, barcode=v["barcode"]) for v in cart.values()]),
                )
                # transaction.save() auto-creates productTransaction rows and
                # decrements product stock.
                created += 1
        self.stdout.write(f"  sales: {created} transactions created over the last 12 days")
