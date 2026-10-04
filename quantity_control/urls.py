from django.urls import path

from . import views

app_name = "qc"

urlpatterns = [
    path("dashboard/", views.qc_dashboard, name="qc_dashboard"),
    path("pending-review/", views.pending_review, name="pending_review"),
    path("reassay-review/", views.reassay_review, name="reassay_review"),
    path("approved-reports/", views.approved_reports, name="approved_reports"),
    path("generate-report/", views.generate_report, name="generate_report"),
    path("review/<slug:slug>/", views.sample_review, name="sample_review"),
    path("generated-reports/", views.generated_reports, name="generated_reports"),
    path(
        "generated-reports/coa/<int:coa_id>/preview/",
        views.report_coa_preview,
        name="report_coa_preview",
    ),
    path(
        "generated-reports/<path:reference>/", views.report_detail, name="report_detail"
    ),
]
