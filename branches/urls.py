from django.urls import path

from . import views

app_name = "branches"

urlpatterns = [
    path("", views.branch_list, name="branch_list"),
    path("add/", views.branch_save, name="branch_add"),
    path("<int:pk>/edit/", views.branch_save, name="branch_edit"),
    path(
        "<int:pk>/toggle-status/",
        views.branch_toggle_status,
        name="branch_toggle_status",
    ),
]
