# Online Retail POS — System Documentation

A web-based Point-of-Sale system built with Django. Manages inventory, sales transactions, receipts, and analytics dashboards.

**Live URLs:**
- Local: http://127.0.0.1:8000
- ngrok: https://5352-39-45-62-85.ngrok-free.app

**Currency:** PKR (Pakistani Rupees)

---

## 1. User Roles & Functionality

### 3 User Roles

| Role | How Created | Access Level |
|---|---|---|
| **Superuser** (`admin`) | `manage.py createsuperuser` | Full control |
| **Staff** (`staff`) | Via admin → `is_staff=True` | Admin portal + POS |
| **Cashier** (`cashier`) | Via admin → `is_staff=False` | POS only |

### What Each Role Can Do

| Functionality | Superuser | Staff | Cashier |
|---|---|---|---|
| POS Register (scan items, cart) | ✅ | ✅ | ✅ |
| Payments (Cash / Debit / Credit / EBT) | ✅ | ✅ | ✅ |
| Returns (`(-) Returns` button) | ✅ | ✅ | ✅ |
| Suspend / Recall transactions | ✅ | ✅ | ✅ |
| Clear cart | ✅ | ✅ | ✅ |
| View / Print receipts | ✅ | ✅ | ✅ |
| Add stock (`/inventory/`) | ✅ | ✅ | ✅ |
| Product price lookup | ✅ | ✅ | ✅ |
| Dashboards & reports | ✅ | ✅ | ✅ |
| Admin Portal (`/staff_portal/`) | ✅ | ✅ | ❌ |
| Create/edit products, departments, tax, deposits | ✅ | ✅ | ❌ |
| Import/Export product data | ✅ | ✅ | ❌ |
| Manage users | ✅ | ❌ | ❌ |
| View transactions in admin (read-only) | ✅ | ✅ | ❌ |

---

## 2. Database Models & Field Meanings

### 📦 `product` (inventory app) — `inventory/models.py:8`

Stores each sellable item in the store.

| Field | Type | Meaning |
|---|---|---|
| `department` | FK → `department` | Which department/category this product belongs to |
| `barcode` | CharField (unique) | Unique barcode scanned at register |
| `name` | CharField | Product name |
| `sales_price` | Decimal | Selling price in PKR |
| `qty` | Integer | Current stock on hand |
| `cost_price` | Decimal | What you paid for it (for profit calculations) |
| `tax_category` | FK → `tax` | Which tax rate applies to this product |
| `deposit_category` | FK → `deposit` | Which bottle deposit/crate deposit applies |
| `product_desc` | Text | Short description |

---

### 🗂️ `department` — `inventory/models.py:47`

Groups products into categories (e.g., Grocery, Dairy, Beverages).

| Field | Type | Meaning |
|---|---|---|
| `department_name` | CharField (unique) | Dept name, e.g., "Beverages" |
| `department_desc` | Text | Optional description |
| `department_slug` | SlugField | Auto-generated URL-friendly name (e.g., `beverages`) |

---

### 💰 `tax` — `inventory/models.py:60`

Defines tax categories. **Example use in Pakistan: GST (Sales Tax) = 17%.**

| Field | Type | Meaning |
|---|---|---|
| `tax_category` | CharField (unique) | Tax name, e.g., "GST-17%" |
| `tax_desc` | Text | Description |
| `tax_percentage` | Decimal (0–100) | Tax rate in %, e.g., 17.000 |

---

### 🍾 `deposit` — `inventory/models.py:72`

Bottle/crate deposit returned when the customer brings back the container.

| Field | Type | Meaning |
|---|---|---|
| `deposit_category` | CharField (unique) | Deposit name, e.g., "Glass Bottle Deposit" |
| `deposit_desc` | Text | Description |
| `deposit_value` | Decimal | Amount charged per unit, e.g., 50.00 PKR |

---

### 🖥️ `displayed_items` (cart app) — `cart/models.py:91`

The **one-touch sell buttons** shown on the register screen.

| Field | Type | Meaning |
|---|---|---|
| `barcode` | CharField (unique) | Must match an existing product's barcode |
| `display_name` | CharField | Label on the button, e.g., "Coke" |
| `display_info` | CharField | Extra info shown (for variable-price items) |
| `display_color` | ColorField | Button background color |
| `variable_price` | Boolean | If ✅ — prompts cashier to type any custom amount (e.g., loose produce) |

---

### 🧾 `transaction` (transaction app) — `transaction/models.py:11`

One row per completed sale (header record).

| Field | Type | Meaning |
|---|---|---|
| `date_time` | DateTime (auto) | When the record was created |
| `transaction_dt` | DateTime | Transaction date/time (US/Eastern localized) |
| `user` | FK → User | **Which staff member completed the sale** |
| `transaction_id` | CharField (unique) | Unique ID: `YYYYMMDDHHMMSSffffff` |
| `total_sale` | Decimal | Grand total charged |
| `sub_total` | Decimal | Total before tax/deposit |
| `tax_total` | Decimal | Total tax collected |
| `deposit_total` | Decimal | Total deposit collected |
| `payment_type` | CharField | `CASH`, `DEBIT/CREDIT`, or `EBT` |
| `receipt` | Text | Full printable receipt text |
| `products` | Text | Serialized list of every item in the sale |

---

### 📄 `productTransaction` — `transaction/models.py:44`

One row per line item in a sale (like an invoice line).

| Field | Type | Meaning |
|---|---|---|
| `transaction` | FK → transaction | Parent sale |
| `transaction_id_num` | CharField | Same as transaction ID |
| `transaction_date_time` | DateTime | When the item was sold |
| `barcode` | CharField | Item barcode |
| `name` | CharField | Item name |
| `department` | CharField | Dept name at time of sale |
| `sales_price` | Decimal | Price charged |
| `qty` | Integer | Quantity sold (**negative = return**) |
| `cost_price` | Decimal | Cost price at time of sale |
| `tax_category` | CharField | Tax name used |
| `tax_percentage` | Decimal | Tax rate used |
| `tax_amount` | Decimal | Tax amount on this line |
| `deposit_category` | CharField | Deposit name used |
| `deposit` | Decimal | Deposit rate per unit |
| `deposit_amount` | Decimal | Total deposit on this line |
| `payment_type` | CharField | How this item was paid for |

---

### 💳 `Cart` (cart app) — `cart/models.py:11`

**Not a database table** — it's a Python helper class storing the cart in the **browser session** (per-logged-in user).

| Attribute | Meaning |
|---|---|
| `add(product, qty)` | Add item / increase qty in session |
| `remove(product)` | Delete item from cart |
| `decrement(product)` | Lower qty by 1 |
| `clear()` | Empty the cart |
| `returns()` | Multiply all qtys by -1 (returns) |
| `cartTotal()` | Grand total of line totals |

---

## 3. Entity Relationships

```
User ──< transaction ──< productTransaction
department ──< product >── tax
                       └──> deposit
```

**Tax example:** Create tax "GST 17%" → assign it to a product → when sold, the register auto-adds 17% PKR to the line total.

**Deposit example:** "Glass Bottle 50 PKR" → charging a deposit that's refunded when bottles are returned.

---

## 4. Key Features

- **Barcode scanning** at the register for fast checkout
- **Multiple payment types:** Cash, Debit/Credit, EBT
- **Returns processing** (negates cart & restores stock)
- **Suspend/Recall** transactions (hold a sale and resume later)
- **Customer display** (`/retail_display/`) — shows live cart on a second screen
- **ESCPOS thermal printer** support with USB
- **Analytics dashboards:** today's sales, 30-day chart, department reports, top sellers, low inventory
- **Import/Export** product data via Django admin
- **Read-only audit trail** — transactions cannot be edited/deleted