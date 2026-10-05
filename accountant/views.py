from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from accounts.decorators import accountant_required
from coa.models import COA
from coa.services import authorize_release, release_if_paid
from expenses.forms import ExpenseForm
from expenses.models import Expense
from payments.models import Payment, PaymentAccount, PaymentTransaction
from submissions.models import Submission

from .forms import PaymentForm, ReleaseForm, ReportFilterForm
from django.views.decorators.http import require_POST
from quotations.forms import (
    QuotationFilterForm,
    QuotationForm,
    QuotationItemFormSet,
)
from quotations.models import Quotation

ZERO = Decimal("0.00")
DASH = "\u2014"
RECENT_LIMIT = 5
RELEASE_LIMIT = 5
OVERDUE_LIMIT = 5
PAGE_SIZE = 20
REPORT_PAGE_SIZE = 4
RELEASE_PERMISSION = "coa.authorize_release"


def _total(queryset, field):
    return queryset.aggregate(total=Sum(field))["total"] or ZERO


def _paginate(request, queryset, size=PAGE_SIZE, param="page"):
    page = Paginator(queryset, size).get_page(request.GET.get(param))
    params = request.GET.copy()
    params.pop(param, None)
    return page, params.urlencode()


def _submitted_expenses():
    return Expense.objects.filter(is_submitted=True)


def _open_balances():
    balance = ExpressionWrapper(
        F("gross_amount") - F("discount") - F("total_amount_paid"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    return (
        Payment.objects.filter(submission__is_submitted=True)
        .annotate(balance=balance)
        .filter(balance__gt=0)
    )


def _credit_balances():
    return _open_balances().filter(credit_start_date__isnull=False)


def _overdue_cutoff():
    grace = getattr(settings, "CREDIT_GRACE_DAYS", 0)
    return timezone.localdate() - timedelta(days=grace)


def _overdue_credit_rows(limit=None):
    overdue = (
        _credit_balances()
        .filter(credit_due_date__lt=_overdue_cutoff())
        .select_related("submission")
        .order_by("credit_due_date")
    )
    if limit:
        overdue = overdue[:limit]
    return [
        {
            "reference": payment.submission.reference,
            "outstanding": payment.balance,
            "due_date": payment.credit_due_date,
            "days_overdue": payment.days_overdue,
        }
        for payment in overdue
    ]


def _by_method(queryset):
    rows = (
        queryset.order_by().values_list("payment_method").annotate(total=Sum("amount"))
    )
    return dict(rows)


def _channel_rows(today_queryset, month_queryset=None):
    first = _by_method(today_queryset)
    second = _by_method(month_queryset) if month_queryset is not None else {}
    return [
        {
            "name": label,
            "today": first.get(code, ZERO),
            "month": second.get(code, ZERO),
        }
        for code, label in Payment.METHOD_CHOICES
    ]


def _release_row(coa):
    payment = getattr(coa.submission, "payment", None)
    return {
        "id": coa.pk,
        "reference": coa.submission.reference,
        "coa_number": coa.coa_number,
        "outstanding": payment.outstanding_balance if payment else ZERO,
        "status": payment.get_payment_status_display() if payment else DASH,
        "credit_start_date": payment.credit_start_date if payment else None,
        "credit_due_date": payment.credit_due_date if payment else None,
        "eligible": True,
        "created_at": coa.created_at,
    }


def _pending_coas():
    return (
        COA.objects.filter(status=COA.PAYMENT_PENDING)
        .select_related("submission", "submission__payment")
        .order_by("created_at")
    )


def _recent_payments():
    recent = PaymentTransaction.objects.select_related("payment__submission")[
        :RECENT_LIMIT
    ]
    return [
        {
            "payment_date": tx.created_at,
            "reference": tx.payment.submission.reference,
            "amount": tx.amount,
            "method": tx.get_payment_method_display(),
            "receipt_number": DASH,
        }
        for tx in recent
    ]


def _dashboard_context():
    today = timezone.localdate()
    transactions = PaymentTransaction.objects.all()
    today_tx = transactions.filter(created_at__date=today)
    month_tx = transactions.filter(
        created_at__year=today.year, created_at__month=today.month
    )

    submitted_expenses = _submitted_expenses()
    today_expenses = submitted_expenses.filter(expense_date=today)
    month_expenses = submitted_expenses.filter(
        expense_date__year=today.year, expense_date__month=today.month
    )

    payments_today = _total(today_tx, "amount")
    payments_month = _total(month_tx, "amount")
    expenses_today = _total(today_expenses, "amount")
    expenses_month = _total(month_expenses, "amount")

    open_balances = _open_balances()

    return {
        "payments_today": payments_today,
        "expenses_today": expenses_today,
        "net_today": payments_today - expenses_today,
        "payments_month": payments_month,
        "expenses_month": expenses_month,
        "net_month": payments_month - expenses_month,
        "outstanding_debt": _total(open_balances, "balance"),
        "credit_outstanding": _total(_credit_balances(), "balance"),
        "channels": _channel_rows(today_tx, month_tx),
        "awaiting_release": [_release_row(c) for c in _pending_coas()[:RELEASE_LIMIT]],
        "overdue_credit": _overdue_credit_rows(limit=OVERDUE_LIMIT),
        "recent_payments": _recent_payments(),
    }


def _record_payment(submission, data, user):
    amount = data["amount"]
    if amount <= 0:
        raise ValidationError("Amount must be greater than zero.")

    with transaction.atomic():
        payment = Payment.ensure_for(submission)
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        payment.total_amount_paid = payment.total_amount_paid + amount
        payment.payment_method = data["payment_method"]
        payment.transaction_reference = data["transaction_reference"]
        payment.payment_status = payment.expected_status()
        payment.full_clean()
        payment.save()

        record = PaymentTransaction.objects.create(
            payment=payment,
            amount=amount,
            payment_method=data["payment_method"],
            transaction_reference=data["transaction_reference"],
            remarks=data.get("remarks", ""),
            resulting_status=payment.payment_status,
            resulting_total_paid=payment.total_amount_paid,
            resulting_outstanding=payment.outstanding_balance,
            recorded_by=user,
        )
        transaction.on_commit(lambda: release_if_paid(submission))
    return record


@accountant_required
def dashboard(request):
    return render(request, "accountant/dashboard.html", _dashboard_context())


@accountant_required
def reference_list(request):
    query = request.GET.get("q", "").strip()
    payments = (
        Payment.objects.filter(submission__is_submitted=True)
        .select_related("submission")
        .prefetch_related("submission__coas")
        .order_by("-submission__submitted_at", "-id")
    )
    if query:
        payments = payments.filter(submission__reference__icontains=query)

    page_obj, querystring = _paginate(request, payments)
    context = {
        "query": query,
        "page_obj": page_obj,
        "querystring": querystring,
        "total_count": payments.count(),
    }
    return render(request, "accountant/reference_list.html", context)


@accountant_required
def reference_detail(request, pk):
    payment = get_object_or_404(
        Payment.objects.filter(submission__is_submitted=True).select_related(
            "submission"
        ),
        pk=pk,
    )
    transactions = (
        PaymentTransaction.objects.filter(payment=payment)
        .select_related("recorded_by")
        .order_by("created_at", "id")
    )
    context = {
        "payment": payment,
        "submission": payment.submission,
        "transactions": transactions,
        "coas": payment.submission.coas.all(),
        "is_overdue": bool(
            payment.credit_due_date
            and payment.outstanding_balance > 0
            and payment.credit_due_date < _overdue_cutoff()
        ),
    }
    return render(request, "accountant/reference_detail.html", context)


@accountant_required
def payment_add(request):
    form = PaymentForm(
        request.POST or None,
        initial={"reference": request.GET.get("reference", "")},
    )

    if request.method == "POST" and form.is_valid():
        try:
            record = _record_payment(form.submission, form.cleaned_data, request.user)
        except ValidationError as exc:
            for message in exc.messages:
                form.add_error(None, message)
        else:
            messages.success(
                request,
                f"Payment of TZS {record.amount:,.2f} recorded for "
                f"{form.submission.reference}.",
            )
            url = reverse("accountant:payment_add")
            return redirect(f"{url}?reference={quote(form.submission.reference)}")

    submission = form.submission
    if submission is None:
        reference = (request.GET.get("reference") or "").strip()
        if reference:
            submission = Submission.objects.filter(
                is_submitted=True, reference__iexact=reference
            ).first()

    context = {
        "form": form,
        "summary": Payment.ensure_for(submission) if submission else None,
        "lookup": request.GET.get("reference", ""),
        "accounts": PaymentAccount.objects.filter(is_active=True),
    }
    return render(request, "accountant/payment_add.html", context)


@accountant_required
def payment_list(request):
    query = request.GET.get("q", "").strip()
    method = request.GET.get("method", "").strip()
    date_from = parse_date(request.GET.get("from", "") or "")
    date_to = parse_date(request.GET.get("to", "") or "")

    transactions = PaymentTransaction.objects.select_related(
        "payment__submission", "recorded_by"
    )
    if query:
        transactions = transactions.filter(
            payment__submission__reference__icontains=query
        )
    if method:
        transactions = transactions.filter(payment_method=method)
    if date_from:
        transactions = transactions.filter(created_at__date__gte=date_from)
    if date_to:
        transactions = transactions.filter(created_at__date__lte=date_to)

    page_obj, querystring = _paginate(request, transactions)
    context = {
        "query": query,
        "method": method,
        "date_from": request.GET.get("from", ""),
        "date_to": request.GET.get("to", ""),
        "methods": Payment.METHOD_CHOICES,
        "page_obj": page_obj,
        "querystring": querystring,
        "total_count": transactions.count(),
        "total_amount": _total(transactions, "amount"),
    }
    return render(request, "accountant/payment_list.html", context)


@accountant_required
def debt_credit(request):
    query = request.GET.get("q", "").strip()
    kind = request.GET.get("status", "all")

    balances = (
        _open_balances()
        .select_related("submission")
        .order_by("submission__submitted_at", "id")
    )
    if kind in ("credit", "overdue"):
        balances = balances.filter(credit_start_date__isnull=False)
    if kind == "overdue":
        balances = balances.filter(credit_due_date__lt=_overdue_cutoff())
    if query:
        balances = balances.filter(submission__reference__icontains=query)

    page_obj, querystring = _paginate(request, balances)
    context = {
        "query": query,
        "kind": kind,
        "page_obj": page_obj,
        "querystring": querystring,
        "total_count": balances.count(),
        "total_outstanding": _total(balances, "balance"),
    }
    return render(request, "accountant/debt_credit.html", context)


@accountant_required
def release_queue(request):
    if not request.user.has_perm(RELEASE_PERMISSION):
        raise PermissionDenied

    coas = _pending_coas()
    page_obj, querystring = _paginate(request, coas)
    context = {
        "rows": [_release_row(c) for c in page_obj.object_list],
        "page_obj": page_obj,
        "querystring": querystring,
        "total_count": coas.count(),
    }
    return render(request, "accountant/release_queue.html", context)


@accountant_required
def release_authorize(request, pk):
    if not request.user.has_perm(RELEASE_PERMISSION):
        raise PermissionDenied

    coa = get_object_or_404(_pending_coas(), pk=pk)
    row = _release_row(coa)
    form = ReleaseForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            authorize_release(coa, request.user, form.cleaned_data["reason"])
        except ValidationError as exc:
            for message in exc.messages:
                form.add_error(None, message)
        else:
            messages.success(
                request,
                f"Release authorized for {row['reference']} ({row['coa_number']}).",
            )
            return redirect("accountant:release_queue")

    return render(
        request,
        "accountant/release_authorize.html",
        {"row": row, "form": form},
    )


@accountant_required
def reports(request):
    data = request.GET.copy()
    if not data.get("period"):
        data["period"] = "daily"

    form = ReportFilterForm(data)
    today = timezone.localdate()

    if form.is_valid():
        start = form.cleaned_data["start"]
        end = form.cleaned_data["end"]
        label = form.cleaned_data["label"]
    else:
        start = end = today
        label = today.isoformat()

    transactions = (
        PaymentTransaction.objects.select_related("payment__submission")
        .filter(created_at__date__gte=start, created_at__date__lte=end)
        .order_by("-created_at", "-id")
    )

    period_expenses = (
        _submitted_expenses()
        .filter(expense_date__gte=start, expense_date__lte=end)
        .select_related("added_by")
        .order_by("-expense_date", "-created_at", "-id")
    )

    open_balances = _open_balances()
    credit_balances = _credit_balances()

    debt_qs = open_balances.select_related("submission").order_by(
        "submission__submitted_at", "id"
    )
    credit_qs = credit_balances.select_related("submission").order_by(
        "credit_due_date", "id"
    )

    payments_total = _total(transactions, "amount")
    expenses_total = _total(period_expenses, "amount")

    page_obj, querystring = _paginate(
        request, transactions, size=REPORT_PAGE_SIZE, param="page"
    )
    expense_page, expense_querystring = _paginate(
        request, period_expenses, size=REPORT_PAGE_SIZE, param="epage"
    )
    debt_page, debt_querystring = _paginate(
        request, debt_qs, size=REPORT_PAGE_SIZE, param="dpage"
    )
    credit_page, credit_querystring = _paginate(
        request, credit_qs, size=REPORT_PAGE_SIZE, param="cpage"
    )

    context = {
        "form": form,
        "label": label,
        "start": start,
        "end": end,
        "payments_total": payments_total,
        "expenses_total": expenses_total,
        "net_total": payments_total - expenses_total,
        "transaction_count": transactions.count(),
        "expense_count": period_expenses.count(),
        "outstanding_debt": _total(open_balances, "balance"),
        "credit_outstanding": _total(credit_balances, "balance"),
        "channels": _channel_rows(transactions),
        "page_obj": page_obj,
        "querystring": querystring,
        "expense_page": expense_page,
        "expense_querystring": expense_querystring,
        "debt_page": debt_page,
        "debt_querystring": debt_querystring,
        "credit_page": credit_page,
        "credit_querystring": credit_querystring,
    }
    return render(request, "accountant/reports.html", context)


@accountant_required
def expense_list(request):
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    date_from = parse_date(request.GET.get("from", "") or "")
    date_to = parse_date(request.GET.get("to", "") or "")

    expenses = Expense.objects.filter(is_submitted=True).select_related("added_by")
    if query:
        expenses = expenses.filter(
            Q(description__icontains=query)
            | Q(supplier_reference__icontains=query)
            | Q(document_number__icontains=query)
        )
    if category:
        expenses = expenses.filter(category=category)
    if date_from:
        expenses = expenses.filter(expense_date__gte=date_from)
    if date_to:
        expenses = expenses.filter(expense_date__lte=date_to)

    page_obj, querystring = _paginate(request, expenses)
    context = {
        "query": query,
        "category": category,
        "date_from": request.GET.get("from", ""),
        "date_to": request.GET.get("to", ""),
        "categories": Expense.CATEGORY_CHOICES,
        "page_obj": page_obj,
        "querystring": querystring,
        "total_count": expenses.count(),
        "total_amount": _total(expenses, "amount"),
        "my_drafts": Expense.objects.filter(
            is_submitted=False, added_by=request.user
        ).order_by("-created_at"),
    }
    return render(request, "accountant/expense_list.html", context)


@accountant_required
def expense_add(request):
    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.is_submitted = False
            expense.added_by = request.user
            expense.save()
            return redirect("accountant:expense_edit", slug=expense.slug)
    else:
        form = ExpenseForm()

    return render(request, "accountant/expense_add.html", {"form": form})


@accountant_required
def expense_edit(request, slug):
    expense = get_object_or_404(
        Expense, slug=slug, is_submitted=False, added_by=request.user
    )

    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES, instance=expense)
        if form.is_valid():
            action = request.POST.get("action")
            if action == "submit":
                expense = form.save(commit=False)
                expense.is_submitted = True
                expense.submitted_at = timezone.now()
                expense.save()
                messages.success(request, "Expense submitted successfully.")
                return redirect("accountant:expense_list")

            form.save()
            messages.success(request, "Expense changes saved.")
            return redirect("accountant:expense_edit", slug=expense.slug)
    else:
        form = ExpenseForm(instance=expense)

    return render(
        request,
        "accountant/expense_edit.html",
        {"form": form, "expense": expense},
    )


@accountant_required
def placeholder(request, heading):
    return render(request, "accountant/placeholder.html", {"heading": heading})


def _quotation_queryset():
    line = ExpressionWrapper(
        F("items__quantity") * F("items__unit_price"),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )
    return Quotation.objects.select_related("created_by").annotate(line_sum=Sum(line))


@accountant_required
def quotation_list(request):
    form = QuotationFilterForm(request.GET or None)
    quotations = _quotation_queryset()
    today = timezone.localdate()

    query = ""
    status = ""
    if form.is_valid():
        query = (form.cleaned_data.get("q") or "").strip()
        status = form.cleaned_data.get("status") or ""
        date_from = form.cleaned_data.get("date_from")
        date_to = form.cleaned_data.get("date_to")

        if query:
            quotations = quotations.filter(quotation_number__icontains=query)
        if date_from:
            quotations = quotations.filter(quotation_date__gte=date_from)
        if date_to:
            quotations = quotations.filter(quotation_date__lte=date_to)

        if status == Quotation.EXPIRED:
            quotations = quotations.filter(
                Q(status=Quotation.EXPIRED)
                | Q(
                    status__in=[Quotation.DRAFT, Quotation.SENT],
                    valid_until__lt=today,
                )
            )
        elif status in (Quotation.DRAFT, Quotation.SENT):
            quotations = quotations.filter(status=status, valid_until__gte=today)
        elif status == Quotation.ACCEPTED:
            quotations = quotations.filter(status=Quotation.ACCEPTED)

    quotations = quotations.order_by("-quotation_date", "-id")
    page_obj, querystring = _paginate(request, quotations)

    rows = [
        {
            "quotation": q,
            "total": max((q.line_sum or ZERO) - q.discount, ZERO),
        }
        for q in page_obj.object_list
    ]

    context = {
        "form": form,
        "query": query,
        "status": status,
        "rows": rows,
        "page_obj": page_obj,
        "querystring": querystring,
        "total_count": quotations.count(),
    }
    return render(request, "accountant/quotation_list.html", context)


@accountant_required
def quotation_add(request):
    form = QuotationForm(request.POST or None)
    formset = QuotationItemFormSet(request.POST or None, instance=Quotation())

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        if form.check_discount(formset.subtotal()):
            with transaction.atomic():
                quotation = form.save(commit=False)
                quotation.created_by = request.user
                quotation.save()
                formset.instance = quotation
                formset.save()
            messages.success(
                request, f"Quotation {quotation.quotation_number} created."
            )
            return redirect("accountant:quotation_detail", pk=quotation.pk)

    context = {"form": form, "formset": formset, "quotation": None, "is_edit": False}
    return render(request, "accountant/quotation_form.html", context)


@accountant_required
def quotation_detail(request, pk):
    quotation = get_object_or_404(
        Quotation.objects.select_related("created_by", "updated_by").prefetch_related(
            "items"
        ),
        pk=pk,
    )
    items = list(quotation.items.all())
    subtotal = sum((item.line_total for item in items), ZERO)

    context = {
        "quotation": quotation,
        "items": items,
        "subtotal": subtotal,
        "total_amount": max(subtotal - quotation.discount, ZERO),
        "status": quotation.effective_status,
        "status_display": quotation.effective_status_display,
        "can_edit": quotation.is_editable,
        "can_send": quotation.status == Quotation.DRAFT and bool(items),
        "can_accept": quotation.effective_status == Quotation.SENT,
        "can_expire": quotation.status != Quotation.ACCEPTED
        and quotation.status != Quotation.EXPIRED,
    }
    return render(request, "accountant/quotation_detail.html", context)


@accountant_required
def quotation_edit(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)

    if not quotation.is_editable:
        messages.error(request, "Only draft quotations can be edited.")
        return redirect("accountant:quotation_detail", pk=quotation.pk)

    form = QuotationForm(request.POST or None, instance=quotation)
    formset = QuotationItemFormSet(request.POST or None, instance=quotation)

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        if form.check_discount(formset.subtotal()):
            with transaction.atomic():
                updated = form.save(commit=False)
                updated.updated_by = request.user
                updated.save()
                formset.save()
            messages.success(
                request, f"Quotation {quotation.quotation_number} updated."
            )
            return redirect("accountant:quotation_detail", pk=quotation.pk)

    context = {
        "form": form,
        "formset": formset,
        "quotation": quotation,
        "is_edit": True,
    }
    return render(request, "accountant/quotation_form.html", context)


def _quotation_action(request, pk, action, success):
    quotation = get_object_or_404(Quotation, pk=pk)
    try:
        if action == "send":
            quotation.mark_sent(request.user)
        elif action == "accept":
            quotation.mark_accepted(request.user)
        else:
            quotation.mark_expired(request.user)
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)
    else:
        messages.success(request, f"Quotation {quotation.quotation_number} {success}.")
    return redirect("accountant:quotation_detail", pk=quotation.pk)


@accountant_required
@require_POST
def quotation_send(request, pk):
    return _quotation_action(request, pk, "send", "marked as sent")


@accountant_required
@require_POST
def quotation_accept(request, pk):
    return _quotation_action(request, pk, "accept", "marked as accepted")


@accountant_required
@require_POST
def quotation_expire(request, pk):
    return _quotation_action(request, pk, "expire", "marked as expired")
