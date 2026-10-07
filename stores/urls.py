from django.urls import path

from . import views

urlpatterns = [
    path("branch/switch/", views.switch_store, name="switch_store"),
    path("stock/", views.stock_levels, name="stock_levels"),
    path("stock/transfers/", views.transfer_list, name="transfer_list"),
    path("stock/transfers/new/", views.transfer_new, name="transfer_new"),
    path("stock/transfers/<int:pk>/", views.transfer_detail, name="transfer_detail"),
    path("stock/movements/", views.movement_list, name="movement_list"),
    path("stock/api/search/", views.stock_search, name="stock_search"),
]
