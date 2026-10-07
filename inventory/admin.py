from django import forms
from django.conf import settings
from django.db.models import Case, ExpressionWrapper, F, FloatField, When
from django.contrib import admin, messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.http import urlencode
from django.utils.html import format_html

from .models import product, department, tax, deposit
from stores import stock
from stores.models import Store
from .stock_import import ImportCancelled, import_stock

# django-import-export pulls in tablib[ods] -> odfpy, which ships no binary
# wheel and cannot install on build-locked hosts (e.g. Vercel). Fall back to
# plain ModelAdmin (no import/export buttons) when the package is absent.
try:
    from import_export.admin import ImportExportModelAdmin
    from import_export import resources
    HAS_IMPORT_EXPORT = True
except ImportError:
    HAS_IMPORT_EXPORT = False


if HAS_IMPORT_EXPORT:
    class ProductResource(resources.ModelResource):
        class Meta:
            model = product
            fields = ("id","barcode","name","sales_price","cost_price",
                "department","department__department_name","department__department_desc",
                "department__department_slug", "tax_category", "tax_category__tax_category",
                "tax_category__tax_desc", "tax_category__tax_percentage", "deposit_category",
                "deposit_category__deposit_category","deposit_category__deposit_desc",
                "deposit_category__deposit_value", "product_desc")
            export_order = fields


class StockUploadForm(forms.Form):
    """One-file upload form for the admin stock import (.xlsx)."""

    store = forms.ModelChoiceField(
        queryset=Store.objects.filter(is_active=True), empty_label=None, required=False,
        label="Receive into",
        help_text="Which location the quantities are added to. Usually the warehouse.")

    stock_file = forms.FileField(
        label="Stock file (.xlsx)",
        help_text=(
            "Excel sheet with columns: Sr. No., Code, Barcode, Size, Quantity, "
            "plus optional Sales Price and Cost Price. New barcodes are "
            "created; existing barcodes get the quantity ADDED to current "
            "stock at the chosen location and prices updated only where the sheet provides a value. "
            "If any row is invalid, nothing is saved."
        ),
    )


LOW_STOCK_THRESHOLD = getattr(settings, "LOW_STOCK_THRESHOLD", 5)


class StockStatusFilter(admin.SimpleListFilter):
    title = "stock status"
    parameter_name = "stock"

    def lookups(self, request, model_admin):
        return (
            ("in", "In stock"),
            ("low", f"Low stock (≤ {LOW_STOCK_THRESHOLD})"),
            ("out", "Out of stock"),
        )

    def queryset(self, request, queryset):
        # total_stock is annotated in ProductAdmin.get_queryset (all branches).
        if self.value() == "in":
            return queryset.filter(total_stock__gt=LOW_STOCK_THRESHOLD)
        if self.value() == "low":
            return queryset.filter(total_stock__gt=0, total_stock__lte=LOW_STOCK_THRESHOLD)
        if self.value() == "out":
            return queryset.filter(total_stock__lte=0)
        return queryset


class CostPriceFilter(admin.SimpleListFilter):
    title = "cost price"
    parameter_name = "cost"

    def lookups(self, request, model_admin):
        return (("missing", "No cost price"), ("set", "Has cost price"))

    def queryset(self, request, queryset):
        if self.value() == "missing":
            return queryset.filter(cost_price__lte=0)
        if self.value() == "set":
            return queryset.filter(cost_price__gt=0)
        return queryset


@admin.register(product)
class ProductAdmin(ImportExportModelAdmin if HAS_IMPORT_EXPORT else admin.ModelAdmin):
    list_display = ("name", "barcode", "department", "sales_price", "cost_price", "margin",
                    "total_stock_display", "stock_status", "tax_category", "deposit_category")
    list_display_links = ("name",)
    # Stock is changed through Receive / Transfer / sales so every change is logged.
    list_editable = ("sales_price", "cost_price")
    list_filter = (StockStatusFilter, CostPriceFilter, "department", "tax_category", "deposit_category")
    search_fields = ("barcode", "name", "department__department_name")
    list_select_related = ("department", "tax_category", "deposit_category")
    list_per_page = 100
    ordering = ("name",)
    change_list_template = "inventory/product_changelist.html"

    def get_queryset(self, request):
        # Margin as a DB expression so the column can be sorted; stock = all branches.
        qs = stock.with_stock(super().get_queryset(request), None, name="total_stock")
        return qs.annotate(
            margin_pct=Case(
                When(sales_price__gt=0, cost_price__gt=0, then=ExpressionWrapper(
                    (F("sales_price") - F("cost_price")) * 100.0 / F("sales_price"),
                    output_field=FloatField())),
                default=None, output_field=FloatField()))

    @admin.display(description="Margin", ordering="margin_pct")
    def margin(self, obj):
        if obj.margin_pct is None or not obj.cost_price:
            return format_html('<span style="color:#9a9db8">—</span>')
        color = "#e0475b" if obj.margin_pct < 0 else "#12a46a" if obj.margin_pct >= 20 else "#d97706"
        return format_html('<span style="color:{};font-weight:700">{}%</span>', color, f"{obj.margin_pct:.1f}")

    @admin.display(description="Stock (all branches)", ordering="total_stock")
    def total_stock_display(self, obj):
        return obj.total_stock

    @admin.display(description="Status", ordering="total_stock")
    def stock_status(self, obj):
        if obj.total_stock <= 0:
            label, bg, fg = "Out", "#fde8eb", "#e0475b"
        elif obj.total_stock <= LOW_STOCK_THRESHOLD:
            label, bg, fg = "Low", "#fff4e0", "#d97706"
        else:
            label, bg, fg = "In stock", "#e3f6ee", "#12a46a"
        return format_html(
            '<span style="background:{};color:{};padding:2px 10px;border-radius:999px;'
            'font-size:12px;font-weight:700;white-space:nowrap">{}</span>', bg, fg, label)

    # def has_import_permission(self,request):
    #     return False

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "stock-upload/",
                self.admin_site.admin_view(self.stock_upload_view),
                name="inventory_product_stock_upload",
            ),
        ]
        return custom + urls

    def stock_upload_view(self, request):
        """Upload an .xlsx stock file and import it (all-or-nothing)."""
        if not self.has_add_permission(request):
            return HttpResponseForbidden("You do not have permission to add stock.")

        context = dict(self.admin_site.each_context(request))
        context.update({
            "title": "Upload stock from Excel (.xlsx)",
            "opts": self.model._meta,
            "changelist_url": reverse("admin:inventory_product_changelist"),
        })

        if request.method == "POST":
            form = StockUploadForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    created, updated = import_stock(form.cleaned_data["stock_file"],
                                                    store=form.cleaned_data["store"], user=request.user)
                except ImportCancelled as exc:
                    form.add_error("stock_file", str(exc))
                else:
                    messages.success(
                        request,
                        f"Stock import complete into {form.cleaned_data['store']}: "
                        f"{created} products created, {updated} existing products topped up.",
                    )
                    return redirect("admin:inventory_product_changelist")
        else:
            form = StockUploadForm(initial={"store": Store.warehouse()})

        context["form"] = form
        return render(request, "inventory/stock_upload.html", context)


if HAS_IMPORT_EXPORT:
    ProductAdmin.resource_class = ProductResource


@admin.register(department)
class DepartmentAdmin(ImportExportModelAdmin if HAS_IMPORT_EXPORT else admin.ModelAdmin):
    list_display= ('department_name','department_desc','Products_In_Department')

    def Products_In_Department(self,obj):
        count = product.objects.filter(department=obj).count()
        url = (
            reverse("admin:inventory_product_changelist")
            + "?"
            + urlencode({"department__id": f"{obj.id}"})
        )
        return format_html('<a href="{}" style="color:green;padding-left:20px">{} Products</a>', url, count)


@admin.register(tax)
class TaxAdmin(ImportExportModelAdmin if HAS_IMPORT_EXPORT else admin.ModelAdmin):
    list_display= ('tax_category','tax_percentage','tax_desc')


@admin.register(deposit)
class DepositAdmin(ImportExportModelAdmin if HAS_IMPORT_EXPORT else admin.ModelAdmin):
    list_display= ('deposit_category','deposit_value','deposit_desc')
