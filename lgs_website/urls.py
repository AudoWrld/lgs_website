from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("reception/", include("reception.urls")),
    path("client/", include("client.urls")),
    path("chemist/", include("chemist.urls")),
    path("accountant/", include("accountant.urls")),
    path("qc/", include("quantity_control.urls")),
    path("verify/", include("coa.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
