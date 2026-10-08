from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class SignUpForm(UserCreationForm):
    # Admins are created with `createsuperuser`, never through public sign-up.
    role = forms.ChoiceField(choices=[(User.Role.CUSTOMER, "Customer"), (User.Role.VENDOR, "Vendor (restaurant owner)")])

    class Meta:
        model = User
        fields = ("username", "email", "role")
