from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("assistant/", include("assistant.urls")),
    path("", include("orders.urls")),
    path("", include("restaurants.urls")),
]
