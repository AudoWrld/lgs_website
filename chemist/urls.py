from django.urls import path

from . import views

app_name = "chemist"

urlpatterns = [
    path("dashboard/", views.chemist_dashboard, name="chemist_dashboard"),
    path(
        "mineral-analysis/",
        views.mineral_analysis_search,
        name="mineral_analysis_search",
    ),
    path(
        "mineral-analysis/entry/<slug:slug>/",
        views.mineral_analysis_entry,
        name="mineral_analysis_entry",
    ),
    path(
        "mineral-analysis/entry/<slug:slug>/preview/",
        views.mineral_analysis_preview,
        name="mineral_analysis_preview",
    ),
    path(
        "mineral-analysis/crm/<int:row_id>/",
        views.mineral_crm_entry,
        name="mineral_crm_entry",
    ),
    path(
        "mineral-analysis/<path:reference>/",
        views.mineral_analysis_samples,
        name="mineral_analysis_samples",
    ),
    path(
        "metallurgical-tests/",
        views.metallurgical_tests_search,
        name="metallurgical_tests_search",
    ),
    path(
        "metallurgical-tests/entry/<slug:slug>/",
        views.metallurgical_test_entry,
        name="metallurgical_tests_entry",
    ),
    path(
        "metallurgical-tests/<path:reference>/",
        views.metallurgical_tests_samples,
        name="metallurgical_tests_samples",
    ),
    path(
        "carbon-activity/entry/<slug:slug>/",
        views.carbon_activity_entry,
        name="carbon_activity_entry",
    ),
    path(
        "carbon-activity/entry/<slug:slug>/preview/",
        views.carbon_activity_preview,
        name="carbon_activity_preview",
    ),
    path("reassay/", views.reassay_samples, name="reassay_samples"),
    path("reassay/entry/<slug:slug>/", views.reassay_entry, name="reassay_entry"),
    path("qc-approved/", views.qc_approved, name="qc_approved"),
]
