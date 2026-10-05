"""Tests for the admin .xlsx stock upload (inventory/stock_import.py)."""
import io
import zipfile
from decimal import Decimal
from xml.sax.saxutils import escape

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import deposit, department, product, tax

STOCK_UPLOAD_URL_NAME = "admin:inventory_product_stock_upload"

SS_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

HEADER = ["Sr. No.", "Code", "Barcode", "Size", "Quantity",
          "Sales Price", "Cost Price"]


def make_xlsx(rows):
    """Build a minimal in-memory .xlsx with the given rows (header included)."""
    cells_xml = []
    for r_idx, row in enumerate([HEADER] + rows, start=1):
        row_cells = []
        for c_idx, value in enumerate(row, start=1):
            ref = f"{chr(64 + c_idx)}{r_idx}"
            row_cells.append(
                f'<c r="{ref}" t="inlineStr">'
                f'<is><t>{escape(str(value))}</t></is></c>'
            )
        cells_xml.append(f'<row r="{r_idx}">{"".join(row_cells)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{SS_NS}">'
        "<sheetData>" + "".join(cells_xml) + "</sheetData></worksheet>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0"?><Types xmlns='
                   '"http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/worksheets/sheet1.xml" ContentType='
                   '"application/vnd.openxmlformats-officedocument.spreadsheetml.'
                   'worksheet+xml"/></Types>')
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    buf.seek(0)
    buf.name = "stock.xlsx"
    return buf


def stock_file(rows):
    """Uploadable file object for the test client."""
    content = make_xlsx(rows)
    content.seek(0)
    return SimpleUploadedFile(
        "stock.xlsx", content.read(),
        content_type="application/vnd.openxmlformats-officedocument"
                     ".spreadsheetml.sheet",
    )


class StockImportTests(TestCase):
    """End-to-end tests through the admin upload view."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = get_user_model().objects.create_superuser(
            username="boss", email="boss@example.com", password="pw-12345"
        )

    def setUp(self):
        self.client.force_login(self.superuser)
        self.url = reverse(STOCK_UPLOAD_URL_NAME)

    def _rows(self):
        return [
            ["1", "ME1001", "ME1001-OOS", "Small", "3"],
            ["2", "ME1001", "ME1001-OOM", "Medium", "3"],
            ["3", "ME1002", "ME1002-OOS", "Small", "4"],
        ]

    def test_upload_creates_products_with_placeholders(self):
        resp = self.client.post(self.url, {"stock_file": stock_file(self._rows())})
        self.assertEqual(resp.status_code, 302)

        self.assertEqual(product.objects.count(), 3)
        p = product.objects.get(barcode="ME1001-OOS")
        self.assertEqual(p.name, "ME1001 — Small")
        self.assertEqual(p.qty, 3)
        self.assertEqual(p.department.department_name, "Clothing")
        self.assertEqual(p.tax_category.tax_percentage, Decimal("0.000"))
        self.assertEqual(p.deposit_category.deposit_value, Decimal("0.00"))
        self.assertEqual(p.sales_price, Decimal("0.00"))
        self.assertEqual(p.cost_price, Decimal("0.00"))
        # Placeholder support rows were auto-created exactly once.
        self.assertEqual(department.objects.count(), 1)
        self.assertEqual(tax.objects.count(), 1)
        self.assertEqual(deposit.objects.count(), 1)

    def test_prices_default_to_zero_when_columns_absent(self):
        self.client.post(self.url, {"stock_file": stock_file(self._rows())})
        p = product.objects.get(barcode="ME1001-OOS")
        self.assertEqual(p.sales_price, Decimal("0.00"))
        self.assertEqual(p.cost_price, Decimal("0.00"))

    def test_prices_imported_when_columns_present(self):
        rows = [
            ["1", "ME1001", "ME1001-OOS", "Small", "3", "1499.00", "900"],
            ["2", "ME1002", "ME1002-OOS", "Small", "4", "", ""],
        ]
        self.client.post(self.url, {"stock_file": stock_file(rows)})
        p = product.objects.get(barcode="ME1001-OOS")
        self.assertEqual(p.sales_price, Decimal("1499.00"))
        self.assertEqual(p.cost_price, Decimal("900.00"))
        # Empty price cells leave those products at the 0.00 placeholder.
        p2 = product.objects.get(barcode="ME1002-OOS")
        self.assertEqual(p2.sales_price, Decimal("0.00"))

    def test_reupload_with_prices_updates_prices_and_adds_qty(self):
        self.client.post(self.url, {"stock_file": stock_file(self._rows())})
        rows = [["1", "ME1001", "ME1001-OOS", "Small", "2", "1999.50", "1200"]]
        self.client.post(self.url, {"stock_file": stock_file(rows)})
        p = product.objects.get(barcode="ME1001-OOS")
        self.assertEqual(p.qty, 5)                      # 3 + 2
        self.assertEqual(p.sales_price, Decimal("1999.50"))
        self.assertEqual(p.cost_price, Decimal("1200.00"))
        # Re-upload without price columns keeps the new prices.
        rows2 = [["1", "ME1001", "ME1001-OOS", "Small", "1"]]
        self.client.post(self.url, {"stock_file": stock_file(rows2)})
        p = product.objects.get(barcode="ME1001-OOS")
        self.assertEqual(p.qty, 6)
        self.assertEqual(p.sales_price, Decimal("1999.50"))

    def test_non_numeric_price_aborts_everything(self):
        rows = [["1", "ME1001", "ME1001-OOS", "Small", "3", "expensive", ""]]
        resp = self.client.post(self.url, {"stock_file": stock_file(rows)})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(product.objects.count(), 0)
        self.client.post(self.url, {"stock_file": stock_file(self._rows())})
        self.client.post(self.url, {"stock_file": stock_file(self._rows())})

        self.assertEqual(product.objects.count(), 3)  # no duplicates
        self.assertEqual(product.objects.get(barcode="ME1001-OOS").qty, 6)
        self.assertEqual(product.objects.get(barcode="ME1002-OOS").qty, 8)

    def test_existing_product_other_fields_are_untouched(self):
        clothing = department.objects.create(
            department_name="Clothing", department_desc="d"
        )
        zero_tax = tax.objects.create(
            tax_category="Zero Tax", tax_percentage=Decimal("0.000")
        )
        no_dep = deposit.objects.create(
            deposit_category="No Deposit", deposit_value=Decimal("0.00")
        )
        product.objects.create(
            barcode="ME1001-OOS", name="Hand-named", department=clothing,
            sales_price=Decimal("1499.00"), cost_price=Decimal("900.00"),
            qty=5, tax_category=zero_tax, deposit_category=no_dep,
        )
        self.client.post(self.url, {"stock_file": stock_file(self._rows())})

        p = product.objects.get(barcode="ME1001-OOS")
        self.assertEqual(p.qty, 8)            # 5 + 3
        self.assertEqual(p.name, "Hand-named")
        self.assertEqual(p.sales_price, Decimal("1499.00"))

    def test_invalid_row_aborts_everything(self):
        rows = self._rows()
        rows.append(["4", "ME1003", "", "Large", "2"])       # missing barcode
        resp = self.client.post(self.url, {"stock_file": stock_file(rows)})

        self.assertEqual(resp.status_code, 200)  # form re-rendered with error
        self.assertEqual(product.objects.count(), 0)  # nothing was saved

    def test_non_numeric_quantity_aborts_everything(self):
        rows = self._rows()
        rows.append(["4", "ME1003", "ME1003-OOL", "Large", "abc"])
        resp = self.client.post(self.url, {"stock_file": stock_file(rows)})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(product.objects.count(), 0)

    def test_not_an_xlsx_file_is_rejected(self):
        resp = self.client.post(
            self.url,
            {"stock_file": SimpleUploadedFile(
                "stock.xlsx", b"this is not a zip file",
                content_type="application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(product.objects.count(), 0)

    def test_missing_header_columns_are_rejected(self):
        resp = self.client.post(self.url, {"stock_file": stock_file(
            [["A", "B"], ["1", "2"]]
        )})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(product.objects.count(), 0)

    def test_changelist_shows_upload_button(self):
        resp = self.client.get(reverse("admin:inventory_product_changelist"))
        self.assertContains(resp, "Upload stock (.xlsx)")

    def test_anonymous_and_non_staff_cannot_upload(self):
        User = get_user_model()
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)  # -> login

        User.objects.create_user(username="peon", password="pw-12345")
        self.client.force_login(User.objects.get(username="peon"))
        # Non-staff users are bounced to the admin login — never given access.
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"])

    def test_get_upload_page_renders(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Stock file")
