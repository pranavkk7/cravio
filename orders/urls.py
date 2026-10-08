from django.urls import path

from . import views

app_name = "orders"
urlpatterns = [
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/<int:item_id>/", views.add_to_cart, name="add"),
    path("cart/update/<int:item_id>/", views.update_cart, name="update"),
    path("cart/remove/<int:item_id>/", views.remove_from_cart, name="remove"),
    path("checkout/", views.checkout, name="checkout"),
    path("orders/<int:pk>/pay/", views.pay, name="pay"),
    path("orders/<int:pk>/callback/", views.payment_callback, name="callback"),
    path("orders/", views.history, name="history"),
]
