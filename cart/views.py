# Create your views here.
from django.shortcuts import redirect
from inventory.models import product as Product
from django.contrib.auth.decorators import login_required
from .models import Cart
from django.contrib import messages
from stores import stock


@login_required(login_url="/user/login")
def cart_add(request,id,qty):
    cart = Cart(request)
    product = Product.objects.filter(barcode=id).first()
    if not product:
        # Fallback: Search by exact or partial product name / barcode
        product = Product.objects.filter(name__iexact=id).first()
    if not product:
        product = Product.objects.filter(name__icontains=id).first()
    if not product:
        product = Product.objects.filter(barcode__icontains=id).first()

    if product:
        cart.add(product=product,quantity=int(qty))
        # Warn but allow: a wrong stock count must never block a sale.
        in_cart = cart.cart.get(product.barcode, {}).get('quantity', 0)
        on_hand = stock.branch_qty(request.store, product)
        if in_cart > on_hand:
            branch = request.store.name if request.store else "this branch"
            messages.warning(request, f"Low stock: {product.name} — {in_cart} in cart, "
                                      f"only {max(on_hand, 0)} on hand at {branch}.")
        return redirect('register')
    else:
        scheme = request.is_secure() and "https" or "http"
        return redirect(f"{scheme}://{request.get_host()}/register/ProductNotFound/")


@login_required(login_url="/user/login")
def item_remove(request, id):
    """Remove an entire cart line immediately (all qty of that product).

    One row gone, cart totals recomputed on the next render. The manual
    discount is cleared so it cannot linger on a changed cart.
    """
    cart = Cart(request)
    product = Product.objects.filter(barcode=id).first()
    if product:
        cart.remove(product)
    request.session["Discount_Percent"] = 0
    request.session.modified = True
    return redirect("register")


@login_required(login_url="/user/login")
def item_clear(request, id):
    """Legacy route: delegates to ``item_remove`` (same behaviour)."""
    return item_remove(request, id)


@login_required(login_url="/user/login")
def item_increment(request, id):
    cart = Cart(request)
    product = Product.objects.get(barcode=id)
    cart.add(product=product)
    return redirect("cart_detail")


@login_required(login_url="/user/login")
def item_decrement(request, id):
    cart = Cart(request)
    product = Product.objects.get(barcode=id)
    cart.decrement(product=product)
    return redirect("cart_detail")


@login_required(login_url="/user/login")
def cart_clear(request):
    cart = Cart(request)
    cart.clear()
    # A manual discount belongs to the cleared transaction.
    request.session["Discount_Percent"] = 0
    request.session.modified = True
    return redirect('register')
