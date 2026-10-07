"""
Stock import from an .xlsx sheet (e.g. "RTW Stock 05102026.xlsx").

Parsed with the Python standard library only (zipfile + xml.etree) because
django-import-export cannot be installed on Vercel (odfpy ships no wheel and
build hosts are pip-locked). See the comment in inventory/admin.py.

Expected sheet layout (header row first):
    Sr. No. | Code | Barcode | Size | Quantity

Import contract (confirmed with the product owner):
  * one product row per unique Barcode (trimmed) — that is what the POS scans
  * product name   -> "Code — Size" (the sheet has no name column)
  * department     -> Clothing (created on first import)
  * tax/deposit    -> Zero Tax / No Deposit placeholder categories
  * prices         -> optional Sales Price / Cost Price columns; products
                      without them get 0.00 placeholders to set later
  * re-upload      -> quantities are ADDED to existing stock; sheet prices
                      overwrite product prices only where a value is present
  * invalid row    -> the WHOLE import is aborted (all-or-nothing)
"""
import re
import zipfile
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

from django.db import transaction as db_transaction

from .models import deposit, department, product, tax
from stores import stock
from stores.models import StockMovement, Store

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# Header names we accept (case/space insensitive -> canonical key).
HEADER_ALIASES = {
    "sr.no.": "sr",
    "sr.no": "sr",
    "code": "code",
    "barcode": "barcode",
    "size": "size",
    "quantity": "quantity",
    "qty": "quantity",
    "sales price": "sales_price",
    "sale price": "sales_price",
    "price": "sales_price",
    "cost price": "cost_price",
    "cost": "cost_price",
}


class ImportCancelled(Exception):
    """Raised when a row is invalid; aborts the entire import."""


def _parse_money(raw):
    """Parse an optional money cell. Empty means 'not provided'.

    Returns (Decimal, None) on success or (None, error_message).
    """
    raw = (raw or "").strip()
    if not raw:
        return None, None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None, f"'{raw}' is not a number"
    if value < 0:
        return None, f"must be 0 or more, got '{raw}'"
    return value, None


def parse_xlsx_rows(file_obj):
    """Return a list of dict rows from the first worksheet of an .xlsx file.

    Raises ImportCancelled if the file is not a readable xlsx or the
    mandatory columns are missing.
    """
    try:
        with zipfile.ZipFile(file_obj) as z:
            sheet_names = [n for n in z.namelist()
                           if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)]
            if not sheet_names:
                raise ImportCancelled("No worksheet found in the file.")
            # Lowest sheet number = first visible sheet.
            sheet_names.sort(key=lambda n: int(re.search(r"(\d+)", n).group(1)))
            sheet = ET.fromstring(z.read(sheet_names[0]))

            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                sroot = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in sroot.findall("m:si", NS):
                    shared.append("".join(
                        t.text or "" for t in si.iter("{%s}t" % NS["m"])
                    ))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ImportCancelled(
            "This does not look like a valid .xlsx file. Export the sheet "
            "from Excel as .xlsx and try again."
        )

    raw_rows = []
    for row in sheet.findall(".//m:row", NS):
        values = []
        for cell in row.findall("m:c", NS):
            cell_type = cell.get("t")
            if cell_type == "inlineStr":
                # Some writers (and our tests) embed text inline instead of
                # via the shared-strings table.
                values.append("".join(
                    t.text or "" for t in cell.iter("{%s}t" % NS["m"])
                ))
                continue
            v = cell.find("m:v", NS)
            if v is None:
                values.append("")
            elif cell_type == "s":
                values.append(shared[int(v.text)])
            else:
                values.append(v.text)
        raw_rows.append(values)

    if not raw_rows:
        raise ImportCancelled("The sheet is empty.")

    # Map the header row to canonical keys; require barcode + quantity.
    header = [str(c).strip().lower() for c in raw_rows[0]]
    keys = []
    for h in header:
        keys.append(HEADER_ALIASES.get(h, None))
    if "barcode" not in keys or "quantity" not in keys:
        raise ImportCancelled(
            "Header row must contain at least 'Barcode' and 'Quantity' "
            f"columns. Found: {header}"
        )

    rows = []
    for values in raw_rows[1:]:
        row = {}
        for i, key in enumerate(keys):
            if key and i < len(values):
                row[key] = (values[i] or "").strip()
        # Excel files often carry a stray empty row after the data (a touched
        # cell below the table). Those are not real rows: skip them instead of
        # aborting. Rows with SOME data but invalid values still abort later.
        if any(row.values()):
            rows.append(row)
    return rows


def import_stock(file_obj, store=None, user=None):
    """Validate + import the whole file atomically.

    Quantities are received into ``store`` (default: the warehouse) and each
    one is logged as a RECEIVE stock movement.
    Returns (created_count, updated_count) on success.
    Raises ImportCancelled with a user-facing message on any invalid row —
    nothing is written to the database in that case.
    """
    rows = parse_xlsx_rows(file_obj)

    # ---- validate everything BEFORE touching the database --------------
    cleaned = []
    errors = []
    for idx, row in enumerate(rows, start=2):  # Excel row 1 = header
        barcode = row.get("barcode", "")
        code = row.get("code", "")
        size = row.get("size", "")
        qty_raw = row.get("quantity", "")

        problems = []
        if not barcode:
            problems.append("missing Barcode")
        if not code:
            problems.append("missing Code")
        try:
            qty = int(Decimal(qty_raw))
            if qty <= 0:
                problems.append(f"Quantity must be positive, got '{qty_raw}'")
        except (InvalidOperation, ValueError):
            problems.append(f"Quantity '{qty_raw}' is not a number")

        sales_price, sales_err = _parse_money(row.get("sales_price", ""))
        if sales_err:
            problems.append(f"Sales Price {sales_err}")
        cost_price, cost_err = _parse_money(row.get("cost_price", ""))
        if cost_err:
            problems.append(f"Cost Price {cost_err}")

        if problems:
            label = barcode or code or f"row {idx}"
            errors.append(f"Excel row {idx} ({label}): " + "; ".join(problems))
            continue

        name = f"{code} — {size}" if size else code
        cleaned.append({
            "barcode": barcode,
            "name": name,
            "qty": qty,
            "sales_price": sales_price,
            "cost_price": cost_price,
        })

    if errors:
        raise ImportCancelled(
            "Import aborted — nothing was saved. Problems found: "
            + " | ".join(errors)
        )

    if not cleaned:
        raise ImportCancelled("Import aborted — the sheet has no data rows.")

    store = store or Store.warehouse() or Store.objects.filter(is_active=True).first()
    if store is None:
        raise ImportCancelled("Import aborted — create a branch or warehouse first.")

    # ---- write (single transaction) ------------------------------------
    with db_transaction.atomic():
        clothing = department.objects.get_or_create(
            department_name="Clothing",
            defaults={"department_desc": "Apparel and garments"},
        )[0]
        zero_tax = tax.objects.get_or_create(
            tax_category="Zero Tax",
            defaults={"tax_desc": "No sales tax applied",
                      "tax_percentage": Decimal("0.000")},
        )[0]
        no_deposit = deposit.objects.get_or_create(
            deposit_category="No Deposit",
            defaults={"deposit_desc": "No container deposit",
                      "deposit_value": Decimal("0.00")},
        )[0]

        created = updated = 0
        for item in cleaned:
            defaults = {
                "name": item["name"],
                "department": clothing,
                "tax_category": zero_tax,
                "deposit_category": no_deposit,
                "sales_price": (item["sales_price"]
                                if item["sales_price"] is not None
                                else Decimal("0.00")),
                "cost_price": (item["cost_price"]
                               if item["cost_price"] is not None
                               else Decimal("0.00")),
            }
            obj, was_created = product.objects.get_or_create(
                barcode=item["barcode"], defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                # Prices are only touched when the sheet provides them
                # (empty cell = leave as-is).
                updates = {}
                if item["sales_price"] is not None:
                    updates["sales_price"] = item["sales_price"]
                if item["cost_price"] is not None:
                    updates["cost_price"] = item["cost_price"]
                if updates:
                    product.objects.filter(pk=obj.pk).update(**updates)
                updated += 1
            # "Add stock": the sheet quantity is received into the branch.
            stock.adjust(store, obj, item["qty"], StockMovement.RECEIVE, user=user,
                         note="Excel stock upload")

    return created, updated
