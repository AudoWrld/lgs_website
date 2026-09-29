from django.urls import path, include

urlpatterns = [
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("reception/", include("reception.urls")),
    path("client/", include("client.urls")),
    path("chemist/", include("chemist.urls")),
    path("qc/", include("quantity_control.urls")),
]
