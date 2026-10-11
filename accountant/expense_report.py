from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET

from accounts.decorators import accountant_required
from expenses.models import Expense

from .expense_pdf import render_expense_pdf

ZERO = Decimal("0.00")
COMPANY_NAME = "LGS AFRICAN GROUP COMPANY LIMITED"
LOGO_STATIC = "core/img/lgs-logo.png"
PREVIEW_ROWS = 5


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


def _percent(amount, total):
    if not total:
        return Decimal("0.0")
    return (amount * 100 / total).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def build_report(start, end):
    expenses = Expense.objects.filter(
        is_submitted=True,
        expense_date__gte=start,
        expense_date__lte=end,
    ).order_by("-expense_date", "-created_at", "-id")

    total = ZERO
    by_category = {}
    by_method = {}
    rows = []

    for expense in expenses:
        label = _category_label(expense)
        total += expense.amount
        by_category[label] = by_category.get(label, ZERO) + expense.amount
        by_method[expense.payment_method] = (
            by_method.get(expense.payment_method, ZERO) + expense.amount
        )
        rows.append(
            {
                "date": expense.expense_date,
                "description": expense.description,
                "category": label,
                "payment": expense.get_payment_method_display(),
                "amount": expense.amount,
                "reference": " / ".join(
                    part
                    for part in (expense.supplier_reference, expense.document_number)
                    if part
                ),
            }
        )

    categories = [
        {"label": label, "amount": amount, "percent": _percent(amount, total)}
        for label, amount in sorted(by_category.items(), key=lambda i: (-i[1], i[0]))
    ]
    methods = [
        {"label": label, "amount": by_method.get(code, ZERO)}
        for code, label in Expense.PAYMENT_METHOD_CHOICES
    ]

    return {
        "rows": rows,
        "count": len(rows),
        "total": total,
        "categories": categories,
        "methods": methods,
    }


def _logo_path():
    found = finders.find(LOGO_STATIC)
    if found:
        return found
    root = getattr(settings, "STATIC_ROOT", None)
    return f"{root}/{LOGO_STATIC}" if root else ""


@accountant_required
@require_GET
def expense_report_preview(request):
    start, end = _range(request)
    if start is None:
        return HttpResponseBadRequest("Choose a valid date range.")

    data = build_report(start, end)
    context = {
        "start": start,
        "end": end,
        "data": data,
        "preview_rows": data["rows"][:PREVIEW_ROWS],
        "remaining": max(data["count"] - PREVIEW_ROWS, 0),
    }
    return render(request, "accountant/_expense_report_preview.html", context)


@accountant_required
@require_GET
def expense_report_pdf(request):
    start, end = _range(request)
    if start is None:
        return HttpResponseBadRequest("Choose a valid date range.")

    data = build_report(start, end)
    pdf = render_expense_pdf(
        data,
        start,
        end,
        printed=timezone.localtime(),
        company=COMPANY_NAME,
        logo_path=_logo_path(),
    )

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="expense-report-{start:%Y%m%d}-{end:%Y%m%d}.pdf"'
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response