from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django import forms
from django.db.models import Q
from django.utils.http import url_has_allowed_host_and_scheme
from cart.models import Cart, displayed_items
from inventory.models import product, department
from transaction.models import productTransaction, transaction
from transaction.views import DateSelector
from plotly import express as px
from plotly import offline as po
import plotly.figure_factory as ff
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd
import pytz, os
timezone = pytz.timezone("US/Eastern")



class EnterBarcode(forms.Form):
    barcode = forms.CharField(widget=forms.TextInput(attrs={'autofocus':"autofocus",' autocomplete':"off",'style':"width:100%"}),max_length = 32)
    qty = forms.IntegerField(label="Quantity",widget=forms.TextInput(attrs={'style':"width:100%"}))


@login_required(login_url="/user/login/")
def register(request):
    form = EnterBarcode(initial={'qty':1})
    if request.method == "POST":
        form = EnterBarcode(request.POST)
        if form.is_valid():
            return redirect(f"/cart/add/{form.cleaned_data['barcode']}/{form.cleaned_data['qty']}")
    try:
        cart = request.session[settings.CART_SESSION_ID]
        gross_total = round(pd.DataFrame(cart).T["line_total"].astype(float).sum(),2)
        Tax_Total = round(pd.DataFrame(cart).T["tax_value"].astype(float).sum(),2)
    except KeyError:
        cart = Cart(request)
        gross_total = 0
        Tax_Total = 0
    discount_percent = float(request.session.get("Discount_Percent", 0) or 0)
    discount_amount = round(gross_total * discount_percent / 100, 2)
    Total = round(gross_total - discount_amount, 2)

    all_products = product.objects.select_related('department').all()
    departments = department.objects.all()

    context = {
        'form':form,
        'no_product':  True if "ProductNotFound" in request.path else False,
        'cart':cart,
        'total':Total,
        'gross_total':gross_total,
        'discount_percent':discount_percent,
        'discount_amount':discount_amount,
        'tax_total':Tax_Total,
        'displayed_items':displayed_items.objects.all(),
        'all_products': all_products,
        'departments': departments,
    }
    request.session["Total"] = Total
    request.session["Tax_Total"] = Tax_Total
    request.session.modified = True
    return render(request,'retailScreen.html', context=context)


@login_required(login_url="/user/login/")
def api_products(request):
    q = request.GET.get('q', '').strip()
    dept_id = request.GET.get('department', '').strip()
    products_qs = product.objects.select_related('department').all()
    if q:
        products_qs = products_qs.filter(
            Q(barcode__icontains=q) | Q(name__icontains=q) | Q(product_desc__icontains=q)
        )
    if dept_id and dept_id.isdigit():
        products_qs = products_qs.filter(department_id=int(dept_id))
    
    data = []
    for p in products_qs[:100]:
        data.append({
            'id': p.id,
            'barcode': p.barcode,
            'name': p.name,
            'sales_price': str(p.sales_price),
            'qty': p.qty,
            'department_name': p.department.department_name,
            'department_id': p.department.id,
        })
    return JsonResponse({'products': data})



@login_required(login_url="/user/login/")
def retail_display(request,values=None):
    if values:
        # Same arithmetic as the register so the customer sees exactly what
        # the cashier will charge: line totals include tax + deposit, and the
        # receipt-level discount comes off the gross total.
        cart = request.session.get(settings.CART_SESSION_ID, {})
        items = []
        gross_total = tax_total = deposit_total = 0.0
        for key, value in cart.items():
            try:
                line_total = float(value['line_total'])
                tax = float(value.get('tax_value', 0) or 0)
                deposit = float(value.get('deposit_value', 0) or 0)
                items.append({
                    'id': key,
                    'name': value['name'],
                    'qty': int(value['quantity']),
                    'price': float(value['price']),
                    'line_total': line_total,
                })
            except Exception:
                continue
            gross_total += line_total
            tax_total += tax
            deposit_total += deposit

        gross_total = round(gross_total, 2)
        discount_percent = float(request.session.get("Discount_Percent", 0) or 0)
        discount_amount = round(gross_total * discount_percent / 100, 2)

        return JsonResponse({
            'store': settings.STORE_NAME,
            'currency': 'PKR',
            'items': items,
            'gross_total': gross_total,
            'tax_total': round(tax_total, 2),
            'deposit_total': round(deposit_total, 2),
            'discount_percent': discount_percent,
            'discount': discount_amount,
            'total': round(gross_total - discount_amount, 2),
        })

    return render(request,'retailDisplay.html',context={"store_name":settings.STORE_NAME})


@login_required(login_url="/user/login/")
def report_regular(request,start_date,end_date):
    # timezone.localize(datetime.combine(datetime.strptime(start_date,"%Y-%m-%d").date(), datetime.min.time()))
    start_date = datetime.strptime(start_date,"%Y-%m-%d").date()
    end_date = datetime.strptime(end_date,"%Y-%m-%d").date()
    df = pd.DataFrame(productTransaction.objects.filter(transaction_date_time__date__range = (start_date,end_date)).order_by('-transaction_date_time').values())
    if not df.shape[0]:
        # No sales in the period: show the report page with a note rather
        # than silently bouncing to the home dashboard.
        return render(request,"reportsRegular.html", context={
                "table_html":"<p class=\"text-center text-gray-500\">No transactions found in the selected period.</p>",
                "start_date":start_date,"end_date":end_date,"store_name":settings.STORE_NAME,
                })

    df['transaction_date_time'] = df['transaction_date_time'].apply(lambda x: x.astimezone(timezone) )
    df['date'] = df['transaction_date_time'].dt.date
    df['total_sales'] = (df['qty'] * df['sales_price']) + df['tax_amount'] + df['deposit_amount']
    df['total_pre_sales'] = df['qty'] * df['sales_price']

    date_group = df.groupby(['date','department','payment_type'])[['qty','total_pre_sales','tax_amount','deposit_amount','total_sales']].apply(lambda x : x.sum())
    table = date_group.reset_index().groupby(['date'])[['total_pre_sales','tax_amount','deposit_amount','total_sales']].apply(lambda x : x.sum())
    for i, val in table.iterrows():
        date_group.loc[(i," Day Total","")] = val
    table = date_group.reset_index().groupby(['date','department'])[['qty','total_pre_sales','tax_amount','deposit_amount','total_sales']].apply(lambda x : x.sum())
    for i, val in table.iterrows():
        if i[1] ==  " Day Total":
            continue
        date_group.loc[(i[0],i[1]," Department Total ")] = val

    date_group.loc[("TOTAL","TOTAL"," TOTAL")] = df[['total_pre_sales','tax_amount','deposit_amount','total_sales']].apply(lambda x : x.sum())
    for i, val in df.groupby('payment_type')[['total_pre_sales','tax_amount','deposit_amount','total_sales']].apply(lambda x : x.sum()).iterrows():
         date_group.loc[("TOTAL","TOTAL",i)] = val

    date_group = date_group.sort_index()
    date_group.fillna("",inplace=True)
    date_group.rename(columns = { 'qty':'Quantity','total_pre_sales':'Total Pre_Sales','tax_amount':'Total Tax',
            'deposit_amount':'Total Deposit','total_sales':'Total Sales'}, inplace = True)
    date_group.index.names = ['Date','Department','Payment Type',]

    return render(request,"reportsRegular.html", context={
            "table_html":date_group.to_html(classes= "table table-bordered table-hover h6 text-gray-900 border-5"),
            "start_date":start_date,"end_date":end_date,"store_name":settings.STORE_NAME,
            })


@login_required(login_url="/user/login/")
def dashboard_products(request):
    context = {}
    number = 10
    today_date=datetime.now().date()
    last_30_date = datetime.now().date() - timedelta(30)
    df = pd.DataFrame(productTransaction.objects.filter(transaction_date_time__date__range = (last_30_date,today_date)).order_by('-transaction_date_time').values())
    # Empty when no sales yet (e.g. fresh deployments): show an empty
    # top-sellers section instead of bouncing the user back to the register.
    context['products_group'] = {}
    if not df.empty:
        for dept, dept_df in df.groupby('department'):
            context['products_group'][dept] = dept_df.groupby(["barcode","name"])[["qty"]].sum().reset_index().sort_values(by=["qty"],ascending=False).iloc[:number].to_dict('records')

    context['low_inventory_products'] = product.objects.all().order_by('qty').values('barcode','name','qty')[:50]
    context['number'] = number
    return render(request,"productsDashboard.html",context=context)


@login_required(login_url="/user/login/")
def dashboard_department(request):
    context ={}
    end_date=datetime.now().date()
    start_date=datetime.now().date()
    form = DateSelector(initial = {'end_date':end_date, 'start_date':start_date})
    if request.method == "POST":
        form = DateSelector(request.POST)
        if form.is_valid():
            end_date= form.cleaned_data['end_date']
            start_date= form.cleaned_data['start_date']
    df = pd.DataFrame(productTransaction.objects.filter(transaction_date_time__date__range = (start_date,end_date)).order_by('-transaction_date_time').values())
    if df.shape[0]:
        df['total_sales'] = (df['qty'] * df['sales_price']) + df['tax_amount'] + df['deposit_amount']
        df['total_pre_sales'] = df['qty'] * df['sales_price']
        sales_by_payment = df.groupby('payment_type')['total_sales'].sum()

        tableValues = [['Total QTY', 'Total Sales b4 Tax & Deposit', 'Total Tax', 'Total Deposit']+[f"Sales by {i}" for i in sales_by_payment.index.to_list()],
                            [df['qty'].sum(), df['total_pre_sales'].sum(), df['tax_amount'].sum(), df['deposit_amount'].sum() ]+sales_by_payment.to_list()]
        tableValues = [("TOTAL SALES",round(df['total_sales'].sum(),2))]+ list(zip(tableValues[0],tableValues[1]))
        table_fig = ff.create_table(tableValues, height_constant= 25,)
        table_fig.update_layout(margin = dict(b=10,t=0,l=0,r=0),height=275 ,)
        context['table_fig'] = po.plot(table_fig, auto_open=False, output_type='div',config= {'displayModeBar': False},include_plotlyjs=False)

        pie_fig = px.pie(values=sales_by_payment,names=sales_by_payment.index, color=sales_by_payment.index,
                            color_discrete_map={'CASH': "darkgreen",'EBT': "royalblue",'DEBIT/CREDIT':"darkslategray"} )
        pie_fig.update_layout(margin = dict(b=50,t=10,l=10,r=10),height=225 ,
                    title={ 'text': f"Date Period : ({start_date:%Y/%m/%d} - {end_date:%Y/%m/%d})", 'font_size':16,
                            'y':0.15, 'x':0.5,  'xanchor': 'center', 'yanchor': 'top'})
        pie_fig.update_traces(hovertemplate=None)
        context['pie_fig'] = po.plot(pie_fig, auto_open=False, output_type='div',config= {'displayModeBar': False},include_plotlyjs=False)

        sales_by_department = df.groupby(['department','payment_type'])[['qty','total_pre_sales','tax_amount','deposit_amount','total_sales']].apply(lambda x : x.sum())
        sales_by_department = sales_by_department.reset_index()

        bar_fig = px.bar(sales_by_department, x="department",  y="total_sales", color="payment_type",text_auto=True, hover_name="total_sales",
                hover_data={'qty':True,'total_pre_sales':True,'tax_amount':True,'deposit_amount':True,'total_sales':False,},
                labels={'qty':"Quantity",'payment_type':"Payment Type",'department':"Department",'total_sales':"Total Sales","total_pre_sales":"Total Sales b4 Tax & Deposit",
                        'tax_amount':"Total Tax Amount",'deposit_amount':"Total Deposit Amount"},
                color_discrete_map={  'CASH': "darkgreen",'EBT': "royalblue",'DEBIT/CREDIT':"darkslategray"})
        bar_fig.update_yaxes(title=f"Total Sales ({start_date:%Y/%m/%d} - {end_date:%Y/%m/%d})")
        bar_fig.update_layout(margin = dict(b=10,pad=0,t=10,l=10,r=10),height=500,showlegend=False)

        # df['date'] = df['transaction_date_time'].dt.date
        # date_group = df.groupby(['date','department','payment_type'])[['qty','total_pre_sales','tax_amount','deposit_amount','total_sales']].apply(lambda x : x.sum())
        # date_group = date_group.reset_index()
        # bar_fig = px.bar(date_group, x="date",  y="total_sales", facet_row="department", hover_name="total_sales", color="payment_type",
        #         hover_data={'qty':True,'total_pre_sales':True,'tax_amount':True,'deposit_amount':True,'total_sales':False,},
        #         labels={'qty':"Quantity",'payment_type':"Payment Type",'department':"Department",'total_sales':"Total Sales","total_pre_sales":"Total Sales b4 Tax & Deposit",
        #                 'tax_amount':"Total Tax Amount",'deposit_amount':"Total Deposit Amount",'date':"Date"},
        #          color_discrete_sequence=["darkgreen", "royalblue", "darkslategray"])
        # bar_fig.update_layout(margin = dict(b=10,pad=0,t=10,l=10,r=10),height=500,showlegend=False)

        context['bar_fig'] = po.plot(bar_fig, auto_open=False, output_type='div',config= {'displayModeBar': False},include_plotlyjs=False)

    context["report_link"] = f"/department_report/{start_date}/{end_date}/"
    context['form'] = form
    return render(request,"departmentDashboard.html",context=context)


BRAND = "#4e5ae8"
BRAND_SOFT = "rgba(78, 90, 232, .35)"
MONEY = "#12a46a"
CHART_FONT = dict(family="Nunito, sans-serif", size=12, color="#5f6383")
PIE_COLORS = ["#4e5ae8", "#12a46a", "#f6c23e", "#36b9cc", "#e0475b"]


def _plot_div(fig):
    return po.plot(fig, auto_open=False, output_type='div',
                   config={'displayModeBar': False, 'responsive': True}, include_plotlyjs=False)


def _style(fig, height):
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=10, b=0), font=CHART_FONT,
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(bgcolor="#1f2340", font_color="#fff", bordercolor="#1f2340"),
                      showlegend=False, bargap=0.25)
    fig.update_xaxes(showgrid=False, title=None, linecolor="#e6e8f2")
    fig.update_yaxes(gridcolor="#eef0f6", zeroline=False, title=None, tickprefix="Rs ", separatethousands=True)
    return fig


def _pct_change(now, before):
    if not before:
        return None
    return round((now - before) / before * 100, 1)


@login_required(login_url="/user/login/")
def dashboard_sales(request):
    today = datetime.now(timezone).date()
    year_start = today.replace(month=1, day=1)
    window_start = min(year_start, today - timedelta(days=29))

    df = pd.DataFrame(transaction.objects
        .filter(transaction_dt__date__gte=window_start - timedelta(days=7))
        .values('transaction_id', 'transaction_dt', 'total_sale', 'payment_type', 'user__username'))
    if df.empty:
        df = pd.DataFrame(columns=['transaction_id', 'transaction_dt', 'total_sale', 'payment_type', 'user__username'])
    df['total_sale'] = df['total_sale'].astype(float)
    df['transaction_dt'] = pd.to_datetime(df['transaction_dt'], utc=True).dt.tz_convert(timezone)
    df['date'] = df['transaction_dt'].dt.date

    daily = df.groupby('date')['total_sale'].sum()
    daily.index = pd.to_datetime(daily.index)
    daily = daily.reindex(pd.date_range(window_start - timedelta(days=7), today, freq='D'), fill_value=0.0)

    def total(start, end):
        return float(daily[(daily.index.date >= start) & (daily.index.date <= end)].sum())

    week_start = today - timedelta(days=today.weekday())          # Monday
    last_week_start = week_start - timedelta(days=7)
    yesterday = today - timedelta(days=1)

    today_df = df[df['date'] == today]
    today_sales = float(today_df['total_sale'].sum())
    today_count = int(len(today_df))
    yesterday_sales = total(yesterday, yesterday)
    # Same weekday-to-date comparison for week / month over the prior period.
    wtd = total(week_start, today)
    last_wtd = total(last_week_start, last_week_start + (today - week_start))

    context = {
        'today_sales': today_sales,
        'today_count': today_count,
        'today_avg': today_sales / today_count if today_count else 0,
        'today_change': _pct_change(today_sales, yesterday_sales),
        'periods': [
            ("Yesterday", yesterday_sales, "fa-calendar-day"),
            ("Last 7 days", total(today - timedelta(days=6), today), "fa-calendar-week"),
            ("This week", wtd, "fa-chart-line"),
            ("Last week", total(last_week_start, week_start - timedelta(days=1)), "fa-history"),
            ("This month", total(today.replace(day=1), today), "fa-calendar-alt"),
            ("This year", total(year_start, today), "fa-trophy"),
        ],
        'wtd_change': _pct_change(wtd, last_wtd),
    }

    # --- last 30 days -------------------------------------------------------
    last30 = daily[daily.index.date > today - timedelta(days=30)]
    context['total_30'] = float(last30.sum())
    context['avg_30'] = float(last30.mean()) if len(last30) else 0
    context['best_day'] = (last30.idxmax().date(), float(last30.max())) if last30.max() > 0 else None
    colors = [MONEY if d.date() == today else BRAND for d in last30.index]
    # One category per day so all 30 days get their own slot and label.
    labels = [d.strftime('%d %b') for d in last30.index]
    tick_text = [f"<b>{l}</b>" if d.date() == today else l for l, d in zip(labels, last30.index)]
    fig = go.Figure(go.Bar(
        x=labels, y=last30.values, marker_color=colors, marker_line_width=0,
        customdata=[d.strftime('%a, %d %b') for d in last30.index],
        hovertemplate="<b>%{customdata}</b><br>Rs %{y:,.2f}<extra></extra>"))
    if context['avg_30']:
        fig.add_hline(y=context['avg_30'], line_dash="dot", line_color="#9a9db8", line_width=1,
                      annotation_text=f"avg {context['avg_30']:,.0f}", annotation_position="top left",
                      annotation_font=dict(size=11, color="#9a9db8"))
    _style(fig, 330)
    fig.update_xaxes(type="category", tickmode="array", tickvals=labels, ticktext=tick_text,
                     tickangle=-45, tickfont=dict(size=11))
    context['sales_30_graph'] = _plot_div(fig)

    # --- today: by hour + payment mix --------------------------------------
    hours = list(range(24))
    by_hour = today_df.groupby(today_df['transaction_dt'].dt.hour)['total_sale'].sum().reindex(hours, fill_value=0.0)
    first = next((h for h in hours if by_hour[h] > 0), 9)
    last = max([h for h in hours if by_hour[h] > 0] or [21])
    shown = list(range(min(first, 9), max(last, 21) + 1))
    fig_h = go.Figure(go.Bar(
        x=[f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}" for h in shown], y=[by_hour[h] for h in shown],
        marker_color=BRAND, marker_line_width=0,
        hovertemplate="<b>%{x}</b><br>Rs %{y:,.2f}<extra></extra>"))
    _style(fig_h, 230)
    context['hourly_graph'] = _plot_div(fig_h)

    pay = today_df.groupby('payment_type')['total_sale'].sum()
    context['payment_mix'] = [(k, float(v), float(v) / today_sales * 100 if today_sales else 0,
                               PIE_COLORS[i % len(PIE_COLORS)]) for i, (k, v) in enumerate(pay.items())]
    if len(pay):
        fig_p = go.Figure(go.Pie(
            labels=list(pay.index), values=list(pay.values), hole=.68, sort=False,
            marker=dict(colors=PIE_COLORS[:len(pay)], line=dict(color="#fff", width=2)),
            textinfo="none", hovertemplate="<b>%{label}</b><br>Rs %{value:,.2f} (%{percent})<extra></extra>"))
        _style(fig_p, 200)
        context['payment_graph'] = _plot_div(fig_p)

    recent = df.sort_values('transaction_dt', ascending=False).head(6).to_dict('records')
    for r in recent:
        # naive local time so the template's |date doesn't re-convert it
        r['transaction_dt'] = r['transaction_dt'].tz_localize(None).to_pydatetime()
    context['recent'] = recent
    return render(request, "salesDashboard.html", context=context)


def user_login(request):
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()},
                                           require_https=request.is_secure()):
        next_url = ''
    context = {"store_name": settings.STORE_NAME, "next": next_url}
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            request.session["Total"] = 0.00
            request.session["Tax_Total"] = 0.00
            return redirect(next_url or 'home')
        context.update(error=True, username=username)
    return render(request, 'registration/login.html', context=context)


@login_required(login_url="/user/login/")
def user_logout(request):
    logout(request)
    return render(request, 'registration/login.html',
                  context={'logout': True, "store_name": settings.STORE_NAME})

