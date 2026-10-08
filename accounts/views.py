from decimal import Decimal

from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.urls import reverse

from restaurants.models import Restaurant
from orders.models import Order

from .decorators import role_required
from .forms import SignUpForm
from .models import User


class RoleLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        # Each role is sent to its own dashboard after login.
        return self.get_redirect_url() or reverse(self.request.user.dashboard_url_name)


def signup(request):
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect(user.dashboard_url_name)
    return render(request, "accounts/signup.html", {"form": form})


@role_required(User.Role.ADMIN)
def admin_dashboard(request):
    paid = Order.objects.exclude(status=Order.Status.PENDING_PAYMENT)
    context = {
        "user_count": User.objects.count(),
        "customer_count": User.objects.filter(role=User.Role.CUSTOMER).count(),
        "vendor_count": User.objects.filter(role=User.Role.VENDOR).count(),
        "restaurant_count": Restaurant.objects.count(),
        "order_count": paid.count(),
        "revenue": paid.aggregate(total=Sum("total"))["total"] or Decimal("0"),
        "orders": Order.objects.select_related("customer", "restaurant")[:20],
    }
    return render(request, "accounts/admin_dashboard.html", context)
