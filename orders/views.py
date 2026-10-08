from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import User
from restaurants import location
from restaurants.models import MenuItem, Restaurant

from . import payments
from .cart import Cart, add_item
from .models import Order, OrderLine


@require_POST
def add_to_cart(request, item_id):
    item = get_object_or_404(MenuItem, pk=item_id, is_available=True)
    error = add_item(request.session, item)
    if error:
        messages.error(request, error)
    else:
        messages.success(request, f"Added {item.name} to your cart.")
    return redirect("restaurants:detail", pk=item.restaurant_id)


@require_POST
def remove_from_cart(request, item_id):
    Cart(request.session).remove(item_id)
    return redirect("orders:cart")


def redirect_back(request, fallback):
    """Returns to the page named in the form's "next" field, but only if it is a path on this site."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(target)
    return redirect(fallback)


@require_POST
def update_cart(request, item_id):
    """Plus and minus buttons. Anything other than "inc" counts as a decrease."""
    delta = 1 if request.POST.get("action") == "inc" else -1
    Cart(request.session).change(item_id, delta)
    return redirect_back(request, "orders:cart")


def cart_view(request):
    cart = Cart(request.session)
    loc = location.get_location(request.session)
    restaurant = Restaurant.objects.filter(pk=cart.data["restaurant"]).first()
    distance = restaurant.distance_to(loc) if restaurant else None
    in_range = bool(restaurant and restaurant.delivers_to(loc))
    return render(request, "orders/cart.html", {
        "lines": cart.lines(),
        "total": cart.total(),
        "restaurant": restaurant,
        "location": loc,
        "distance": distance,
        "in_range": in_range,
        "eta": location.delivery_minutes(distance, restaurant.prep_minutes) if in_range else None,
    })


@role_required(User.Role.CUSTOMER)
@require_POST
def checkout(request):
    cart = Cart(request.session)
    lines = cart.lines()
    if not lines:
        messages.error(request, "Your cart is empty.")
        return redirect("orders:cart")

    # The delivery location is checked again here; the cart page alone is not trusted.
    restaurant = get_object_or_404(Restaurant, pk=cart.data["restaurant"])
    loc = location.get_location(request.session)
    if loc.get("is_default"):
        # Kannur is only the starting view for browsing; a real order needs the customer's own location.
        messages.error(request, "Set your delivery location before checking out.")
        return redirect("orders:cart")
    if not restaurant.delivers_to(loc):
        messages.error(request, f"{restaurant.name} does not deliver to {loc['label']}.")
        return redirect("orders:cart")

    with transaction.atomic():
        order = Order.objects.create(
            customer=request.user,
            restaurant=restaurant,
            total=cart.total(),
        )
        OrderLine.objects.bulk_create([
            OrderLine(order=order, item=l["item"], name=l["item"].name,
                      unit_price=l["item"].price, quantity=l["quantity"])
            for l in lines
        ])
        if payments.razorpay_enabled():
            order.razorpay_order_id = payments.create_payment_order(order)
            order.save(update_fields=["razorpay_order_id"])
    cart.clear()
    return redirect("orders:pay", pk=order.pk)


@role_required(User.Role.CUSTOMER)
def pay(request, pk):
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    if order.status != Order.Status.PENDING_PAYMENT:
        return redirect("orders:history")
    return render(request, "orders/pay.html", {
        "order": order,
        "razorpay_enabled": payments.razorpay_enabled(),
        "razorpay_key": settings.RAZORPAY_KEY_ID,
    })


@role_required(User.Role.CUSTOMER)
@require_POST
def payment_callback(request, pk):
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    if order.status != Order.Status.PENDING_PAYMENT:
        return redirect("orders:history")
    if payments.razorpay_enabled():
        ok = payments.verify_payment(
            order.razorpay_order_id,
            request.POST.get("razorpay_payment_id", ""),
            request.POST.get("razorpay_signature", ""),
        )
        if not ok:
            return HttpResponseBadRequest("Payment verification failed.")
        order.razorpay_payment_id = request.POST["razorpay_payment_id"]
    else:
        order.razorpay_payment_id = "simulated"  # demo mode, no real money involved
    order.status = Order.Status.PAID
    order.save(update_fields=["status", "razorpay_payment_id"])
    messages.success(request, f"Payment received for order #{order.pk}. Thank you!")
    return redirect("orders:history")


@role_required(User.Role.CUSTOMER)
def history(request):
    orders = request.user.orders.select_related("restaurant").prefetch_related("lines")
    return render(request, "orders/history.html", {"orders": orders})
