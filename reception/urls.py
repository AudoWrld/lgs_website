from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "reception"

urlpatterns = [
    path("dashboard/", views.reception_dashboard, name="reception_dashboard"),
]
