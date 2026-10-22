from django.urls import path
from . import views

app_name = "administrator"

urlpatterns = [
    path("dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("branch-options/", views.branch_options, name="branch_options"),
]
