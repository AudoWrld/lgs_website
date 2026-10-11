from django.urls import path

from . import views

app_name = "client"

urlpatterns = [
    path("dashboard/", views.customer_dashboard, name="customer_dashboard"),
    path("ready/", views.ready_for_release, name="ready_for_release"),
    path("pending/", views.pending_release, name="pending_release"),
    path("submissions/", views.my_submissions, name="my_submissions"),
    path("coa/<int:coa_id>/", views.coa_detail, name="coa_detail"),
    path("coa/<int:coa_id>/file/<str:kind>/", views.coa_file, name="coa_file"),
    path("coa/<int:coa_id>/preview/", views.coa_preview, name="coa_preview"),
]
