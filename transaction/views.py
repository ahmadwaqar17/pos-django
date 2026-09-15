from django.shortcuts import redirect, render
from django.http import Http404, HttpResponse
from django.conf import settings 
from cart.models import Cart
import pandas as pd
from .models import transaction
from datetime import datetime, timedelta
from django.contrib.auth.decorators import login_required
from django import forms

class DateSelector(forms.Form):
    start_date = forms.DateField(widget = forms.SelectDateWidget())
    end_date = forms.DateField(widget = forms.SelectDateWidget())


class printer:
    printer = None

    def printReceipt(printText,times=0,*args,**kwargs):
        try:
            if printer.printer:
                printer.printer.text(printText)
                printer.printer.text(f"\nPrint Time: {datetime.now():%Y-%m-%d %H:%M}\n\n\n")
                # printer.printer.print_and_feed(n=3)
        except Exception as e: 
            printer.connectPrinter()
            if times <3:
                printer.printReceipt(printText, times+1)

    def connectPrinter():
        try:
            # Imported lazily: USB receipt printing is unavailable on hosts
            # like Vercel, and a top-level import here would crash the whole
            # URLconf (urls.py imports this module) and take down every route.
            from escpos.printer import Usb
            printer.printer = Usb(eval(settings.PRINTER_VENDOR_ID),eval(settings.PRINTER_PRODUCT_ID))
        except Exception as e:
            print(e)
            printer.printer = None


def transactionReceipt(request,transNo):
    # Demo sales (read-only deployments) live in the session
    demo = _demo_get_transaction(request, transNo)
    if demo:
        t, items = demo
        return render(request,'receiptView.html',context={
            'receipt': t.receipt, 'transNo': transNo,
            'txn': t, 'items': items,
            'store_name': settings.STORE_NAME, 'store_address': settings.STORE_ADDRESS,
            'store_phone': settings.STORE_PHONE,
        })
    try:
        t = transaction.objects.get(transaction_id=transNo)
        import ast
        items = ast.literal_eval(t.products)
        for it in items:
            it['line_total'] = round(float(it['price']) * float(it['quantity']), 2)
        return render(request,'receiptView.html',context={
            'receipt': t.receipt, 'transNo': transNo,
            'txn': t, 'items': items,
            'store_name': settings.STORE_NAME, 'store_address': settings.STORE_ADDRESS,
            'store_phone': settings.STORE_PHONE,
        })
    except transaction.DoesNotExist:
        raise Http404("No Transactions Found!!!")

def transactionPrintReceipt(request,transNo):
    # Demo sales: no USB printer exists server-side; return to the receipt
    # page (its Print button works via the browser's print dialog there).
    if _demo_get_transaction(request, transNo):
        return redirect(f'/transaction_receipt/{transNo}/')
    try:
        receipt = transaction.objects.get(transaction_id=transNo).receipt
        if printer.printer is None:
            printer.connectPrinter() 
            print("Connecting Printer")
        if printer.printer: 
            printer.printReceipt(receipt)
        return redirect(f'/transaction_receipt/{transNo}/')
    except Exception as e:
        print(e)
        return redirect('register')


@login_required(login_url="/user/login/")
def transactionView(request, transNo=None):
    end_date=datetime.now().date()
    start_date=datetime.now().date()-timedelta(7)
    form = DateSelector(initial = {'end_date':end_date, 'start_date':start_date})
    if request.method == "POST":
        form = DateSelector(request.POST)
        if form.is_valid():
            end_date= form.cleaned_data['end_date']
            start_date= form.cleaned_data['start_date']
    transactions = list(transaction.objects.filter(transaction_dt__date__range = (start_date,end_date)).order_by('-transaction_dt').values('transaction_dt', 'transaction_id','total_sale','payment_type'))
    # Demo sales appear in the list too (newest first)
    for tid, data in sorted((request.session.get('demo_transactions') or {}).items(), reverse=True):
        transactions.insert(0, {
            'transaction_dt': datetime.strptime(data['transaction_dt'], '%Y-%m-%d %H:%M:%S'),
            'transaction_id': tid,
            'total_sale': data['total_sale'],
            'payment_type': data['payment_type'],
        })
    return render(request, 'transactions.html',
        context={'transactions':transactions,
            'form':form,})


@login_required(login_url="/user/login/")
def returnsTransaction(request):
    Cart(request).returns()
    return redirect('register')


@login_required(login_url="/user/login/")
def suspendTransaction(request):
    if Cart(request).isNotEmpty():
        if "Cart_Sessions" in request.session.keys():
            request.session["Cart_Sessions"][datetime.now().strftime('%Y%m%d%H%M%S%f')] = request.session[settings.CART_SESSION_ID]
            request.session.modified = True
        else:
            request.session["Cart_Sessions"] = {}
            request.session["Cart_Sessions"][datetime.now().strftime('%Y%m%d%H%M%S%f')] = request.session[settings.CART_SESSION_ID] 
    return redirect("cart_clear")


@login_required(login_url="/user/login/")
def recallTransaction(request, recallTransNo = None):
    if Cart(request).isNotEmpty():
        return redirect("suspend_transaction")
    if recallTransNo:
        request.session[settings.CART_SESSION_ID] = request.session["Cart_Sessions"][recallTransNo]
        del request.session["Cart_Sessions"][recallTransNo]
        request.session.modified = True
    elif "Cart_Sessions" in request.session.keys() and len(request.session["Cart_Sessions"]):
        return render(request, "recallTransaction.html", context={"obj_rt": request.session["Cart_Sessions"].keys()})
    return redirect("register")


@login_required(login_url="/user/login/")
def endTransactionReceipt(request,transNo):
    try:
        if request.GET["type"]=="cash":
            change = float(request.GET["value"]) - float(request.GET["total"])
            change = f"""<table class="table text-white h3 p-0 m-0"> 
                            <tr> 
                                <td class="text-left pl-5"> Total : </td> 
                                <td class="text-right pr-5"> PKR {request.GET["total"]}</td> 
                            </tr> 
                            <tr> 
                                <td class="text-left pl-5"> Cash : </td> 
                                <td class="text-right pr-5"> PKR {request.GET["value"]}</td> 
                            </tr> 
                            <tr class="h1 badge-danger" >  
                                <td style="padding-top:15px"> Change : </td> 
                                <td style="padding-top:15px"> PKR {change*(-1):.2f}</td> 
                            </tr> 
                        </table>"""
        elif request.GET["type"]=="card":
            change = f"""<table class="table text-white h3 p-0 m-0"> 
                            <tr> 
                                <td class="text-left pl-5"> Total : </td> 
                                <td class="text-right pr-5"> PKR {request.GET["total"]}</td> 
                            </tr> 
                            <tr> 
                                <td class="text-left pl-5"> Card : </td> 
                                <td class="text-right pr-5"> {request.GET["value"]}</td> 
                            </tr> 
                            
                        </table>
                        <div class="h1 badge-danger p-3" >  
                                 CARD TRANSACTION 
                            </div> 
                            """
        
        demo = _demo_get_transaction(request, transNo)
        obj = transaction.objects.get(transaction_id=transNo) if not demo else demo[0]
        return render(request,'endTransaction.html',context={'receipt':obj.receipt,'change':change})
    except transaction.DoesNotExist:
        raise Http404("No Transactions Found!!!")


@login_required(login_url="/user/login/")
def endTransaction(request,type,value):
    try:
        return_transaction = None
        # Card Transactions
        cart = request.session[settings.CART_SESSION_ID]
        total = round(pd.DataFrame(cart).T["line_total"].astype(float).sum(),2)
        if type == "card": # Card Transaction
            # EBT Transaction
            if value=="EBT": 
                return_transaction = _complete_sale(request,"EBT",total,cart,total)
            # DEBIT/CREDIT Transaction
            elif value=="DEBIT_CREDIT": 
                return_transaction = _complete_sale(request,"DEBIT/CREDIT",total,cart,total)
        elif type=="cash": # Cash Transaction
            value = round(float(value),2)
            if value>= total: 
                return_transaction = _complete_sale(request,"CASH",total,cart,value)
        if return_transaction:
            Cart(request).clear()
            return redirect(f"/endTransaction/{return_transaction.transaction_id}/?type={type}&value={value}&total={total}")
        return redirect("register")
    except Exception as e:
        print(e,type,value,request.user)
        return redirect("register")


# --- Demo mode (read-only deployments): completed sales are kept in the
# --- session instead of the read-only database, so cashiers can see the
# --- full sell -> receipt flow without persistence.
def _complete_sale(request, payment_type, total, cart, value):
    """Persist the sale in the DB, or in the session when the DB is read-only."""
    if getattr(settings, 'READ_ONLY_DATABASES', False):
        return _demo_add_transaction(request, payment_type, total, cart, value)
    return addTransaction(request.user, payment_type, total, cart, value)


def _demo_add_transaction(request, payment_type, total, cart, value):
    """Build a receipt exactly like addTransaction, store it in the session,
    and return a lightweight namespace mimicking a transaction row."""
    from types import SimpleNamespace
    transaction_id = datetime.now().strftime('%Y%m%d%H%M%S%f')
    short_id = transaction_id[:14]
    cart_df = pd.DataFrame(cart).T.reset_index(drop=True)
    cart_df.index = cart_df.index + 1
    tax_total = round(cart_df["tax_value"].astype(float).sum(),2)
    deposit_total = round(cart_df["deposit_value"].astype(float).sum(),2)
    receipt_date = datetime.now().strftime('%d %b %Y  %I:%M %p')
    w = settings.RECEIPT_CHAR_COUNT

    items_lines = []
    for idx, row in cart_df.iterrows():
        items_lines.append(f" {str(idx)+')':<3}{str(row['name'])[:20]}")
        items_lines.append(f"    {row['barcode']:<12} x{int(row['quantity']):<3} PKR {row['price']}")
        dep = float(row['deposit_value'])
        if dep > 0:
            items_lines.append(f"    Deposit:  PKR {dep:.2f}")
    cart_string = "\n".join(items_lines)

    receipt = f"{'='*w}\n"
    receipt += f"{settings.STORE_NAME.center(w)}\n"
    receipt += f"{settings.STORE_ADDRESS.center(w)}\n"
    if settings.STORE_PHONE:
        receipt += f"{'Ph: '+str(settings.STORE_PHONE).center(w-4)}\n"
    receipt += f"{'='*w}\n"
    receipt += f"{receipt_date.center(w)}\n"
    receipt += f"{'Receipt #'+short_id.center(w-8)}\n"
    receipt += f"{'-'*w}\n"
    receipt += f" {'#':<3}{'Item':<13}{'Qty':>4}  {'Price':>8}\n"
    receipt += f" {'-'*w}\n"
    receipt += cart_string + "\n"
    receipt += f" {'-'*w}\n"
    receipt += f" {'Subtotal:':<15}PKR {round(total-tax_total,2):>8.2f}\n"
    if tax_total > 0:
        receipt += f" {'Tax:':<15}PKR {tax_total:>8.2f}\n"
    if deposit_total > 0:
        receipt += f" {'Deposit:':<15}PKR {deposit_total:>8.2f}\n"
    receipt += f" {'='*w}\n"
    receipt += f" {'TOTAL:':<15}PKR {round(total,2):>8.2f}\n"
    receipt += f" {'-'*w}\n"
    receipt += f" {str(payment_type):<15}PKR {round(value,2):>8.2f}\n"
    receipt += f" {'CHANGE:':<15}PKR {round(value-total,2):>8.2f}\n"
    receipt += f"{'='*w}\n"
    receipt += f"{settings.RECEIPT_FOOTER.center(w)}\n"
    receipt += f"{'='*w}\n"
    receipt += f"{('Trans ID: '+transaction_id).center(w)}\n"
    receipt += f"{'='*w}"

    import json
    transaction_id = transaction_id
    demo_txn = SimpleNamespace(
        transaction_id=transaction_id,
        transaction_dt=datetime.strptime(transaction_id[:-6],'%Y%m%d%H%M%S'),
        total_sale=total,
        sub_total=round(total-tax_total,2),
        tax_total=tax_total,
        deposit_total=deposit_total,
        payment_type=payment_type,
        receipt=receipt,
    )
    store = request.session.get('demo_transactions') or {}
    # to_json() guarantees JSON-safe scalar types (numpy ints would break the
    # cookie session serializer).
    store[transaction_id] = {
        'transaction_id': transaction_id,
        'transaction_dt': demo_txn.transaction_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'total_sale': total,
        'sub_total': demo_txn.sub_total,
        'tax_total': tax_total,
        'deposit_total': deposit_total,
        'payment_type': payment_type,
        'receipt': receipt,
        'products': json.loads(cart_df.to_json(orient='records')),
    }
    # Cookie sessions are tiny (~4KB): keep only the most recent demo sale,
    # or the cookie would be dropped by the browser and destroy the session.
    request.session['demo_transactions'] = dict(sorted(store.items())[-1:])
    request.session.modified = True
    return demo_txn


def _demo_get_transaction(request, trans_no):
    """Return (txn, items) from the session demo store, or None."""
    from types import SimpleNamespace
    data = (request.session.get('demo_transactions') or {}).get(trans_no)
    if not data:
        return None
    txn = SimpleNamespace(**{k: data[k] for k in (
        'transaction_id', 'transaction_dt', 'total_sale', 'sub_total',
        'tax_total', 'deposit_total', 'payment_type', 'receipt')})
    txn.transaction_dt = datetime.strptime(txn.transaction_dt, '%Y-%m-%d %H:%M:%S')
    items = data['products']
    for it in items:
        it['line_total'] = round(float(it['price']) * float(it['quantity']), 2)
    return txn, items


def addTransaction(user,payment_type,total,cart,value):
    transaction_id = datetime.now().strftime('%Y%m%d%H%M%S%f')
    short_id = transaction_id[:14]
    cart_df = pd.DataFrame(cart).T.reset_index(drop=True)
    cart_df.index = cart_df.index + 1
    tax_total = round(cart_df["tax_value"].astype(float).sum(),2)
    deposit_total = round(cart_df["deposit_value"].astype(float).sum(),2)
    receipt_date = datetime.now().strftime('%d %b %Y  %I:%M %p')
    w = settings.RECEIPT_CHAR_COUNT

    # Item lines
    items_lines = []
    for idx, row in cart_df.iterrows():
        items_lines.append(f" {str(idx)+')':<3}{str(row['name'])[:20]}")
        items_lines.append(f"    {row['barcode']:<12} x{int(row['quantity']):<3} PKR {row['price']}")
        dep = float(row['deposit_value'])
        if dep > 0:
            items_lines.append(f"    Deposit:  PKR {dep:.2f}")
    cart_string = "\n".join(items_lines)

    receipt = f"{'='*w}\n"
    receipt += f"{settings.STORE_NAME.center(w)}\n"
    receipt += f"{settings.STORE_ADDRESS.center(w)}\n"
    if settings.STORE_PHONE:
        receipt += f"{'Ph: '+str(settings.STORE_PHONE).center(w-4)}\n"
    receipt += f"{'='*w}\n"
    receipt += f"{receipt_date.center(w)}\n"
    receipt += f"{'Receipt #'+short_id.center(w-8)}\n"
    receipt += f"{'-'*w}\n"
    receipt += f" {'#':<3}{'Item':<13}{'Qty':>4}  {'Price':>8}\n"
    receipt += f" {'-'*w}\n"
    receipt += cart_string + "\n"
    receipt += f" {'-'*w}\n"
    receipt += f" {'Subtotal:':<15}PKR {round(total-tax_total,2):>8.2f}\n"
    if tax_total > 0:
        receipt += f" {'Tax:':<15}PKR {tax_total:>8.2f}\n"
    if deposit_total > 0:
        receipt += f" {'Deposit:':<15}PKR {deposit_total:>8.2f}\n"
    receipt += f" {'='*w}\n"
    receipt += f" {'TOTAL:':<15}PKR {round(total,2):>8.2f}\n"
    receipt += f" {'-'*w}\n"
    receipt += f" {str(payment_type):<15}PKR {round(value,2):>8.2f}\n"
    receipt += f" {'CHANGE:':<15}PKR {round(value-total,2):>8.2f}\n"
    receipt += f"{'='*w}\n"
    receipt += f"{settings.RECEIPT_FOOTER.center(w)}\n"
    receipt += f"{'='*w}\n"
    receipt += f"{('Trans ID: '+transaction_id).center(w)}\n"
    receipt += f"{'='*w}"
    
    ## IF CASH DRAWER Connected uncomment below
    # if printer.printer and settings.CASH_DRAWER: 
    #     try: printer.printer.cashdraw(2)
    #     except: pass

    #Saving Transaction into Database
    return transaction.objects.create( transaction_id = transaction_id , transaction_dt = datetime.strptime(transaction_id[:-6],'%Y%m%d%H%M%S'),
            user = user, total_sale= total, sub_total = round(total-tax_total,2),tax_total=tax_total, deposit_total = deposit_total,
            payment_type = payment_type, receipt = receipt, products = str(cart_df.to_dict('records')),
        )
