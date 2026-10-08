from django.urls import path

from . import views

app_name = "assistant"
urlpatterns = [
    path("history/", views.history, name="history"),
    path("chat/", views.chat, name="chat"),
    path("reset/", views.reset, name="reset"),
]
