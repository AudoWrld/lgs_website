from django.http import HttpResponse
from django.utils import timezone

from accounts.decorators import accountant_required
from expenses.models import Expense
from payments.models import Payment, PaymentTransaction

from .report_pdf import ReportDoc, Section, render_report_pdf
from .views import (
    DASH,
    ZERO,
    _breakdown,
    _by_method,
    _credit_balances,
    _open_balances,
    _overdue_cutoff,
    _report_range,
    _submitted_expenses,
    _total,
)


def _money(value):
    return f"{(value or ZERO):,.2f}"


def _day(value):
    return timezone.localtime(value).strftime("%Y-%m-%d")


def _category(expense):
    if expense.category == Expense.OTHER and expense.other_category:
        return expense.other_category
    return expense.get_category_display()


def _pdf_response(data, name):
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


def _file_name(prefix, start, end):
    return f"{prefix}-{start:%Y%m%d}-{end:%Y%m%d}.pdf"


@accountant_required
def financial_report_pdf(request):
    start, end = _report_range(request)

    transactions = (
        PaymentTransaction.objects.select_related("payment__submission__client")
        .filter(created_at__date__gte=start, created_at__date__lte=end)
        .order_by("-created_at", "-id")
    )
    expenses = (
        _submitted_expenses()
        .filter(expense_date__gte=start, expense_date__lte=end)
        .order_by("-expense_date", "-created_at", "-id")
    )
    open_balances = _open_balances()
    debts = open_balances.select_related("submission", "submission__client").order_by(
        "submission__submitted_at", "id"
    )

    by_method = _by_method(transactions)
    payments_total = _total(transactions, "amount")
    expenses_total = _total(expenses, "amount")
    debt_total = _total(open_balances, "balance")
    credit_total = _total(_credit_balances(), "balance")

    summary = [
        (f"{label} Payments:", _money(by_method.get(code, ZERO)), False)
        for code, label in Payment.METHOD_CHOICES
    ]
    summary += [
        ("Total Collected:", _money(payments_total), True),
        ("Total Expenses:", _money(expenses_total), False),
        ("Net Income:", _money(payments_total - expenses_total), True),
        ("Outstanding Debt (as of today):", _money(debt_total), False),
        ("Credit Outstanding (as of today):", _money(credit_total), False),
    ]

    payment_rows = [
        [
            tx.payment.submission.reference,
            tx.payment.submission.client.client_name,
            _day(tx.created_at),
            tx.get_payment_method_display(),
            tx.transaction_reference or DASH,
            _money(tx.amount),
        ]
        for tx in transactions
    ]
    expense_rows = [
        [
            expense.expense_date.strftime("%Y-%m-%d"),
            _category(expense),
            expense.description,
            expense.get_payment_method_display(),
            _money(expense.amount),
        ]
        for expense in expenses
    ]
    debt_rows = [
        [
            payment.submission.reference,
            payment.submission.client.client_name,
            (
                payment.credit_due_date.strftime("%Y-%m-%d")
                if payment.credit_due_date
                else DASH
            ),
            _money(payment.total_amount_paid),
            _money(payment.balance),
        ]
        for payment in debts
    ]

    doc = ReportDoc(
        title="Financial Report",
        short_title="Financial Report",
        start=start,
        end=end,
        generated=timezone.localtime(),
        website=request.get_host(),
        summary=summary,
        sections=[
            Section(
                title="Payments Collected",
                header=[
                    "Ref No.",
                    "Client",
                    "Date",
                    "Method",
                    "Txn. Ref.",
                    "Amount (TZS)",
                ],
                rows=payment_rows,
                widths=[0.17, 0.27, 0.13, 0.11, 0.16, 0.16],
                right=[5],
                totals=["", "", "", "", "Total", _money(payments_total)],
                empty="No payments collected in this period.",
            ),
            Section(
                title="Expenses",
                header=["Date", "Category", "Description", "Method", "Amount (TZS)"],
                rows=expense_rows,
                widths=[0.12, 0.2, 0.4, 0.12, 0.16],
                right=[4],
                truncate=[2],
                totals=["", "", "", "Total", _money(expenses_total)],
                empty="No expenses recorded in this period.",
            ),
            Section(
                title="Outstanding Debt (as of today)",
                header=[
                    "Ref No.",
                    "Client",
                    "Due Date",
                    "Paid (TZS)",
                    "Outstanding (TZS)",
                ],
                rows=debt_rows,
                widths=[0.2, 0.3, 0.14, 0.18, 0.18],
                right=[3, 4],
                totals=["", "", "", "Total", _money(debt_total)],
                empty="No outstanding debt.",
            ),
        ],
    )
    return _pdf_response(
        render_report_pdf(doc), _file_name("financial-report", start, end)
    )


@accountant_required
def expense_report_pdf(request):
    start, end = _report_range(request)

    expenses = (
        _submitted_expenses()
        .filter(expense_date__gte=start, expense_date__lte=end)
        .select_related("added_by")
        .order_by("-expense_date", "-created_at", "-id")
    )
    total = _total(expenses, "amount")
    count = expenses.count()
    categories = _breakdown(expenses, "category", dict(Expense.CATEGORY_CHOICES), total)

    summary = [(f"{row['name']}:", _money(row["total"]), False) for row in categories]
    summary += [
        ("Number of Records:", str(count), False),
        ("Grand Total:", _money(total), True),
    ]

    rows = [
        [
            expense.expense_date.strftime("%Y-%m-%d"),
            _category(expense),
            expense.description,
            expense.supplier_reference or DASH,
            expense.document_number or DASH,
            expense.get_payment_method_display(),
            _money(expense.amount),
        ]
        for expense in expenses
    ]

    doc = ReportDoc(
        title="Expense Report",
        short_title="Expense Report",
        start=start,
        end=end,
        generated=timezone.localtime(),
        website=request.get_host(),
        summary=summary,
        sections=[
            Section(
                title="Expense Records",
                header=[
                    "Date",
                    "Category",
                    "Description",
                    "Payee Ref.",
                    "Doc. No.",
                    "Method",
                    "Amount (TZS)",
                ],
                rows=rows,
                widths=[0.1, 0.16, 0.27, 0.13, 0.11, 0.1, 0.13],
                right=[6],
                truncate=[2],
                totals=["", "", "", "", "", "Total", _money(total)],
                empty="No expenses recorded in this period.",
            )
        ],
    )
    return _pdf_response(
        render_report_pdf(doc), _file_name("expense-report", start, end)
    )


@accountant_required
def debt_report_pdf(request):
    start, end = _report_range(request)

    debts = _open_balances().filter(
        submission__submitted_at__date__gte=start,
        submission__submitted_at__date__lte=end,
    )
    credit = debts.filter(credit_start_date__isnull=False)
    overdue = credit.filter(credit_due_date__lt=_overdue_cutoff())

    total = _total(debts, "balance")
    records = debts.select_related("submission", "submission__client").order_by(
        "submission__submitted_at", "id"
    )

    summary = [
        ("Total Outstanding:", _money(total), True),
        ("References Owing:", str(debts.count()), False),
        ("Credit Outstanding:", _money(_total(credit, "balance")), False),
        ("Credit References:", str(credit.count()), False),
        ("Overdue Outstanding:", _money(_total(overdue, "balance")), False),
        ("Overdue References:", str(overdue.count()), False),
    ]

    rows = [
        [
            payment.submission.reference,
            payment.submission.client.client_name,
            timezone.localtime(payment.submission.submitted_at).strftime("%Y-%m-%d"),
            _money(payment.net_amount_payable),
            _money(payment.total_amount_paid),
            _money(payment.balance),
            (
                payment.credit_due_date.strftime("%Y-%m-%d")
                if payment.credit_due_date
                else DASH
            ),
            (
                payment.credit_status
                if payment.credit_start_date
                else payment.get_payment_status_display()
            ),
        ]
        for payment in records
    ]

    doc = ReportDoc(
        title="Debt Report",
        short_title="Debt Report",
        start=start,
        end=end,
        generated=timezone.localtime(),
        website=request.get_host(),
        summary=summary,
        sections=[
            Section(
                title="Outstanding Balances",
                header=[
                    "Ref No.",
                    "Client",
                    "Submitted",
                    "Amount Due (TZS)",
                    "Paid (TZS)",
                    "Outstanding (TZS)",
                    "Due Date",
                    "Status",
                ],
                rows=rows,
                widths=[0.15, 0.2, 0.1, 0.12, 0.12, 0.12, 0.1, 0.09],
                right=[3, 4, 5],
                totals=["", "", "", "", "Total", _money(total), "", ""],
                empty="No outstanding debt for references submitted in this period.",
            )
        ],
    )
    return _pdf_response(render_report_pdf(doc), _file_name("debt-report", start, end))
