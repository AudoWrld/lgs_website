from django.urls import path

from . import views

app_name = "reception"

urlpatterns = [
    path("dashboard/", views.reception_dashboard, name="reception_dashboard"),
    path("clients/search/", views.client_search, name="client_search"),
    path("clients/register/", views.client_register, name="client_register"),
    path(
        "clients/<slug:slug>/submissions/",
        views.client_submissions,
        name="client_submissions",
    ),
    path(
        "clients/<slug:slug>/submissions/new/",
        views.client_new_submission,
        name="client_new_submission",
    ),
    path(
        "clients/<slug:slug>/submissions/<int:submission_id>/use/",
        views.submission_use,
        name="submission_use",
    ),
    path("clients/<slug:slug>/edit/", views.client_edit, name="client_edit"),
    path("samples/register/", views.submission_list, name="sample_registration"),
    path(
        "samples/<slug:slug>/",
        views.sample_registration_detail,
        name="sample_registration_detail",
    ),
    path(
        "samples/<int:pk>/edit/",
        views.sample_edit,
        name="sample_edit",
    ),
    path(
        "samples/<int:submission_id>/<int:pk>/remove/",
        views.sample_remove,
        name="sample_remove",
    ),
    path(
        "submissions/<int:submission_id>/submit/review/",
        views.submission_submit_review,
        name="submission_submit_review",
    ),
    path(
        "submissions/<int:submission_id>/submit/confirm/",
        views.submission_confirm_submit,
        name="submission_confirm_submit",
    ),
    path(
        "coa/reporting-preference/",
        views.coa_reporting_preference,
        name="coa_reporting_preference",
    ),
    path("worksheets/new/", views.generate_worksheet, name="generate_worksheet"),
    path(
        "client-submission/",
        views.client_submission_form,
        name="client_submission_form",
    ),
    path("payments/", views.payment_details, name="payment_details"),
    path("expenses/new/", views.add_expense, name="add_expense"),
]
