from django.urls import path
from . import views

app_name = "administrator"

urlpatterns = [
    path("dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("branch-options/", views.branch_options, name="branch_options"),
    path("set-branch/", views.set_branch, name="set_branch"),
    path("clients/", views.client_list, name="client_list"),
    path("employees/", views.employee_list, name="employee_list"),
]
