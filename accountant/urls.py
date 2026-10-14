from django.urls import path
from django.views.generic import RedirectView

from . import report_downloads, views

app_name = "accountant"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="accountant:dashboard")),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("references/", views.reference_list, name="reference_list"),
    path("references/<int:pk>/", views.reference_detail, name="reference_detail"),
    path("payments/add/", views.payment_add, name="payment_add"),
    path("payments/", views.payment_list, name="payment_list"),
    path(
        "receipts/",
        views.placeholder,
        {"heading": "Receipts"},
        name="receipt_list",
    ),
    path("quotations/", views.quotation_list, name="quotation_list"),
    path("quotations/add/", views.quotation_add, name="quotation_add"),
    path("quotations/<int:pk>/", views.quotation_detail, name="quotation_detail"),
    path("quotations/<int:pk>/edit/", views.quotation_edit, name="quotation_edit"),
    path("quotations/<int:pk>/send/", views.quotation_send, name="quotation_send"),
    path(
        "quotations/<int:pk>/accept/", views.quotation_accept, name="quotation_accept"
    ),
    path(
        "quotations/<int:pk>/expire/", views.quotation_expire, name="quotation_expire"
    ),
    path(
        "invoices/",
        views.placeholder,
        {"heading": "Invoices"},
        name="invoice_list",
    ),
    path("expenses/", views.expense_list, name="expense_list"),
    path("expenses/add/", views.expense_add, name="expense_add"),
    path("expenses/<slug:slug>/edit/", views.expense_edit, name="expense_edit"),
    path("debt-credit/", views.debt_credit, name="debt_credit"),
    path("release-queue/", views.release_queue, name="release_queue"),
    path(
        "release-queue/<int:pk>/",
        views.release_authorize,
        name="release_authorize",
    ),
    path("reports/", views.reports, name="reports"),
    path("expenses/report/", views.expense_report, name="expense_report"),
    path(
        "expenses/report/pdf/",
        report_downloads.expense_report_pdf,
        name="expense_report_pdf",
    ),
    path("reports/financial/", views.financial_report, name="financial_report"),
    path(
        "reports/financial/pdf/",
        report_downloads.financial_report_pdf,
        name="financial_report_pdf",
    ),
    path("reports/debt/", views.debt_report, name="debt_report"),
    path(
        "reports/debt/pdf/",
        report_downloads.debt_report_pdf,
        name="debt_report_pdf",
    ),
]