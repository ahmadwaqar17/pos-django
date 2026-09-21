import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.shortcuts import redirect, render

from .models import Store, StoreMembership


def _slugify(value):
    value = re.sub(r"[^\w\s-]", "", value.lower()).strip()
    return re.sub(r"[-\s]+", "-", value) or "store"


class SignupForm(forms.Form):
    store_name = forms.CharField(max_length=100, label="Store name")
    username = forms.CharField(max_length=150, label="Username")
    email = forms.EmailField(required=False, label="Email (optional)")
    password1 = forms.CharField(widget=forms.PasswordInput, label="Password")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "Passwords do not match.")
        if cleaned.get("password1"):
            validate_password(cleaned["password1"])
        return cleaned


def signup(request):
    """Self-serve onboarding: Store + owner account + seeded defaults, atomically."""
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            User = get_user_model()
            store_name = form.cleaned_data["store_name"].strip()
            username = form.cleaned_data["username"].strip()
            base_slug = _slugify(store_name)
            slug = base_slug
            n = 2
            while Store.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{n}"
                n += 1

            if get_user_model().objects.filter(username=username).exists():
                form.add_error("username", "That username is already taken.")
                return render(request, "stores/signup.html", {"form": form})

            user = User.objects.create_user(
                username=username,
                email=form.cleaned_data.get("email") or "",
                password=form.cleaned_data["password1"],
            )

            store = Store.objects.create(
                name=store_name,
                slug=slug,
                store_name=store_name,
                receipt_footer="Thank You",
            )
            StoreMembership.objects.create(store=store, user=user, role=StoreMembership.ROLE_OWNER)

            # Seed defaults so the register is usable immediately.
            from inventory.models import deposit, department, tax

            deposit.objects.create(store=store, deposit_category="No Deposit", deposit_value=0)
            tax.objects.create(store=store, tax_category="Zero Tax", tax_percentage=0)
            department.objects.create(store=store, department_name="General")

            from django.contrib.auth import login

            login(request, user)
            return redirect("home")
    else:
        form = SignupForm()
    return render(request, "stores/signup.html", {"form": form})


# ======================================================================
# Platform (super admin) area
# ======================================================================
from django.contrib.auth import login as auth_login
from django.db import transaction as db_transaction
from django.db.models import Count, Q

from .platform import super_admin_required
from inventory.models import deposit, department, tax
from transaction.models import transaction


class AddStoreForm(forms.Form):
    store_name = forms.CharField(max_length=100, label="Store name")
    store_address = forms.CharField(max_length=255, required=False, label="Address")
    store_phone = forms.CharField(max_length=32, required=False, label="Phone")
    currency = forms.CharField(max_length=8, initial="PKR")
    timezone = forms.CharField(max_length=64, initial="US/Eastern")
    plan = forms.ChoiceField(choices=[("trial", "Trial"), ("standard", "Standard"), ("bootstrap", "Bootstrap")],
                             initial="trial")


class AssignUserForm(forms.Form):
    username = forms.CharField(max_length=150, label="Username")
    email = forms.EmailField(label="Email")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
    role = forms.ChoiceField(choices=[("owner", "Owner"), ("cashier", "Cashier")])


@super_admin_required
def platform_dashboard(request):
    stores_qs = Store.objects.annotate(
        user_count=Count("memberships", distinct=True),
    ).order_by("-created_at")

    stores = []
    for s in stores_qs:
        txn_count = transaction.all_objects.filter(store=s).count()
        stores.append({
            "store": s,
            "user_count": s.user_count,
            "txn_count": txn_count,
            "memberships": s.memberships.select_related("user").order_by("role"),
        })

    context = {
        "stores": stores,
        "total_stores": Store.objects.count(),
        "active_stores": Store.objects.filter(is_active=True).count(),
        "total_users": StoreMembership.objects.exclude(role=StoreMembership.ROLE_SUPER_ADMIN).count(),
        "add_store_form": AddStoreForm(),
    }
    return render(request, "stores/platform_dashboard.html", context)


@super_admin_required
@db_transaction.atomic
def platform_add_store(request):
    """Create a store + its first owner (email + password entered here)."""
    if request.method != "POST":
        return redirect("platform_dashboard")

    form = AddStoreForm(request.POST)
    if not form.is_valid():
        return redirect("platform_dashboard")

    data = form.cleaned_data
    base_slug = _slugify(data["store_name"])
    slug, n = base_slug, 2
    while Store.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{n}"
        n += 1

    store = Store.objects.create(
        name=data["store_name"], slug=slug,
        store_name=data["store_name"], store_address=data["store_address"] or "",
        store_phone=data["store_phone"] or "", currency=data["currency"],
        timezone=data["timezone"], plan=data["plan"],
    )

    # Seed defaults so the register is usable immediately.
    deposit.objects.create(store=store, deposit_category="No Deposit", deposit_value=0)
    tax.objects.create(store=store, tax_category="Zero Tax", tax_percentage=0)
    department.objects.create(store=store, department_name="General")

    return redirect("platform_store_users", store_id=store.id)


@super_admin_required
def platform_store_users(request, store_id):
    """Manage a store's users: list + assign existing/new users with credentials."""
    store = Store.objects.get(pk=store_id)
    error = None

    if request.method == "POST":
        form = AssignUserForm(request.POST)
        if form.is_valid():
            User = get_user_model()
            data = form.cleaned_data
            user = User.objects.filter(Q(username=data["username"]) | Q(email=data["email"])).first()
            if user:
                # Existing user: reassign or update credentials to this store.
                existing = getattr(user, "store_membership", None)
                if existing and existing.store_id != store.id:
                    error = "That user already belongs to another store."
                else:
                    if existing:
                        existing.role = data["role"]
                        existing.store = store
                        existing.save()
                    else:
                        StoreMembership.objects.create(store=store, user=user, role=data["role"])
                    if data["password"]:
                        user.set_password(data["password"])
                        user.save()
                    return redirect("platform_store_users", store_id=store.id)
            else:
                user = User.objects.create_user(
                    username=data["username"], email=data["email"], password=data["password"],
                )
                StoreMembership.objects.create(store=store, user=user, role=data["role"])
                return redirect("platform_store_users", store_id=store.id)
        else:
            error = form.errors.as_text()

    memberships = store.memberships.select_related("user").order_by("role")
    return render(request, "stores/platform_store_users.html", {
        "store": store, "memberships": memberships, "error": error,
        "form": AssignUserForm(),
    })


@super_admin_required
def platform_toggle_store(request, store_id):
    store = Store.objects.get(pk=store_id)
    if request.method == "POST":
        store.is_active = not store.is_active
        store.save()
    return redirect("platform_dashboard")


@super_admin_required
def platform_remove_user(request, store_id, membership_id):
    if request.method == "POST":
        StoreMembership.objects.filter(pk=membership_id, store_id=store_id).delete()
    return redirect("platform_store_users", store_id=store_id)
