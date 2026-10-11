from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET

from accounts.decorators import accountant_required
from expenses.models import Expense
from payments.models import PaymentTransaction

from .financial_pdf import render_financial_pdf
from .views import (
    _channel_rows,
    _credit_balances,
    _open_balances,
    _submitted_expenses,
    _total,
)

COMPANY_NAME = "LGS AFRICAN GROUP COMPANY LIMITED"
LOGO_STATIC = "core/img/lgs-logo.png"
CONTACT_LINES = ()


def _date(value):
    try:
        return parse_date(value or "")
    except ValueError:
        return None


def _range(request):
    start = _date(request.GET.get("from"))
    end = _date(request.GET.get("to"))
    if start is None or end is None or start > end:
        return None, None
    return start, end


def _category_label(expense):
    if expense.category == Expense.OTHER and expense.other_category:
        return expense.other_category
    return expense.get_category_display()


def _logo_path():
    found = finders.find(LOGO_STATIC)
    if found:
        return found
    root = getattr(settings, "STATIC_ROOT", None)
    return f"{root}/{LOGO_STATIC}" if root else ""


def build_financial_report(start, end):
    transactions = (
        PaymentTransaction.objects.select_related("payment__submission")
        .filter(created_at__date__gte=start, created_at__date__lte=end)
        .order_by("-created_at", "-id")
    )
    expenses = (
        _submitted_expenses()
        .filter(expense_date__gte=start, expense_date__lte=end)
        .order_by("-expense_date", "-created_at", "-id")
    )
    open_balances = _open_balances()
    credit_balances = _credit_balances()
    debt = open_balances.select_related("submission").order_by(
        "submission__submitted_at", "id"
    )
    credit = credit_balances.select_related("submission").order_by(
        "credit_due_date", "id"
    )

    payments_total = _total(transactions, "amount")
    expenses_total = _total(expenses, "amount")

    payments = [
        {
            "date": timezone.localtime(tx.created_at),
            "reference": tx.payment.submission.reference,
            "method": tx.get_payment_method_display(),
            "amount": tx.amount,
        }
        for tx in transactions
    ]
    expense_rows = [
        {
            "date": expense.expense_date,
            "category": _category_label(expense),
            "description": expense.description,
            "amount": expense.amount,
        }
        for expense in expenses
    ]
    credit_rows = [
        {
            "reference": payment.submission.reference,
            "outstanding": payment.balance,
            "due_date": payment.credit_due_date,
            "status": str(payment.credit_status or ""),
        }
        for payment in credit
    ]
    debt_rows = [
        {
            "reference": payment.submission.reference,
            "due": payment.net_amount_payable,
            "paid": payment.total_amount_paid,
            "outstanding": payment.balance,
        }
        for payment in debt
    ]

    return {
        "payments_total": payments_total,
        "expenses_total": expenses_total,
        "net_total": payments_total - expenses_total,
        "outstanding_debt": _total(open_balances, "balance"),
        "credit_outstanding": _total(credit_balances, "balance"),
        "payment_count": len(payments),
        "expense_count": len(expense_rows),
        "channels": [
            {"label": row["name"], "amount": row["today"]}
            for row in _channel_rows(transactions)
        ],
        "payments": payments,
        "expenses": expense_rows,
        "credit": credit_rows,
        "debt": debt_rows,
    }


@accountant_required
@require_GET
def financial_report_preview(request):
    start, end = _range(request)
    if start is None:
        return HttpResponseBadRequest("Choose a valid date range.")

    context = {
        "start": start,
        "end": end,
        "data": build_financial_report(start, end),
    }
    return render(request, "accountant/_financial_report_preview.html", context)


@accountant_required
@require_GET
def financial_report_pdf(request):
    start, end = _range(request)
    if start is None:
        return HttpResponseBadRequest("Choose a valid date range.")

    pdf = render_financial_pdf(
        build_financial_report(start, end),
        start,
        end,
        printed=timezone.localtime(),
        company=COMPANY_NAME,
        logo_path=_logo_path(),
        contact_lines=CONTACT_LINES,
    )

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="financial-report-{start:%Y%m%d}-{end:%Y%m%d}.pdf"'
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response