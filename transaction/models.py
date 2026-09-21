# from itertools import product
from django.db import models
from django.conf import settings
from django.db.models import F
from inventory.models import product, PERCENTAGE_VALIDATOR
from stores.managers import StoreScopedManager
import pytz
timezone = pytz.timezone("US/Eastern")


# Create your models here.transaction_dt
class transaction(models.Model):
    objects = StoreScopedManager()
    all_objects = models.Manager()
    store           = models.ForeignKey("stores.store",on_delete=models.RESTRICT,null=False,blank=False)
    date_time       = models.DateTimeField(auto_now_add=True)
    transaction_dt  = models.DateTimeField(editable=False, null=False, blank=False,)
    user            = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, null=False, blank=False,editable=False,)
    transaction_id  = models.CharField(max_length=50, editable=False,null=False)
    total_sale      = models.DecimalField(max_digits=7,decimal_places=2,null=False,editable=False)
    sub_total       = models.DecimalField(max_digits=7,decimal_places=2,null=False,editable=False)
    tax_total       = models.DecimalField(max_digits=7,decimal_places=2,null=True,editable=False)
    deposit_total   = models.DecimalField(max_digits=7,decimal_places=2,null=True,editable=False)
    payment_type    = models.CharField(choices=[('CASH','CASH'),('DEBIT/CREDIT','DEBIT/CREDIT'),('EBT','EBT')],max_length=32, null=False,editable=False)
    receipt         = models.TextField(blank=False,null=False,editable=False)
    products        = models.TextField(blank=False,null=False,editable=False)

    def __str__(self) -> str:
        return self.transaction_id

    def save(self,*args,**kwargs):
        # SaaS: use the store's timezone when it exists, fall back to the old default
        tz = pytz.timezone(self.store.timezone) if self.store and self.store.timezone else timezone
        self.transaction_dt = tz.localize(self.transaction_dt)
        super().save(*args, **kwargs)
        for product_item in eval(self.products):
            try: item = product.objects.get(barcode = product_item['barcode'])
            except: item = product.objects.get(barcode = product_item['barcode'].split("_")[0])
            productTransaction.objects.create(transaction = self, transaction_id_num = self.transaction_id, transaction_date_time = self.transaction_dt,
                store = self.store,
                barcode = product_item['barcode'], name = product_item['name'], department = item.department.department_name, sales_price= product_item['price'],
                qty = product_item['quantity'], cost_price = item.cost_price, tax_category = item.tax_category.tax_category,tax_percentage= item.tax_category.tax_percentage ,
                tax_amount = product_item['tax_value'], deposit_category = item.deposit_category.deposit_category,deposit = item.deposit_category.deposit_value ,
                deposit_amount = product_item['deposit_value'], payment_type= self.payment_type )
        return self

    class Meta:
        verbose_name_plural = "Transactions"
        constraints = [
            models.UniqueConstraint(fields=["store","transaction_id"],name="uniq_transaction_id_per_store"),
        ]


class productTransaction(models.Model):
    objects = StoreScopedManager()
    all_objects = models.Manager()
    store                   = models.ForeignKey("stores.store",on_delete=models.RESTRICT,null=False,blank=False)
    transaction             = models.ForeignKey("transaction", on_delete=models.RESTRICT, null=False, blank=False,editable=False,)
    transaction_id_num      = models.CharField(max_length=50, editable=False,null=False)
    transaction_date_time   = models.DateTimeField(editable=False, null=False, blank=False,)
    barcode                 = models.CharField(max_length=32, editable=False, blank = False, null=False)
    name                    = models.CharField(max_length=125, editable=False, blank = False, null = False)
    department              = models.CharField(max_length=125, editable=False,blank = False, null = True)
    sales_price             = models.DecimalField(max_digits=7, editable=False,decimal_places=2,null=False,blank = False)
    qty                     = models.IntegerField(default=0, editable=False, null=True)
    cost_price              = models.DecimalField(max_digits=7,decimal_places=2,editable=False, default=0,null=True)
    tax_category            = models.CharField(max_length=125, editable=False,blank = False, null = False)
    tax_percentage          = models.DecimalField(max_digits=6, decimal_places=3, validators=PERCENTAGE_VALIDATOR,null=False,blank=False)
    tax_amount              = models.DecimalField(max_digits=7,decimal_places=2,editable=False, default=0,null=True)
    deposit_category        = models.CharField(max_length=125, editable=False, blank = False, null = False)
    deposit                 = models.DecimalField(max_digits=7,decimal_places=2,null=False,blank=False)
    deposit_amount          = models.DecimalField(max_digits=7,decimal_places=2,editable=False, default=0,null=True)
    payment_type            = models.CharField(max_length=32, null=False,editable=False)

    def save(self,*args,**kwargs):
        if product.objects.filter(barcode=self.barcode).exists():
            product.objects.filter(barcode=self.barcode).update(qty= F('qty')-self.qty)
        return super().save(*args, **kwargs)
    
    def __str__(self) -> str:
        return self.transaction_id_num + "_"+ self.barcode

    class Meta:
        verbose_name_plural = "Product Transactions"