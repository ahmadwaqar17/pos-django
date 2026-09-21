from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup, name="stores_signup"),
    # Platform (super admin) area
    path("platform/", views.platform_dashboard, name="platform_dashboard"),
    path("platform/stores/add/", views.platform_add_store, name="platform_add_store"),
    path("platform/stores/<int:store_id>/", views.platform_store_detail, name="platform_store_detail"),
    path("platform/stores/<int:store_id>/users/", views.platform_store_users, name="platform_store_users"),
    path("platform/stores/<int:store_id>/toggle/", views.platform_toggle_store, name="platform_toggle_store"),
    path("platform/stores/<int:store_id>/users/<int:membership_id>/remove/", views.platform_remove_user, name="platform_remove_user"),
]
