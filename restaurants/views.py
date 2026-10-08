from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Exists, Min, OuterRef, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import User
from orders.cart import Cart
from orders.models import Order
from orders.views import redirect_back

from . import location
from .forms import MenuItemForm, RestaurantForm
from .models import MenuItem, Restaurant


def add_delivery_info(restaurant, loc):
    """Distance, delivery window and range for one restaurant, as seen from the customer's location."""
    restaurant.distance = restaurant.distance_to(loc)
    restaurant.in_range = restaurant.delivers_to(loc)
    restaurant.eta = (
        location.delivery_minutes(restaurant.distance, restaurant.prep_minutes) if restaurant.in_range else None
    )
    return restaurant


def restaurant_list(request):
    loc = location.get_location(request.session)
    available = Q(items__is_available=True)
    restaurants = Restaurant.objects.filter(is_open=True).annotate(
        item_count=Count("items", filter=available),
        min_price=Min("items__price", filter=available),
    )

    query = request.GET.get("q", "").strip()
    if query:
        # A subquery (not a join) for dish names, so the counts above stay correct.
        dish_match = MenuItem.objects.filter(restaurant=OuterRef("pk"), is_available=True, name__icontains=query)
        restaurants = restaurants.filter(
            Q(name__icontains=query) | Q(cuisine__icontains=query) | Q(description__icontains=query) | Exists(dish_match)
        )

    # The city tab: chosen explicitly, otherwise the city of the customer's location, otherwise all cities.
    city_key = request.GET.get("city", loc["city"] if loc and loc["city"] else "all")
    city = location.CITY_BY_KEY.get(city_key)
    if city:
        restaurants = restaurants.filter(area__in=[area.key for area in city.areas])

    restaurants = [add_delivery_info(r, loc) for r in restaurants.order_by("name")]
    if not loc:
        # City by city, so the outlets of one chain are not all listed side by side.
        city_order = {c.key: i for i, c in enumerate(location.CITIES)}
        restaurants.sort(key=lambda r: city_order.get(r.city.key, len(city_order)) if r.city else len(city_order))
    else:
        # Places that deliver come first, nearest first; then the rest by distance.
        far_away = float("inf")
        restaurants.sort(key=lambda r: (not r.in_range, r.distance if r.distance is not None else far_away))

    map_points = [
        {"name": r.name, "area": r.area_name, "lat": r.latitude, "lng": r.longitude,
         "url": r.get_absolute_url(), "inRange": r.in_range}
        for r in restaurants if r.has_position
    ]
    return render(request, "restaurants/list.html", {
        "restaurants": restaurants,
        "query": query,
        "cities": location.CITIES,
        "city": city,
        "location": loc,
        "nearby_count": sum(r.in_range for r in restaurants),
        "map_data": {"restaurants": map_points, "me": loc},
    })


def restaurant_detail(request, pk):
    restaurant = add_delivery_info(get_object_or_404(Restaurant, pk=pk), location.get_location(request.session))
    cart = Cart(request.session)
    items = list(restaurant.items.filter(is_available=True))
    # Menu sections in the order they first appear, so a vendor's newest section goes last.
    sections = {}
    for item in items:
        item.in_cart = cart.quantity(item.pk)
        sections.setdefault(item.category or "Menu", []).append(item)
    return render(request, "restaurants/detail.html", {
        "restaurant": restaurant,
        "items": items,
        "sections": sections.items(),
        "location": location.get_location(request.session),
        # The sticky cart bar only shows when the cart belongs to this restaurant.
        "cart_here": cart.data["restaurant"] == restaurant.pk,
        "cart_total": cart.total(),
    })


@require_POST
def set_location(request):
    """Saves the delivery location from an area picked in the list, or from the browser's geolocation."""
    city, area = location.find_area(request.POST.get("area", ""))
    if area:
        location.set_location(request.session, area.lat, area.lng, f"{area.name}, {city.name}")
    else:
        coordinates = location.parse_coordinates(request.POST.get("lat"), request.POST.get("lng"))
        if coordinates is None:
            messages.error(request, "We could not read that location. Please pick your area instead.")
            return redirect_back(request, "restaurants:list")
        lat, lng = coordinates
        city = location.nearest_city(lat, lng)
        if city:
            nearest = min(city.areas, key=lambda a: location.distance_km(lat, lng, a.lat, a.lng))
            label = f"Near {nearest.name}, {city.name}"
        else:
            label = "Your current location"
        loc = location.set_location(request.session, lat, lng, label)
        if loc["city"] is None:
            messages.error(request, "Cravio does not deliver to your area yet. We serve Kozhikode, Kannur and Bengaluru.")
            return redirect_back(request, "restaurants:list")
    messages.success(request, f"Delivering to {location.get_location(request.session)['label']}.")
    return redirect_back(request, "restaurants:list")


@require_POST
def clear_location(request):
    location.clear_location(request.session)
    return redirect_back(request, "restaurants:list")


@role_required(User.Role.VENDOR)
def vendor_dashboard(request):
    restaurant = Restaurant.objects.filter(owner=request.user).first()
    if restaurant is None:
        form = RestaurantForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            form.instance.owner = request.user
            form.save()
            messages.success(request, "Restaurant created. Add your first menu item.")
            return redirect("restaurants:vendor_dashboard")
        return render(request, "restaurants/vendor_setup.html", {"form": form})

    orders = Order.objects.filter(restaurant=restaurant).select_related("customer").prefetch_related("lines")
    paid_orders = orders.exclude(status=Order.Status.PENDING_PAYMENT)
    stats = {
        "items": restaurant.items.count(),
        "orders": paid_orders.count(),
        "to_prepare": orders.filter(status__in=[Order.Status.PAID, Order.Status.PREPARING]).count(),
        "revenue": paid_orders.aggregate(total=Sum("total"))["total"] or Decimal("0"),
    }
    return render(request, "restaurants/vendor_dashboard.html", {
        "restaurant": restaurant,
        "items": restaurant.items.all(),
        "orders": orders,
        "statuses": [(value.value, value.label) for value in VENDOR_STATUSES],
        "stats": stats,
    })


@role_required(User.Role.VENDOR)
def item_form(request, pk=None):
    restaurant = get_object_or_404(Restaurant, owner=request.user)
    # Scoping the lookup to the vendor's own restaurant stops vendors editing each other's menus.
    item = get_object_or_404(MenuItem, pk=pk, restaurant=restaurant) if pk else None
    form = MenuItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.instance.restaurant = restaurant
        form.save()
        messages.success(request, "Menu item saved.")
        return redirect("restaurants:vendor_dashboard")
    return render(request, "restaurants/item_form.html", {"form": form, "item": item})


@role_required(User.Role.VENDOR)
def item_delete(request, pk):
    item = get_object_or_404(MenuItem, pk=pk, restaurant__owner=request.user)
    if request.method == "POST":
        item.delete()
        messages.success(request, "Menu item deleted.")
        return redirect("restaurants:vendor_dashboard")
    return render(request, "restaurants/item_confirm_delete.html", {"item": item})


# What a vendor may set once the customer has paid. "Pending payment" is never a vendor's choice.
VENDOR_STATUSES = [Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED]


@role_required(User.Role.VENDOR)
def order_status(request, pk):
    order = get_object_or_404(Order, pk=pk, restaurant__owner=request.user)
    new_status = request.POST.get("status")
    if request.method == "POST":
        if order.status == Order.Status.PENDING_PAYMENT:
            # Only a verified payment can move an order out of "pending payment".
            messages.error(request, f"Order #{order.pk} has not been paid yet.")
        elif new_status in VENDOR_STATUSES:
            order.status = new_status
            order.save(update_fields=["status"])
            messages.success(request, f"Order #{order.pk} marked as {order.get_status_display().lower()}.")
    return redirect("restaurants:vendor_dashboard")
