# SaaS Conversion Plan — OnlineRetailPOS

> **Goal:** turn the single-store Django POS into a multi-tenant SaaS **without database or schema
> segregation** — one shared database, one set of tables, every row tagged with a tenant ID.
> **Constraint:** minimal changes. Business logic, templates, and the register flow stay untouched.

---

## 1. Tenancy Model (the core decision)

**Shared database, shared schema, tenant scoping via row ownership** — the standard
"single-database" approach and the smallest change to your existing code.

| Layer | Mechanism |
|---|---|
| **Tenant** | New `Store` model — one row per customer (each customer = one store) |
| **Row ownership** | Every business model gets a `store` FK; all queries filter by it |
| **Enforcement** | One custom `ModelManager` + one middleware — query filtering is automatic |
| **Request scoping** | Middleware reads the logged-in user's store → sets `request.store` |

Why not the alternatives (so you can review with full context):

- **Separate database per tenant** — clean isolation but N databases to migrate, back up, and
  monitor; violates your "no database segregation" constraint.
- **Separate schema per tenant (Postgres `search_path`, django-tenants)** — heavy migration of the
  whole project onto the `django-tenants` pattern; invasive, not minimal.
- **Row-level security in Postgres** — needs Postgres-specific wiring and connection-variable
  plumbing; overkill for the minimal path (can be added later as defense-in-depth).

---

## 2. What Changes (file-by-file)

### 2.1 New app: `stores/` (~6 small files)

| File | Contents |
|---|---|
| `stores/models.py` | **`Store`** model (see §3.1), plus a `StoreMembership` through-model (optional, §3.3) |
| `stores/managers.py` | **`StoreScopedManager`** — auto-filters by the current store (§4) |
| `stores/middleware.py` | **`StoreMiddleware`** — resolves `request.store` from the session/user |
| `stores/views.py` | Signup (creates Store + admin user + seed data), store settings page |
| `stores/urls.py` | `/signup/`, `/store/settings/` |
| `stores/apps.py` | Ready() hook optional; keep light |

New settings: `PUBLIC_TENANT_SLUG` or subdomain resolution config (§5).

### 2.2 New migration touching existing models (additive only)

A single migration adds `store = FK(Store)` to 6 models + a scoped default manager:

| Model | Change |
|---|---|
| `inventory.product` | `+ store FK` |
| `inventory.department` | `+ store FK` |
| `inventory.tax` | `+ store FK` |
| `inventory.deposit` | `+ store FK` |
| `cart.displayed_items` | `+ store FK` |
| `transaction.productTransaction` | `+ store FK` (denormalized copy of transaction lines — needs the tag for reports) |
| `transaction.transaction` | `+ store FK` |

**Uniqueness loosening (required):** `product.barcode`, `department.department_name`,
`department.department_slug`, `tax.tax_category`, `deposit.deposit_category`,
`displayed_items.barcode` are currently `unique=True` **globally**. In SaaS they must become
**unique per store** — i.e. `UniqueTogetherConstraint (("store","barcode"))` instead of bare
`unique=True`. Otherwise store B cannot have the same product barcode as store A.

**Data migration:** all existing rows get `store = <the one bootstrap store>` so nothing breaks.

### 2.3 Small edits in existing code (~10 places, few lines each)

| File | Edit |
|---|---|
| `onlineretailpos/views.py` | Replace `settings.STORE_NAME` / `STORE_ADDRESS` / receipt settings with `request.store.*` (5–6 spots: retail_display, report_regular, login) |
| `transaction/views.py` | Same for receipt head/footer + store name (2–3 spots) |
| `transaction/models.py` | `transaction.save()` uses timezone, products, payment fields — pass `store` in from the view (1-line change at call site) |
| `inventory/views.py` | Reads `STORE_NAME` context — swap to `request.store` |
| `cart/models.py` | `Cart` is session-based → no change needed; `displayed_items.save()` guard unchanged |
| `onlineretailpos/admin.py` | All `ModelAdmin`s inherit `StoreScopedAdmin` (auto-filters dropdowns & lists) |
| `onlineretailpos/settings/*.py` | Add `STORES_APP` config; optionally move receipt/printer settings to per-store columns |
| `onlineretailpos/urls.py` | `include('stores.urls')` |

**Not touched:** `Cart` (session-scoped, already isolated per user session), templates, `theme.js`,
URL structure, register flow, plotly dashboards logic (they read from scoped models already).

---

## 3. New `Store` Model (draft fields)

```python
class Store(models.Model):
    # Identity
    name          = models.CharField(max_length=100)          # "Ahmad's Corner Shop"
    slug          = models.SlugField(unique=True)             # "ahmads-corner" → subdomain
    # Branding / receipt (moves out of env-vars)
    store_name    = models.CharField(max_length=64)
    store_address = models.TextField(blank=True)
    store_phone   = models.CharField(max_length=32, blank=True)
    receipt_footer = models.CharField(max_length=120, blank=True)
    currency      = models.CharField(max_length=8, default="PKR")
    timezone      = models.CharField(max_length=64, default="US/Eastern")
    # Control
    is_active     = models.BooleanField(default=True)         # suspend accounts
    plan          = models.CharField(max_length=32, default="trial")
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.name
```

### 3.1 User ↔ Store link

Simplest: **`Store.owner` → `User`** (FK, one owner per store; the common SaaS shape for a POS
where 1 storefront = 1 account). Middleware: `request.store = Store.objects.get(owner=request.user)`.

If you want multiple users per store (cashiers + manager sharing one store), add:

```python
class StoreMembership(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    user  = models.ForeignKey(User, on_delete=models.CASCADE)
    role  = models.CharField(max_length=16, default="cashier")  # owner / cashier
```

and resolve via `StoreMembership.objects.filter(user=request.user).first().store` instead.
(§9 notes the trade-off; recommend including `StoreMembership` from day one — it's 15 lines and
avoids a second migration later if you ever add cashier accounts.)

**Recommendation:** include `StoreMembership` now. One user can belong to only one store (enforced
in middleware resolution, first-match), keeping "minimal changes" intact.

### 3.2 Who creates stores?

- **Self-serve signup** (`/signup/`): store name → slug → owner account → seed defaults
  (default tax, deposit, department rows so the register isn't empty). After signup, user is
  logged in and redirected to the register.
- **Your own staff (admin)** can also create stores manually via Django admin for offline
  onboarding.

### 3.3 Middleware contract

```
request.store          — the Store row for the current user (None on public pages)
request.store_scoped   — True on every tenant-scoped view
```

Public paths (login, signup, static, admin login) skip scoping. Any view that runs while
`request.store is None` and the path is not public → redirect to login (defensive).

---

## 4. How Scoping Actually Works (the 2 key pieces)

### 4.1 `StoreScopedManager` (models) — *reads, automatic*

```python
class StoreScopedManager(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        store = getattr(_thread_locals, "store", None)  # set by middleware per request
        if store is not None:
            qs = qs.filter(store=store)
        return qs
```

Every `product.objects.all()` / `productTransaction.objects.filter(...)` in your existing views
**automatically becomes store-filtered** — no view edits needed for reads. That's the entire point
of this design: **reads get isolation for free.**

- `_thread_locals` is a `threading.local()` set once per request by middleware — the standard
  Django pattern (used by django-tenants, django-multitenant, etc.).
- **Admin and shell:** `Store.objects.scope(None)` (bypass) is available for scripts/shell where
  there is no request. Admin UI uses the same manager with the admin user's store.
- **Celery/tasks:** set the thread-local explicitly at task start (pattern documented in the app).

### 4.2 Middleware — *request scoping + writes*

```python
class StoreMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        request.store = None
        if request.user.is_authenticated:
            m = StoreMembership.objects.select_related("store").filter(user=request.user).first()
            request.store = m.store if m and m.store.is_active else None
        _thread_locals.store = request.store
        return self.get_response(request)
```

For **writes**, each create path passes `store=request.store` explicitly (audit-friendly; avoids
magic on writes):

- `cart/views.py` → `Product.objects.create(..., store=request.store)` — the fallback-by-name
  search in `cart_add` is now automatically store-scoped by the manager.
- `transaction.save()` call sites pass `store=request.store`.
- Admin: `save_model(self, obj, ..., change)` sets `obj.store = request.store` on create if unset.

---

## 5. Tenant Identification

| Option | How | Fit |
|---|---|---|
| **A. Subdomain** | `ahmads.pos-django.com` — DNS wildcard `*.pos-django.com` → app | Wildcard TLS, needs DNS+cert plumbing at deploy |
| **B. Path prefix** | `/ahmads/register/` — no DNS work, works on any host | Small middleware tweak; URLs change shape slightly |
| **C. Session-only (no URL signal)** | Tenant = the logged-in user's store | **Smallest change; URL shape untouched; tenant is implicit from login.** |

**Recommendation: start with C (session-only).** The user logs in → their store is loaded. No DNS,
no wildcard certs, no URL rewrite. All store data is scoped by who is logged in. Subdomains (A) can
be layered later without touching business logic — the middleware is the single point that resolves
the tenant, so switching to subdomain resolution later is a one-file change.

---

## 6. Rollout Phases

### Phase 0 — Prep (no functional change)
- [ ] Move `STORE_NAME`/receipt/printer env-var reads into a helper so the swap to `request.store` is one-line-per-site
- [ ] Add `db.sqlite3`, `venv/` to `.gitignore` (already tracked today — should not be in git)
- housekeeping commit

### Phase 1 — Multi-tenancy core
- [ ] `stores` app: `Store`, `StoreMembership`, manager, middleware
- [ ] Add `store` FK to 6 models + per-store unique constraints + data migration
- [ ] Edit ~10 view/admin spots per §2.3
- [ ] Tests: tenant isolation (`storeA cannot read storeB`), uniqueness-per-store, middleware contract

### Phase 2 — Onboarding & admin
- [ ] `/signup/` flow (creates store + owner + seeds defaults)
- [ ] `/store/settings/` page (branding, receipt footer, currency/timezone)
- [ ] Django admin: `StoreScopedAdmin` base; store switcher for superusers

### Phase 3 — (later, optional) Billing & limits
- [ ] Stripe webhook → flip `Store.plan`, `is_active`
- [ ] Per-store usage caps (e.g. max products) enforced in views
- Suggested but **out of scope for the minimal conversion**.

### Phase 4 — (later, optional) Public subdomains
- `stores/middleware.py` accepts subdomain when `STORE_RESOLVER=subdomain` setting is flipped —
  middleware is the only file that changes.

---

## 7. What Deliberately Does NOT Change

- **Templates** — all 15 .html files untouched
- **Cart** — session-based, already user-isolated; no model changes
- **Register flow, URLs, plotly dashboards** — they read from scoped models; zero edits
- **theme.js / theme.css / click sound** — client-side, irrelevant to tenancy
- **No `django-tenants`, no schema separation, no separate DBs**

---

## 8. Risks & Review Points

| Risk | Mitigation in this plan |
|---|---|
| Missed unscoped query leaks cross-tenant data | Manager covers every `.objects` call; add a test that visits every route with 2 stores and asserts isolation (Phase 1 test list) |
| `eval(self.products)` in `transaction.save()` — arbitrary code execution | Pre-existing (not a tenancy issue). Note: `eval` on a DB column is a real injection surface; recommend `json.loads` swap while you're in that file (2 lines) |
| `Cart` data leaking across users on shared terminals | Already session-based; keep `SESSION_COOKIE_SECURE` in prod |
| Data migration must backfill `store` on existing rows | Phase 1 includes the data migration (single bootstrap store) |
| Branch protection: main vs feat branch | Do the work on `feat/saas` branched off `main` (recommended; today's work lives on `feat/ui-modernization`) |
| Subdomain flow (Phase 4 later) | Middleware-only change later; no rework |
| `transaction` `transaction_id` must be unique per store, not globally | Add to per-store uniqueness list in §2.2 |
| Timezone: `pytz.timezone("US/Eastern")` hardcoded | Per-store `timezone` column; `transaction.save()` and reports read `request.store.timezone` |
| Currency: hardcoded `'PKR'` in retail_display JSON | Per-store `currency` column; same swap |

---

# 9. Deliberately Out of Scope

- **Billing/Stripe** — Phase 3 optional; not needed to be "SaaS"
- **Per-tenant rate limiting / usage metering** — Phase 3
- **Subdomain routing** — Phase 4 (middleware swap, later)
- **Per-tenant email domains / custom domains** — not needed
- **`django-tenants` / schema separation** — explicitly rejected per your constraint
- **Multi-store per user (a user in 2 stores)** — possible with memberships but not exercised in v1

---

## 10. Rough Size

| Item | Estimate |
|---|---|
| New `stores/` app | ~300 lines (models, manager, middleware, signup, urls) |
| Migration | 1 schema migration (7 models) + 1 data migration |
| View/admin edits | ~10 files, few lines each |
| Templates | 0 |
| Tests | ~15 (isolation, uniqueness, middleware, signup) |
| Elapsed effort | **~2–4 working days** for the minimal path |

---

*Prepared for review — no code has been written. Branched work should go on `feat/saas` off `main`.
Happy to adjust scope: drop `StoreMembership` for a simpler `Store.owner` FK, defer Phase 2
settings page, or fold any optional phase out entirely.*
