from django.urls import path

from . import views

app_name = "reception"

urlpatterns = [
    path("dashboard/", views.reception_dashboard, name="reception_dashboard"),
    path("clients/search/", views.client_search, name="client_search"),
    path("clients/new/", views.client_register, name="client_register"),
    path("samples/register/", views.sample_registration, name="sample_registration"),
    path("coa/reporting-preference/", views.coa_reporting_preference, name="coa_reporting_preference"),
    path("worksheets/new/", views.generate_worksheet, name="generate_worksheet"),
    path("client-submission/", views.client_submission_form, name="client_submission_form"),
    path("payments/", views.payment_details, name="payment_details"),
    path("expenses/new/", views.add_expense, name="add_expense"),
]
