from decimal import Decimal

from django.conf import settings
from django.db import models

from restaurants.models import MenuItem, Restaurant


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Pending payment"
        PAID = "paid", "Paid"
        PREPARING = "preparing", "Preparing"
        DELIVERED = "delivered", "Delivered"

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    razorpay_order_id = models.CharField(max_length=100, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.pk} - {self.restaurant}"

    @property
    def amount_in_paise(self) -> int:
        return int(self.total * 100)

    @property
    def progress_step(self) -> int:
        """0 = waiting for payment, 1 = paid, 2 = being prepared, 3 = delivered."""
        return [value for value, _ in self.Status.choices].index(self.status)


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=120)  # snapshot so old orders survive menu edits
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField()

    @property
    def subtotal(self):
        return self.unit_price * self.quantity
