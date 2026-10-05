from django.urls import path

from . import views

app_name = "accountant"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path(
        "references/",
        views.placeholder,
        {"heading": "References"},
        name="reference_list",
    ),
    path(
        "payments/add/",
        views.placeholder,
        {"heading": "Record Payment"},
        name="payment_add",
    ),
    path(
        "payments/",
        views.placeholder,
        {"heading": "Payments"},
        name="payment_list",
    ),
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
    path(
        "debt-credit/",
        views.placeholder,
        {"heading": "Debt & Credit"},
        name="debt_credit",
    ),
    path(
        "release-queue/",
        views.placeholder,
        {"heading": "Report Release"},
        name="release_queue",
    ),
    path(
        "reports/",
        views.placeholder,
        {"heading": "Reports"},
        name="reports",
    ),
]