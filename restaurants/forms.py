from django import forms

from .models import MenuItem, Restaurant


class RestaurantForm(forms.ModelForm):
    class Meta:
        model = Restaurant
        fields = ("name", "cuisine", "description", "area", "address", "latitude", "longitude",
                  "delivery_radius_km", "prep_minutes", "is_open")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Customers only see restaurants that deliver to them, so every restaurant needs a place on the map.
        self.fields["area"].required = True


class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ("name", "category", "description", "price", "is_veg", "is_available")
