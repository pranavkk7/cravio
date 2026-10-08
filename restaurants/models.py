from django.conf import settings
from django.db import models
from django.urls import reverse

from . import location


def _area_choices():
    return [(city.name, [(area.key, area.name) for area in city.areas]) for city in location.CITIES]


class Restaurant(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="restaurant")
    name = models.CharField(max_length=120)
    cuisine = models.CharField(max_length=80, blank=True, help_text="For example: Malabar, Biryani")
    description = models.TextField(blank=True)
    area = models.CharField(max_length=40, choices=_area_choices(), blank=True,
                            help_text="Sets the city and the map position.")
    address = models.CharField(max_length=255, blank=True)
    latitude = models.FloatField(null=True, blank=True, help_text="Leave empty to use the centre of the area.")
    longitude = models.FloatField(null=True, blank=True)
    delivery_radius_km = models.DecimalField(max_digits=4, decimal_places=1, default=6)
    prep_minutes = models.PositiveSmallIntegerField(default=20, help_text="Typical kitchen time for an order.")
    cover_image = models.CharField(max_length=200, blank=True, help_text="Static file path, e.g. img/food/biryani.jpg")
    is_open = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("restaurants:detail", args=[self.pk])

    def save(self, *args, **kwargs):
        # Restaurants without exact coordinates sit at the centre of their area.
        if self.area and (self.latitude is None or self.longitude is None):
            _, area = location.find_area(self.area)
            if area:
                self.latitude, self.longitude = area.lat, area.lng
        super().save(*args, **kwargs)

    @property
    def city(self):
        city, _ = location.find_area(self.area)
        return city

    @property
    def area_name(self):
        _, area = location.find_area(self.area)
        return area.name if area else ""

    @property
    def has_position(self):
        return self.latitude is not None and self.longitude is not None

    def distance_to(self, loc):
        """Kilometres from a session location to this restaurant, or None if either position is unknown."""
        if not loc or not self.has_position:
            return None
        return location.distance_km(loc["lat"], loc["lng"], self.latitude, self.longitude)

    def delivers_to(self, loc):
        distance = self.distance_to(loc)
        return distance is not None and distance <= float(self.delivery_radius_km)


class MenuItem(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=60, blank=True, help_text="Menu section, e.g. Biryani or Desserts")
    description = models.CharField(max_length=255, blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    is_veg = models.BooleanField("Vegetarian", default=False)
    image = models.CharField(max_length=200, blank=True, help_text="Static file path, e.g. img/food/biryani.jpg")
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"{self.name} ({self.restaurant})"
