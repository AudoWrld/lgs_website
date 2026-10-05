from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "accountant"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="accountant:dashboard")),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("references/", views.reference_list, name="reference_list"),
    path("payments/add/", views.payment_add, name="payment_add"),
    path("payments/", views.payment_list, name="payment_list"),
    path(
        "receipts/",
        views.placeholder,
        {"heading": "Receipts"},
        name="receipt_list",
    ),
    path(
        "expenses/",
        views.placeholder,
        {"heading": "Expenses"},
        name="expense_list",
    ),
    path(
        "quotations/",
        views.placeholder,
        {"heading": "Quotations"},
        name="quotation_list",
    ),
    path(
        "invoices/",
        views.placeholder,
        {"heading": "Invoices"},
        name="invoice_list",
    ),
    path("debt-credit/", views.debt_credit, name="debt_credit"),
    path("release-queue/", views.release_queue, name="release_queue"),
    path("reports/", views.reports, name="reports"),
]
