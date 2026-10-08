"""Session-based cart.

A cart holds items from a single restaurant, stored as
{"restaurant": <restaurant id>, "items": {<item id>: <quantity>}}.
"""
from decimal import Decimal

from restaurants import location
from restaurants.models import MenuItem

SESSION_KEY = "cart"
MAX_QUANTITY = 20  # per item, so a stuck "+" button cannot create a silly order


class Cart:
    def __init__(self, session):
        self.session = session
        self.data = session.get(SESSION_KEY) or {"restaurant": None, "items": {}}

    def _save(self):
        self.session[SESSION_KEY] = self.data
        self.session.modified = True

    def add(self, item: MenuItem, quantity: int = 1):
        if self.data["restaurant"] not in (None, item.restaurant_id):
            self.data = {"restaurant": None, "items": {}}  # switching restaurant starts a fresh cart
        self.data["restaurant"] = item.restaurant_id
        key = str(item.pk)
        self.data["items"][key] = min(self.data["items"].get(key, 0) + quantity, MAX_QUANTITY)
        self._save()

    def change(self, item_id: int, delta: int):
        """Adds [delta] (usually +1 or -1) to an item already in the cart. Dropping to zero removes it."""
        key = str(item_id)
        if key not in self.data["items"]:
            return
        quantity = min(self.data["items"][key] + delta, MAX_QUANTITY)
        if quantity <= 0:
            self.remove(item_id)
            return
        self.data["items"][key] = quantity
        self._save()

    def remove(self, item_id: int):
        self.data["items"].pop(str(item_id), None)
        if not self.data["items"]:
            self.data["restaurant"] = None
        self._save()

    def clear(self):
        self.data = {"restaurant": None, "items": {}}
        self._save()

    def quantity(self, item_id: int) -> int:
        return self.data["items"].get(str(item_id), 0)

    def __len__(self):
        return sum(self.data["items"].values())

    def lines(self):
        items = MenuItem.objects.filter(pk__in=self.data["items"].keys(), is_available=True)
        return [
            {"item": i, "quantity": self.data["items"][str(i.pk)], "subtotal": i.price * self.data["items"][str(i.pk)]}
            for i in items
        ]

    def total(self) -> Decimal:
        return sum((line["subtotal"] for line in self.lines()), Decimal("0.00"))


def add_item(session, item: MenuItem, quantity: int = 1):
    """The one place that decides whether a dish may go in the cart. Used by the Add buttons and by the
    AI assistant, so both follow the same rules. Returns an error message, or None when it was added."""
    restaurant = item.restaurant
    if not item.is_available or not restaurant.is_open:
        return f"{item.name} is not available right now."
    loc = location.get_location(session)
    if loc and not restaurant.delivers_to(loc):
        return f"{restaurant.name} does not deliver to {loc['label']}."
    Cart(session).add(item, quantity)
    return None
