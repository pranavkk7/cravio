from . import location


def delivery_location(request):
    """The customer's delivery location and the area list, for the location picker on every page."""
    return {"delivery_location": location.get_location(request.session), "service_cities": location.CITIES}
