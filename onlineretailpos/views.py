from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django import forms
from django.db.models import Q
from cart.models import Cart, displayed_items
from inventory.models import product, department
from transaction.models import productTransaction, transaction
from transaction.views import DateSelector
from plotly import express as px
from plotly import offline as po
import plotly.figure_factory as ff
from datetime import datetime, timedelta
import pandas as pd
import pytz, os, shutil
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
        Total = round(pd.DataFrame(cart).T["line_total"].astype(float).sum(),2)
        Tax_Total = round(pd.DataFrame(cart).T["tax_value"].astype(float).sum(),2)
    except KeyError:
        cart = Cart(request)
        Total = 0
        Tax_Total = 0
    
    all_products = product.objects.select_related('department').all()
    departments = department.objects.all()

    context = {
        'form':form,
        'no_product':  True if "ProductNotFound" in request.path else False,
        'cart':cart,
        'total':Total,
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
        cart = request.session.get(settings.CART_SESSION_ID, {})
        items = []
        for key, value in cart.items():
            try:
                items.append({
                    'id': key,
                    'name': value['name'],
                    'qty': int(value['quantity']),
                    'price': float(value['price']),
                })
            except Exception:
                continue

        path = "images4display/"
        if os.path.exists(f"./{path}"):
            shutil.copytree(f"./{path}", f"{settings.STATIC_ROOT}/{path}", dirs_exist_ok=True)
        img_list = [ path+i for i in  os.listdir(path) if i.lower().endswith(('.jpg','.jpeg','.png','.webp','.gif'))] if os.path.exists(f"./{path}") else []
        promo_img = f"{settings.STATIC_URL}{img_list[0]}" if img_list else None

        return JsonResponse({
            'store': settings.STORE_NAME,
            'currency': 'PKR',
            'items': items,
            'discount': 0,
            'promo': {
                'kicker': "Today at the counter",
                'title': "Special Offers",
                'price': "",
                'was': "",
                'flag': "OFFERS",
                'terms': "Ask the cashier for today's deals.",
                'image': promo_img,
            },
        })

    path="images4display/"  # insert the path to your directory   
    if os.path.exists(f"./{path}"):
        shutil.copytree(f"./{path}", f"{settings.STATIC_ROOT}/{path}", dirs_exist_ok=True)
    # images4display/ is gitignored and absent on deployments: serve the
    # display page without promo images instead of crashing on listdir.
    img_list = [ path+i for i in  os.listdir(path) if not i.endswith('.md')] if os.path.exists(f"./{path}") else []
    
    return render(request,'retailDisplay.html',context={"store_name":settings.STORE_NAME, "display_images":img_list})


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


@login_required(login_url="/user/login/")
def dashboard_sales(request):
    context = {}
    today_date =  datetime.combine(datetime.now().date(), datetime.min.time())
    df = pd.DataFrame(transaction.objects.filter(transaction_dt__date__gte = datetime(today_date.year, 1,1)).values())
    # No sales yet (fresh/read-only deployments): render the dashboard with
    # zeroed stats and an empty chart instead of redirecting to the register.
    if df.empty:
        empty_fig = px.bar(pd.DataFrame({'Date': [], 'Total Sales': []}), x='Date', y='Total Sales', template="plotly_white")
        empty_fig.update_xaxes(title="Days")
        empty_fig.update_yaxes(title="Total Sales")
        empty_fig.update_layout(margin = dict(b=10,pad=0,t=10,r=0,l=0), )
        context['30_day_sales_graph'] = po.plot(empty_fig, auto_open=False, output_type='div',config= {'displayModeBar': False},include_plotlyjs=False)
        context['day_payment_graph'] = ""
        context['today_total_sales'] = 0
        context['30_Days_Avg_Sales'] = 0
        context['30_Days_Total_Sales'] = 0
        context["add_info"] = {key: 0 for key in (
            "Yesterday's Total Sales", "Last 7 Days Avg Sales", "WTD Total Sales",
            "Last Week Total Sales", "MTD Total Sales", "YTD Total Sales")}
        return render(request,"salesDashboard.html",context=context)

    df['transaction_dt'] = df['transaction_dt'].apply(lambda x: x.astimezone(timezone) )
    df['date'] = df['transaction_dt'].dt.date
    df_date = df.groupby('date')['total_sale'].sum()
    df_date.index = pd.to_datetime(df_date.index)
    if not df_date.get(datetime(today_date.year, 1,1)):df_date[datetime(today_date.year, 1,1)] = 0
    if not df_date.get(today_date): df_date[today_date] = 0
    df_date = df_date.asfreq('D',fill_value=0)

    context['today_total_sales'] = df_date.get(today_date)
    context["add_info"] = {}
    context["add_info"]['Yesterday\'s Total Sales'] = df_date.get(today_date-timedelta(1))
    context["add_info"]['Last 7 Days Avg Sales'] = df_date[df_date.index>today_date-timedelta(7)].sum()/7
    context['30_Days_Avg_Sales'] = df_date[df_date.index>today_date-timedelta(30)].mean()
    context['30_Days_Total_Sales'] = df_date[df_date.index>today_date-timedelta(30)].sum()
    context["add_info"]['WTD Total Sales'] = df_date.resample('W').sum()[-1]
    context["add_info"]['Last Week Total Sales'] = df_date.resample('W').sum()[-2]
    context["add_info"]['MTD Total Sales'] = df_date.resample('M').sum()[-1]
    context["add_info"]['YTD Total Sales'] = df_date.resample('Y').sum()[-1]

    fig = px.bar(x= df_date.index,  y=df_date,text_auto=True,barmode='group',template="plotly_white" ,labels={"x":"Date","y":"Total Sales"})
    fig.update_xaxes(title="Days", tickformat = '%a,%d/%m',tickangle=-90)
    fig.update_yaxes(title="Total Sales")
    fig.update_layout( margin = dict(b=10,pad=0,t=10,r=0,l=0), )
    div = po.plot(fig, auto_open=False, output_type='div',config= {'displayModeBar': False},include_plotlyjs=False)
    context['30_day_sales_graph'] = div

    df_day_payment = df[df['date'] == today_date.date() ].groupby('payment_type')['total_sale'].sum().reset_index()
    fig2 = px.pie(df_day_payment,values='total_sale',names='payment_type',template="plotly_white",height=195 ,
        labels={"payment_type":"Payment Type","total_sale":"Total Sales"})
    fig2.update_layout( margin = dict(b=10,pad=0,t=10), )
    context['day_payment_graph'] = po.plot(fig2, auto_open=False, output_type='div',config= {'displayModeBar': False},include_plotlyjs=False)
    return render(request,"salesDashboard.html",context=context)


def user_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            request.session["Total"] = 0.00
            request.session["Tax_Total"] = 0.00
            return redirect('home')
        else:
            return render(request, 'registration/login.html',context={'error':True,"store_name":settings.STORE_NAME})
    else:
        return render(request, 'registration/login.html',context={"store_name":settings.STORE_NAME},)


@login_required(login_url="/user/login/")
def user_logout(request):
    logout(request)
    return render(request, 'registration/login.html',context={'logout':True})

