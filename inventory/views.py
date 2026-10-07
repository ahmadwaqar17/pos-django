from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from .models import product as Product
from .models import product
from django import forms
from django.db.models import Q
from django.contrib import messages
from stores import stock
from stores.access import manager_required, visible_stores
from stores.models import BranchStock, StockMovement
from django.forms import TextInput
from cart.models import Cart
import decimal


class ProductLookup(forms.Form):
    barcode = forms.CharField(widget=TextInput(attrs={' autocomplete':"off",'placeholder': "Search by barcode or product name..."}),max_length = 32)

class AddProduct(forms.Form):
    qty = forms.IntegerField(label="Quantity To Be Added",widget=TextInput(attrs={'style':"width:100%"}))
    barcode = forms.CharField(label="Product Barcode", widget=TextInput(attrs={'autofocus':"autofocus",' autocomplete':"off",'style':"width:100%"}),max_length = 32)


# Create your views here.
@login_required(login_url="/user/login")
def product_lookup(request):
    """Look a product up by full barcode, or search by part of a barcode,
    name or description. ``?barcode=`` opens one product directly (used by
    the live-search suggestions)."""
    obj = None
    matches = []
    query = ""
    if request.method == "POST":
        form = ProductLookup(request.POST)
        if form.is_valid():
            query = form.cleaned_data['barcode'].strip()
    elif request.GET.get('barcode'):
        query = request.GET['barcode'].strip()

    products = stock.with_stock(product.objects.select_related('department'), request.store)
    if query:
        obj = products.filter(barcode=query).first()
        if obj is None:
            matches = list(products
                .filter(Q(barcode__icontains=query) | Q(name__icontains=query)
                        | Q(product_desc__icontains=query))
                .order_by('name')[:50])
            if len(matches) == 1:
                obj, matches = matches[0], []

    stock_by_branch = []
    if obj is not None:
        stock_by_branch = list(BranchStock.objects.filter(product=obj, store__in=visible_stores(request))
                               .select_related('store').order_by('store__is_warehouse', 'store__name'))

    context = {
        'form': ProductLookup(initial={'barcode': query} if matches else None),
        'obj': obj,
        'stock_by_branch': stock_by_branch,
        'matches': matches,
        'query': query,
        'notFound': bool(query) and obj is None and not matches,
    }
    return render(request, "productLookup.html", context=context)


@login_required(login_url="/user/login")
def manualAmount(request,manual_department,amount):
    """Needs to add Variable Barcode in Inventory and make Prices Zero and Quantity One

    Args:
        request (_type_): _description_
        manual_department (_type_): _description_
        amount (_type_): _description_

    Returns:
        _type_: _description_
    """
    cart = Cart(request)
    product = Product.objects.filter(barcode=manual_department).first()
    if product:
        amount = round(decimal.Decimal(amount),2)
        product.barcode = f"{product.barcode}_{amount}".replace(".","")
        product.sales_price = amount
        cart.add(product=product,quantity=int(1))
        return redirect('register')
    else:
        scheme = request.is_secure() and "https" or "http"
        return redirect(f"{scheme}://{request.get_host()}/register/ProductNotFound/")


@login_required(login_url="/user/login")
@manager_required
def inventoryAdd(request):
    context = { }
    if request.method == "POST":
        form = AddProduct(request.POST)
        if form.is_valid():
            try:
                obj = product.objects.get(barcode=form.cleaned_data['barcode'])
                added = int(form.cleaned_data['qty'])
                if added <= 0:
                    raise ValueError
                new_qty = stock.adjust(request.store, obj, added, StockMovement.RECEIVE,
                                       user=request.user, note="Received in POS")
                context.update(received=True, p_qty=new_qty - added, n_qty=added, new_qty=new_qty)
            except ValueError:
                obj = None
                messages.error(request, "Quantity must be more than 0.")
            except product.DoesNotExist:
                obj = None
                context['notFound']= form.cleaned_data['barcode']
            context['obj'] = obj
    form = AddProduct(initial={'qty':1})
    context['form'] = form
    return render(request,'addInventory.html',context=context)
