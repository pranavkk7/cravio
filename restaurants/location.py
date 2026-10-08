"""Delivery locations: the cities Cravio serves, distance maths and delivery-time estimates.

The customer's location lives in the session as {"lat", "lng", "label", "city"}. It is set either
from the browser's geolocation, by picking an area or by switching city, and nothing about it is stored
in the database. Until the customer chooses, Cravio delivers to Kannur (DEFAULT_LOCATION).
"""
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

SESSION_KEY = "location"
EARTH_RADIUS_KM = 6371.0
CITY_RADIUS_KM = 40  # a location further than this from every city centre is outside the service area
KM_PER_MINUTE = 0.4  # roughly 24 km/h through city traffic


@dataclass(frozen=True)
class Area:
    key: str
    name: str
    lat: float
    lng: float


@dataclass(frozen=True)
class City:
    key: str
    name: str
    lat: float
    lng: float
    areas: tuple


CITIES = (
    City("kozhikode", "Kozhikode", 11.2588, 75.7804, (
        Area("mananchira", "Mananchira", 11.2546, 75.7794),
        Area("nadakkavu", "Nadakkavu", 11.2720, 75.7795),
        Area("beach-road", "Beach Road", 11.2570, 75.7702),
        Area("thondayad", "Thondayad", 11.2486, 75.8318),
        Area("feroke", "Feroke", 11.1810, 75.8380),
    )),
    City("kannur", "Kannur", 11.8745, 75.3704, (
        Area("fort-road", "Fort Road", 11.8700, 75.3660),
        Area("thavakkara", "Thavakkara", 11.8772, 75.3730),
        Area("thana", "Thana", 11.8850, 75.3800),
        Area("payyambalam", "Payyambalam", 11.8822, 75.3555),
    )),
    City("bengaluru", "Bengaluru", 12.9716, 77.5946, (
        Area("koramangala", "Koramangala", 12.9352, 77.6245),
        Area("indiranagar", "Indiranagar", 12.9719, 77.6412),
        Area("hsr-layout", "HSR Layout", 12.9116, 77.6474),
        Area("btm-layout", "BTM Layout", 12.9166, 77.6101),
        Area("mg-road", "MG Road", 12.9756, 77.6066),
        Area("whitefield", "Whitefield", 12.9698, 77.7500),
    )),
)
CITY_BY_KEY = {city.key: city for city in CITIES}


def distance_km(lat1, lng1, lat2, lng2) -> float:
    """Straight-line (haversine) distance between two points on the Earth."""
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def nearest_city(lat, lng):
    """The city whose centre is closest, or None when the point is outside every service area."""
    city = min(CITIES, key=lambda c: distance_km(lat, lng, c.lat, c.lng))
    return city if distance_km(lat, lng, city.lat, city.lng) <= CITY_RADIUS_KM else None


def find_area(key):
    """(city, area) for an area key such as "koramangala", or (None, None)."""
    for city in CITIES:
        for area in city.areas:
            if area.key == key:
                return city, area
    return None, None


def delivery_minutes(distance, prep_minutes):
    """A friendly delivery window such as (25, 30): kitchen time plus travel, rounded to 5 minutes."""
    total = prep_minutes + distance / KM_PER_MINUTE
    low = max(10, int(5 * round(total / 5)))
    return low, low + 5


def parse_coordinates(lat, lng):
    """Validated (lat, lng) floats from untrusted input, or None."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


# Kannur town centre: where Cravio shows restaurants until the customer sets their own location.
DEFAULT_LOCATION = {"lat": 11.8745, "lng": 75.3704, "label": "Kannur", "city": "kannur", "is_default": True}


def get_location(session):
    """The customer's chosen location, or Kannur when they have not chosen one."""
    return session.get(SESSION_KEY) or dict(DEFAULT_LOCATION)


def set_location(session, lat, lng, label):
    city = nearest_city(lat, lng)
    session[SESSION_KEY] = {"lat": lat, "lng": lng, "label": label, "city": city.key if city else None}
    return session[SESSION_KEY]


def clear_location(session):
    session.pop(SESSION_KEY, None)
