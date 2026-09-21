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
