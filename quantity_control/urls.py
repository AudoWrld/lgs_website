from django.urls import path

from . import views

app_name = "qc"

urlpatterns = [
    path("dashboard/", views.qc_dashboard, name="qc_dashboard"),
    path("pending-review/", views.pending_review, name="pending_review"),
    path("reassay-review/", views.reassay_review, name="reassay_review"),
    path("approved-reports/", views.approved_reports, name="approved_reports"),
    path("generated-reports/", views.generated_reports, name="generated_reports"),
    path(
        "generated-reports/<path:reference>/", views.report_detail, name="report_detail"
    ),
]
