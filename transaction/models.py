# from itertools import product
from django.db import models, transaction as db_transaction
from django.conf import settings
from inventory.models import product, PERCENTAGE_VALIDATOR
import pytz
timezone = pytz.timezone("US/Eastern")


# Create your models here.transaction_dt
class transaction(models.Model):
    date_time       = models.DateTimeField(auto_now_add=True)
    transaction_dt  = models.DateTimeField(editable=False, null=False, blank=False,)
    user            = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, null=False, blank=False,editable=False,)
    store           = models.ForeignKey("stores.Store", on_delete=models.PROTECT, related_name="sales", editable=False)
    transaction_id  = models.CharField(unique=True, max_length=50, editable=False,null=False)
    total_sale      = models.DecimalField(max_digits=7,decimal_places=2,null=False,editable=False)
    sub_total       = models.DecimalField(max_digits=7,decimal_places=2,null=False,editable=False)
    tax_total       = models.DecimalField(max_digits=7,decimal_places=2,null=True,editable=False)
    deposit_total   = models.DecimalField(max_digits=7,decimal_places=2,null=True,editable=False)
    payment_type    = models.CharField(choices=[('CASH','CASH'),('DEBIT/CREDIT','DEBIT/CREDIT'),('EBT','EBT')],max_length=32, null=False,editable=False)
    discount_percent = models.DecimalField(max_digits=5,decimal_places=2,null=True,blank=True,editable=False,default=None)
    discount_amount = models.DecimalField(max_digits=7,decimal_places=2,null=True,blank=True,editable=False,default=None)
    receipt         = models.TextField(blank=False,null=False,editable=False)
    products        = models.TextField(blank=False,null=False,editable=False)

    def __str__(self) -> str:
        return self.transaction_id

    def save(self,*args,**kwargs):
        # Imported here: stores.stock imports models that reference this one.
        from stores import stock
        from stores.models import StockMovement

        creating = self._state.adding
        if creating:
            self.transaction_dt = timezone.localize(self.transaction_dt)
        with db_transaction.atomic():
            super().save(*args, **kwargs)
            if not creating:
                return self
            for product_item in eval(self.products):
                try: item = product.objects.get(barcode = product_item['barcode'])
                except: item = product.objects.get(barcode = product_item['barcode'].split("_")[0])
                line = productTransaction.objects.create(transaction = self, store = self.store, transaction_id_num = self.transaction_id, transaction_date_time = self.transaction_dt,
                    barcode = product_item['barcode'], name = product_item['name'], department = item.department.department_name, sales_price= product_item['price'],
                    qty = product_item['quantity'], cost_price = item.cost_price, tax_category = item.tax_category.tax_category,tax_percentage= item.tax_category.tax_percentage ,
                    tax_amount = product_item['tax_value'], deposit_category = item.deposit_category.deposit_category,deposit = item.deposit_category.deposit_value ,
                    deposit_amount = product_item['deposit_value'], payment_type= self.payment_type )
                # Variable-price items (barcode "<dept>_<amount>") are not stocked.
                if item.barcode == line.barcode and line.qty:
                    stock.adjust(self.store, item, -line.qty,
                                 StockMovement.RETURN if line.qty < 0 else StockMovement.SALE,
                                 user=self.user, sale=self)
        return self

    class Meta:
        verbose_name_plural = "Transactions"


class productTransaction(models.Model):
    transaction             = models.ForeignKey("transaction", on_delete=models.RESTRICT, null=False, blank=False,editable=False,)
    store                   = models.ForeignKey("stores.Store", on_delete=models.PROTECT, related_name="sale_lines", editable=False)
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

    def __str__(self) -> str:
        return self.transaction_id_num + "_"+ self.barcode

    class Meta:
        verbose_name_plural = "Product Transactions"