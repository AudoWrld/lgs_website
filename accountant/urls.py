from django.urls import path

from . import views

app_name = "accountant"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
]