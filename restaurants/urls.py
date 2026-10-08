from django.urls import path

from . import views

app_name = "restaurants"
urlpatterns = [
    path("", views.restaurant_list, name="list"),
    path("restaurant/<int:pk>/", views.restaurant_detail, name="detail"),
    path("location/", views.set_location, name="set_location"),
    path("location/clear/", views.clear_location, name="clear_location"),
    path("vendor/", views.vendor_dashboard, name="vendor_dashboard"),
    path("vendor/items/new/", views.item_form, name="item_create"),
    path("vendor/items/<int:pk>/edit/", views.item_form, name="item_edit"),
    path("vendor/items/<int:pk>/delete/", views.item_delete, name="item_delete"),
    path("vendor/orders/<int:pk>/status/", views.order_status, name="order_status"),
]
