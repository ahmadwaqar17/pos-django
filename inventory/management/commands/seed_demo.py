"""
Seed demo users, a Clothing department, zero-tax / no-deposit categories,
and ~15 clothing products.

Idempotent: safe to run repeatedly (get_or_create everywhere). Run with:

    python manage.py seed_demo            # everything
    python manage.py seed_demo --products # products only
    python manage.py seed_demo --users    # users only
"""
from decimal import Decimal

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

    def handle(self, *args, **options):
        seed_users = not options["products"]
        seed_products = not options["users"]

        if seed_users:
            self._seed_users()
        if seed_products:
            self._seed_products()

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
