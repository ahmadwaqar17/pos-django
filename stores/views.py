from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from inventory.models import product
from . import stock
from .access import SESSION_ALL, SESSION_STORE, manager_required, owner_required
from .models import BranchStock, StockMovement, StockTransfer, Store

LOGIN = "/user/login/"


# --------------------------------------------------------------------------- helpers

def stock_stores(request):
    """Locations whose stock this user may see: owners all, managers theirs + the warehouse."""
    active = Store.objects.filter(is_active=True)
    if request.is_owner:
        return active
    return active.filter(Q(pk=request.store.pk) | Q(is_warehouse=True))


def transfer_sources(request):
    """Owners can move stock from anywhere; managers only out of their own branch."""
    if request.is_owner:
        return Store.objects.filter(is_active=True)
    return Store.objects.filter(pk=request.store.pk, is_active=True)


def visible_transfers(request):
    qs = StockTransfer.objects.select_related("source", "destination", "created_by")
    if request.is_owner:
        return qs
    return qs.filter(Q(source=request.store) | Q(destination=request.store))


# --------------------------------------------------------------------------- branch switcher

@login_required(login_url=LOGIN)
@owner_required
@require_POST
def switch_store(request):
    choice = request.POST.get("store", "")
    if choice == "all":
        request.session[SESSION_ALL] = True
    else:
        store = Store.objects.filter(pk=choice, is_active=True).first() if choice.isdigit() else None
        if store is None:
            messages.error(request, "That branch doesn't exist.")
        else:
            request.session[SESSION_STORE] = store.pk
            request.session[SESSION_ALL] = False
            messages.success(request, f"Now working in {store.name}.")
    nxt = request.POST.get("next") or "/"
    if not url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure()):
        nxt = "/"
    return redirect(nxt)


# --------------------------------------------------------------------------- stock levels

@login_required(login_url=LOGIN)
@manager_required
def stock_levels(request):
    stores = list(stock_stores(request))
    low = settings.LOW_STOCK_THRESHOLD
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")

    products = stock.with_stock(product.objects.select_related("department"), None, name="total")
    if q:
        products = products.filter(Q(barcode__icontains=q) | Q(name__icontains=q)
                                   | Q(department__department_name__icontains=q))
    if status == "out":
        products = products.filter(total__lte=0)
    elif status == "low":
        products = products.filter(total__gt=0, total__lte=low)
    elif status == "negative":
        products = products.filter(branch_stock__qty__lt=0).distinct()

    page = Paginator(products.order_by("name"), 100).get_page(request.GET.get("page"))
    cells = {(r.product_id, r.store_id): r.qty for r in BranchStock.objects.filter(
        product__in=[p.pk for p in page], store__in=stores)}
    rows = [{
        "product": p,
        "cells": [cells.get((p.pk, s.pk), 0) for s in stores],
        "total": sum(cells.get((p.pk, s.pk), 0) for s in stores),
    } for p in page]

    totals = BranchStock.objects.filter(store__in=stores).values("store").annotate(
        units=Sum("qty"), skus=Count("id", filter=Q(qty__gt=0)))
    by_store = {t["store"]: t for t in totals}
    store_cards = [{"store": s, "units": by_store.get(s.pk, {}).get("units") or 0,
                    "skus": by_store.get(s.pk, {}).get("skus") or 0} for s in stores]

    return render(request, "stores/stock_levels.html", {
        "stores": stores, "rows": rows, "page": page, "q": q, "status": status,
        "low": low, "store_cards": store_cards,
    })


# --------------------------------------------------------------------------- transfers

@login_required(login_url=LOGIN)
@manager_required
def transfer_list(request):
    transfers = visible_transfers(request).annotate(
        lines=Count("movements", filter=Q(movements__kind=StockMovement.TRANSFER_OUT)),
        units=Sum("movements__qty_change", filter=Q(movements__kind=StockMovement.TRANSFER_IN)),
    ).order_by("-created_at", "-id")
    page = Paginator(transfers, 50).get_page(request.GET.get("page"))
    return render(request, "stores/transfer_list.html", {"page": page})


@login_required(login_url=LOGIN)
@manager_required
def transfer_new(request):
    sources = transfer_sources(request)
    destinations = Store.objects.filter(is_active=True)
    warehouse = Store.warehouse()
    default_source = (warehouse if request.is_owner and warehouse else request.store)
    form = {"source": default_source.pk if default_source else "", "destination": "", "note": "", "lines": []}

    if request.method == "POST":
        form["source"] = request.POST.get("source", "")
        form["destination"] = request.POST.get("destination", "")
        form["note"] = request.POST.get("note", "").strip()
        barcodes = request.POST.getlist("barcode")
        qtys = request.POST.getlist("qty")
        found = {p.barcode: p for p in product.objects.filter(barcode__in=barcodes)}
        lines, errors = [], []
        for barcode, qty in zip(barcodes, qtys):
            barcode = barcode.strip()
            if not barcode:
                continue
            form["lines"].append({"barcode": barcode, "qty": qty,
                                  "name": found[barcode].name if barcode in found else ""})
            if barcode not in found:
                errors.append(f"Unknown barcode {barcode}.")
            else:
                lines.append((found[barcode], qty))

        source = sources.filter(pk=form["source"]).first() if str(form["source"]).isdigit() else None
        destination = destinations.filter(pk=form["destination"]).first() if str(form["destination"]).isdigit() else None
        if source is None:
            errors.append("You can't send stock from that location.")
        if not errors:
            try:
                record = stock.transfer(source, destination, lines, user=request.user, note=form["note"])
            except stock.StockError as exc:
                errors.append(str(exc))
            else:
                messages.success(request, f"Transfer #{record.pk} done: stock moved from "
                                          f"{record.source} to {record.destination}.")
                return redirect("transfer_detail", pk=record.pk)
        for e in errors:
            messages.error(request, e)

    return render(request, "stores/transfer_form.html", {
        "sources": sources, "destinations": destinations, "form": form,
    })


@login_required(login_url=LOGIN)
@manager_required
def transfer_detail(request, pk):
    record = visible_transfers(request).filter(pk=pk).first()
    if record is None:
        raise Http404("Transfer not found")
    lines = (record.movements.filter(kind=StockMovement.TRANSFER_IN)
             .select_related("product").order_by("product__name"))
    return render(request, "stores/transfer_detail.html", {
        "transfer": record, "lines": lines, "units": sum(l.qty_change for l in lines),
    })


@login_required(login_url=LOGIN)
@manager_required
def stock_search(request):
    """Product search for the transfer form, with the quantity at ``store``."""
    store = stock_stores(request).filter(pk=request.GET.get("store") or 0).first()
    q = request.GET.get("q", "").strip()
    products = stock.with_stock(product.objects.select_related("department"), store)
    if q:
        products = products.filter(Q(barcode__icontains=q) | Q(name__icontains=q))
    if request.GET.get("available") == "1":
        products = products.filter(qty__gt=0)
    try:
        limit = max(1, min(int(request.GET.get("limit", 20)), 2000))
    except ValueError:
        limit = 20
    data = [{"barcode": p.barcode, "name": p.name, "qty": p.qty,
             "department": p.department.department_name}
            for p in products.order_by("name")[:limit]]
    return JsonResponse({"products": data})


# --------------------------------------------------------------------------- movements

@login_required(login_url=LOGIN)
@manager_required
def movement_list(request):
    stores = stock_stores(request)
    moves = StockMovement.objects.filter(store__in=stores).select_related(
        "store", "product", "user", "sale", "transfer")
    store_id = request.GET.get("store", "")
    kind = request.GET.get("kind", "")
    q = request.GET.get("q", "").strip()
    if store_id.isdigit():
        moves = moves.filter(store_id=store_id)
    if kind:
        moves = moves.filter(kind=kind)
    if q:
        moves = moves.filter(Q(product__barcode__icontains=q) | Q(product__name__icontains=q))
    page = Paginator(moves, 100).get_page(request.GET.get("page"))
    return render(request, "stores/movement_list.html", {
        "page": page, "stores": stores, "kinds": StockMovement.KINDS,
        "f_store": store_id, "f_kind": kind, "q": q,
    })
