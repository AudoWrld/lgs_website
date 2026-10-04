from django.urls import path

from . import views

app_name = "coa"

urlpatterns = [
    path("<str:token>/", views.verify_coa, name="verify_coa"),
    path("<str:token>", views.verify_coa, name="verify_coa_legacy"),
]