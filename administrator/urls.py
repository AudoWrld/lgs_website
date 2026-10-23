from django.urls import path

from . import user_management, views

app_name = "administrator"

urlpatterns = [
    path("dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("branch-options/", views.branch_options, name="branch_options"),
    path("set-branch/", views.set_branch, name="set_branch"),
    path("clients/", views.client_list, name="client_list"),
    path("employees/", views.employee_list, name="employee_list"),
    path("add-client/", user_management.add_client, name="add_client"),
    path("add-employee/", user_management.add_employee, name="add_employee"),
    path("edit-client/<int:user_id>/", user_management.edit_client, name="edit_client"),
    path(
        "edit-employee/<int:user_id>/",
        user_management.edit_employee,
        name="edit_employee",
    ),
    path("delete-user/<int:user_id>/", user_management.delete_user, name="delete_user"),
    path(
        "employees/<int:user_id>/toggle/",
        user_management.toggle_employee,
        name="toggle_employee",
    ),
    path(
        "employees/<int:user_id>/reset-password/",
        user_management.reset_employee_password,
        name="reset_employee_password",
    ),
    path(
        "clients/<int:user_id>/reset-password/",
        user_management.reset_client_password,
        name="reset_client_password",
    ),
    path(
        "employees/<int:user_id>/activity/",
        user_management.employee_activity,
        name="employee_activity",
    ),
    path(
        "clients/<int:user_id>/activity/",
        user_management.client_activity,
        name="client_activity",
    ),
    path("profile/", views.profile_view, name="profile"),
]
