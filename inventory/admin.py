from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.http import urlencode
from django.utils.html import format_html

from .models import product, department, tax, deposit
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
            fields = ("id","barcode","name","sales_price","qty","cost_price",
                "department","department__department_name","department__department_desc",
                "department__department_slug", "tax_category", "tax_category__tax_category",
                "tax_category__tax_desc", "tax_category__tax_percentage", "deposit_category",
                "deposit_category__deposit_category","deposit_category__deposit_desc",
                "deposit_category__deposit_value", "product_desc")
            export_order = fields


class StockUploadForm(forms.Form):
    """One-file upload form for the admin stock import (.xlsx)."""

    stock_file = forms.FileField(
        label="Stock file (.xlsx)",
        help_text=(
            "Excel sheet with columns: Sr. No., Code, Barcode, Size, Quantity, "
            "plus optional Sales Price and Cost Price. New barcodes are "
            "created; existing barcodes get the quantity ADDED to current "
            "stock and prices updated only where the sheet provides a value. "
            "If any row is invalid, nothing is saved."
        ),
    )


@admin.register(product)
class ProductAdmin(ImportExportModelAdmin if HAS_IMPORT_EXPORT else admin.ModelAdmin):
    editable_list = ["sales_price",'qty']
    list_display = ("barcode","name","sales_price","qty","department","tax_category","deposit_category")
    list_filter = ("department","tax_category", "deposit_category",)
    change_list_template = "inventory/product_changelist.html"

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
                    created, updated = import_stock(form.cleaned_data["stock_file"])
                except ImportCancelled as exc:
                    form.add_error("stock_file", str(exc))
                else:
                    messages.success(
                        request,
                        f"Stock import complete: {created} products created, "
                        f"{updated} existing products topped up.",
                    )
                    return redirect("admin:inventory_product_changelist")
        else:
            form = StockUploadForm()

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
