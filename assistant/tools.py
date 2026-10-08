"""The tools Claude may call. Each one is a normal Python function over the same data and rules as the
website, so the assistant can never do something a customer could not do with the buttons.

Claude only sees the tool names, descriptions and input schemas below. It never touches the database:
it asks for a tool, this code runs it for the current visitor, and the result goes back as JSON.
"""
import json

from django.db.models import Q

from orders.cart import Cart, add_item
from restaurants import location
from restaurants.models import MenuItem, Restaurant
from restaurants.views import add_delivery_info

MAX_RESULTS = 15
MAX_QUANTITY_PER_CALL = 10

TOOLS = [
    {
        "name": "list_restaurants",
        "description": (
            "List open Cravio restaurants. When the customer has set a delivery location, only restaurants that "
            "deliver to them are listed, nearest first, with distance and delivery time. Use it to answer "
            "'what is near me' or before recommending a place."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_menu",
        "description": "The full menu of one restaurant: every available dish with its id, section, price and veg flag.",
        "input_schema": {
            "type": "object",
            "properties": {"restaurant_id": {"type": "integer", "description": "The id from list_restaurants."}},
            "required": ["restaurant_id"],
        },
    },
    {
        "name": "search_dishes",
        "description": (
            "Search dishes across restaurants by words in the dish name, description, menu section, cuisine or "
            "restaurant name, for example 'biryani', 'mandi', 'kunafa' or 'fish'. Only dishes that can be "
            "delivered to the customer are returned. Use one or two simple keywords per search."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "One or two keywords."},
                "max_price": {"type": "number", "description": "Optional: highest price per dish in rupees."},
                "veg_only": {"type": "boolean", "description": "Optional: only vegetarian dishes."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "add_to_cart",
        "description": (
            "Add a dish to the customer's cart. Only call this when the customer has asked for it or agreed to it. "
            "A cart holds dishes from one restaurant; adding from another restaurant starts a new cart."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "integer", "description": "The dish id from get_menu or search_dishes."},
                "quantity": {"type": "integer", "description": "How many, 1 to 10. Defaults to 1."},
            },
            "required": ["item_id"],
        },
    },
    {
        "name": "view_cart",
        "description": "What is in the customer's cart now, with quantities and the total.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _restaurant_info(r):
    info = {"restaurant_id": r.pk, "name": r.name, "cuisine": r.cuisine, "area": r.area_name,
            "city": r.city.name if r.city else ""}
    if r.distance is not None:
        info["distance_km"] = round(r.distance, 1)
    if r.eta:
        info["delivery_minutes"] = f"{r.eta[0]}-{r.eta[1]}"
    return info


def _dish_info(item):
    return {"item_id": item.pk, "name": item.name, "section": item.category, "description": item.description,
            "price_rupees": float(item.price), "vegetarian": item.is_veg}


def _reachable_restaurants(session):
    """Open restaurants this visitor can order from: in range of their location, or all when no location is set."""
    loc = location.get_location(session)
    restaurants = [add_delivery_info(r, loc) for r in Restaurant.objects.filter(is_open=True)]
    if loc:
        restaurants = sorted((r for r in restaurants if r.in_range), key=lambda r: r.distance)
    return loc, restaurants


def list_restaurants(session):
    loc, restaurants = _reachable_restaurants(session)
    result = {"delivering_to": loc["label"] if loc else None,
              "restaurants": [_restaurant_info(r) for r in restaurants]}
    if not loc:
        result["note"] = "No delivery location set, so distances and delivery times are unknown."
    return result


def get_menu(session, restaurant_id):
    loc, restaurants = _reachable_restaurants(session)
    restaurant = next((r for r in restaurants if r.pk == restaurant_id), None)
    if restaurant is None:
        return {"error": "No such restaurant, or it does not deliver to the customer's location."}
    return {"restaurant": _restaurant_info(restaurant),
            "dishes": [_dish_info(i) for i in restaurant.items.filter(is_available=True)]}


def search_dishes(session, query, max_price=None, veg_only=False):
    loc, restaurants = _reachable_restaurants(session)
    by_id = {r.pk: r for r in restaurants}
    words = [w for w in str(query).split() if len(w) > 1][:3]
    if not words:
        return {"error": "Give at least one keyword."}
    match = Q()
    for word in words:  # any word may match any field
        match |= (Q(name__icontains=word) | Q(description__icontains=word) | Q(category__icontains=word)
                  | Q(restaurant__name__icontains=word) | Q(restaurant__cuisine__icontains=word))
    dishes = MenuItem.objects.filter(match, is_available=True, restaurant_id__in=by_id).select_related("restaurant")
    if max_price is not None:
        dishes = dishes.filter(price__lte=max_price)
    if veg_only:
        dishes = dishes.filter(is_veg=True)
    # Nearest restaurants first, then cheapest dishes.
    ranked = sorted(dishes, key=lambda d: (by_id[d.restaurant_id].distance or 0, d.price))[:MAX_RESULTS]
    return {"delivering_to": loc["label"] if loc else None,
            "dishes": [{**_dish_info(d), "restaurant": _restaurant_info(by_id[d.restaurant_id])} for d in ranked]}


def add_to_cart(session, item_id, quantity=1):
    item = MenuItem.objects.filter(pk=item_id).select_related("restaurant").first()
    if item is None:
        return {"error": "No dish with that id."}
    quantity = max(1, min(int(quantity or 1), MAX_QUANTITY_PER_CALL))
    error = add_item(session, item, quantity)
    if error:
        return {"error": error}
    return {"added": f"{quantity} x {item.name} from {item.restaurant.name}", "cart": view_cart(session)}


def view_cart(session):
    cart = Cart(session)
    lines = cart.lines()
    if not lines:
        return {"items": [], "total_rupees": 0}
    restaurant = lines[0]["item"].restaurant
    return {"restaurant": restaurant.name,
            "items": [{"name": l["item"].name, "quantity": l["quantity"], "subtotal_rupees": float(l["subtotal"])}
                      for l in lines],
            "total_rupees": float(cart.total())}


HANDLERS = {
    "list_restaurants": list_restaurants,
    "get_menu": get_menu,
    "search_dishes": search_dishes,
    "add_to_cart": add_to_cart,
    "view_cart": view_cart,
}


def run_tool(session, name, tool_input):
    """Runs one tool call from Claude and returns (json_text, is_error). Bad input never crashes the chat:
    the error goes back to Claude as a tool result so it can correct itself."""
    handler = HANDLERS.get(name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool {name}."}), True
    try:
        args = dict(tool_input or {})
        if "restaurant_id" in args:
            args["restaurant_id"] = int(args["restaurant_id"])
        if "item_id" in args:
            args["item_id"] = int(args["item_id"])
        if args.get("max_price") is not None:
            args["max_price"] = float(args["max_price"])
        result = handler(session, **args)
    except (TypeError, ValueError) as error:
        return json.dumps({"error": f"Invalid input: {error}"}), True
    return json.dumps(result, ensure_ascii=False), "error" in result
