from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        VENDOR = "vendor", "Vendor"
        ADMIN = "admin", "Admin"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER)

    def save(self, *args, **kwargs):
        # Superusers always get the admin role so they land on the admin dashboard.
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    @property
    def dashboard_url_name(self) -> str:
        return {
            self.Role.CUSTOMER: "restaurants:list",
            self.Role.VENDOR: "restaurants:vendor_dashboard",
            self.Role.ADMIN: "accounts:admin_dashboard",
        }[self.role]
