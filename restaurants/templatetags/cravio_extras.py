import os
from decimal import Decimal, InvalidOperation

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    """A static URL that changes whenever the file does ("style.css?v=<modified time>"), so browsers
    never keep using an old cached copy of the stylesheet or scripts after an update."""
    url = static(path)
    found = finders.find(path)
    return f"{url}?v={int(os.path.getmtime(found))}" if found else url

COVER_COUNT = 6  # number of .cover-N gradients defined in style.css


@register.filter
def inr(value):
    """Formats money the Indian way: 125000 -> "₹1,25,000", 99.5 -> "₹99.50"."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    sign = "-" if amount < 0 else ""
    whole, _, paise = f"{abs(amount):.2f}".partition(".")
    # Indian grouping: the last three digits, then groups of two.
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    grouped = ",".join(groups + [tail])
    return f"{sign}₹{grouped}" + ("" if paise == "00" else f".{paise}")


@register.filter
def cover(pk):
    """A stable cover style for a restaurant, so it looks the same on every page."""
    try:
        return f"cover-{int(pk) % COVER_COUNT + 1}"
    except (TypeError, ValueError):
        return "cover-1"


@register.filter
def initial(name):
    """First letter of a name, for monogram tiles."""
    text = str(name or "").strip()
    return text[:1].upper() if text else "?"


@register.filter
def monogram(name):
    """Up to two initials of a dish name, for the tile shown when a dish has no photo: "Peppy Paneer" -> "PP"."""
    words = [w for w in str(name or "").replace("(", " ").split() if w[:1].isalpha()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


@register.filter
def km(distance):
    """A friendly distance: 0.45 -> "450 m", 3.24 -> "3.2 km", 27.6 -> "28 km"."""
    try:
        distance = float(distance)
    except (TypeError, ValueError):
        return ""
    metres = max(50, round(distance * 1000, -1))
    if metres < 1000:
        return f"{metres:.0f} m"
    return f"{distance:.1f} km" if distance < 10 else f"{distance:.0f} km"
