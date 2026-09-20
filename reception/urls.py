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
        "samples/<slug:submission_slug>/<slug:sample_slug>/edit/",
        views.sample_edit,
        name="sample_edit",
    ),
    path(
        "samples/<slug:submission_slug>/<slug:sample_slug>/remove/",
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
        "coa/<path:reference>/reporting-preference/",
        views.coa_reporting_preference,
        name="coa_reporting_preference",
    ),
    path(
        "coa/<path:reference>/custom-groups/",
        views.coa_custom_group_wizard,
        name="coa_custom_group_wizard",
    ),
    path(
        "coa/<path:reference>/review/",
        views.coa_final_review,
        name="coa_final_review",
    ),
    path(
        "coa/<path:reference>/groups/<int:group_number>/delete/",
        views.coa_group_delete,
        name="coa_group_delete",
    ),
    path(
        "coa/<path:reference>/confirmation/",
        views.coa_confirmation,
        name="coa_confirmation",
    ),
    path("worksheets/new/", views.generate_worksheet, name="generate_worksheet"),
    path(
        "worksheets/<path:reference>/",
        views.generate_worksheet_detail,
        name="generate_worksheet_detail",
    ),
    path(
        "client-submission/",
        views.client_submission_form,
        name="client_submission_form",
    ),
    path(
        "client-submission/<path:reference>/reissue-password/",
        views.client_reissue_temp_password,
        name="client_reissue_temp_password",
    ),
    path(
        "client-submission/<path:reference>/pdf/",
        views.client_submission_form_pdf,
        name="client_submission_form_pdf",
    ),
    path(
        "client-submission/<path:reference>/",
        views.client_submission_form_detail,
        name="client_submission_form_detail",
    ),
    path("payments/", views.payment_list, name="payment_details"),
    path("payments/<path:reference>/", views.payment_detail, name="payment_detail"),
    path("expenses/new/", views.add_expense, name="add_expense"),
    path("expenses/<int:pk>/edit/", views.expense_edit, name="expense_edit"),
]
