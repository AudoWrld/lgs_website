from django.urls import path, include

urlpatterns = [
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("reception/", include("reception.urls")),
]
