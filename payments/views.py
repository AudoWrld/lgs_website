from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.decorators import reception_required
from samples.models import SampleService, Service
from submissions.models import Submission

from .forms import PaymentUpdateForm
from .models import Payment, PaymentTransaction

LIST_LIMIT = 60
MAX_QUOTATION = Decimal("9999999999.99")


def _split_url(reference="", query=""):
    url = reverse("reception:payment_details")
    params = {}
    if reference:
        params["ref"] = reference
    if query:
        params["q"] = query
    return f"{url}?{urlencode(params)}" if params else url


def _quotation_lines(submission):
    return list(
        SampleService.objects.filter(
            sample__submission=submission,
            service__pricing_type=Service.QUOTATION,
        )
        .select_related("sample", "service")
        .order_by("sample__id", "service__name")
    )


def _save_quotations(request, submission):
    open_lines = [
        line for line in _quotation_lines(submission) if line.quoted_price is None
    ]
    amounts = {}
    errors = {}

    for line in open_lines:
        raw = (request.POST.get(f"quote_{line.pk}") or "").strip().replace(",", "")
        if not raw:
            continue
        try:
            amount = Decimal(raw)
        except InvalidOperation:
            errors[line.pk] = "Enter a valid amount."
            continue
        if not amount.is_finite() or amount <= 0:
            errors[line.pk] = "Amount must be greater than zero."
        elif amount > MAX_QUOTATION:
            errors[line.pk] = "Amount is too large."
        elif amount != amount.quantize(Decimal("0.01")):
            errors[line.pk] = "Use at most two decimal places."
        else:
            amounts[line.pk] = amount

    if errors:
        return 0, errors, "Please correct the highlighted amounts."
    if not amounts:
        return 0, {}, "Enter at least one approved quotation amount."

    with transaction.atomic():
        locked = list(
            SampleService.objects.select_for_update()
            .select_related("sample__submission", "service")
            .filter(pk__in=amounts, quoted_price__isnull=True)
        )
        if len(locked) != len(amounts):
            return (
                0,
                {},
                "One or more amounts were already entered. Refresh the page and try again.",
            )
        now = timezone.now()
        for line in locked:
            line.quoted_price = amounts[line.pk]
            line.quoted_by = request.user
            line.quoted_at = now
            line.save()

    return len(amounts), {}, ""


@reception_required
def payment_list(request):
    query = request.GET.get("q", "").strip()
    reference = request.GET.get("ref", "").strip()
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    quote_post = (
        request.method == "POST" and request.POST.get("action") == "save_quotations"
    )

    submission = None
    payment = None
    update_form = None
    flash = ""
    quote_errors = {}
    quote_message = ""

    if reference:
        submission = (
            Submission.objects.filter(is_submitted=True, reference__iexact=reference)
            .select_related("client")
            .first()
        )

    if submission:
        payment = Payment.ensure_for(submission)

        if quote_post:
            saved, quote_errors, quote_message = _save_quotations(request, submission)
            if saved:
                payment.refresh_from_db()
                text = (
                    f"{saved} quotation amount{'s' if saved != 1 else ''} saved for "
                    f"{submission.reference} — Gross Amount: "
                    f"TZS {payment.gross_amount:,.2f}."
                )
                if is_ajax:
                    flash = text
                else:
                    messages.success(request, text)
                    return redirect(_split_url(submission.reference, query))
        elif request.method == "POST":
            if payment.payment_status == Payment.PAID:
                if not is_ajax:
                    messages.info(request, "This payment is already marked as Paid.")
                    return redirect(_split_url(submission.reference, query))
            else:
                update_form = PaymentUpdateForm(request.POST)
                if update_form.is_valid():
                    cleaned = update_form.cleaned_data
                    additional_paid = cleaned["additional_amount_paid"] or Decimal("0")
                    if cleaned.get("discount") is not None:
                        payment.discount = cleaned["discount"]
                    payment.total_amount_paid += additional_paid
                    payment.payment_method = cleaned["payment_method"]
                    payment.transaction_reference = cleaned["transaction_reference"]
                    payment.payment_status = cleaned["payment_status"]
                    payment.remarks = cleaned["remarks"]

                    try:
                        payment.full_clean()
                    except ValidationError as exc:
                        for message in exc.messages:
                            update_form.add_error(None, message)
                        payment.refresh_from_db()
                    else:
                        with transaction.atomic():
                            payment.save()
                            PaymentTransaction.objects.create(
                                payment=payment,
                                amount=additional_paid,
                                payment_method=payment.payment_method,
                                transaction_reference=payment.transaction_reference,
                                remarks=payment.remarks,
                                resulting_status=payment.payment_status,
                                resulting_total_paid=payment.total_amount_paid,
                                resulting_outstanding=payment.outstanding_balance,
                                recorded_by=request.user,
                            )
                        text = (
                            f"Payment updated for {submission.reference} — "
                            f"Total Paid: TZS {payment.total_amount_paid:,.2f}, "
                            f"Status: {payment.get_payment_status_display()}."
                        )
                        if is_ajax:
                            flash = text
                            update_form = None
                        else:
                            messages.success(request, text)
                            return redirect(_split_url(submission.reference, query))

        if update_form is None:
            initial = {
                "discount": payment.discount if payment.discount else None,
                "payment_method": payment.payment_method or Payment.CASH,
                "transaction_reference": payment.transaction_reference,
                "payment_status": payment.payment_status,
                "remarks": payment.remarks,
            }
            update_form = PaymentUpdateForm(initial=initial)

    scoped = Submission.objects.filter(is_submitted=True)
    if query:
        scoped = scoped.filter(
            Q(reference__icontains=query) | Q(client__client_name__icontains=query)
        )
    match_count = scoped.count()
    submissions = list(
        scoped.select_related("client", "payment")
        .annotate(sample_count=Count("samples", distinct=True))
        .order_by("-created_at")[:LIST_LIMIT]
    )

    if submission is None and not reference:
        first_sub = submissions[0] if submissions else None
        if first_sub:
            submission = first_sub
            payment = Payment.ensure_for(submission)
            update_form = PaymentUpdateForm(
                initial={
                    "discount": payment.discount if payment.discount else None,
                    "payment_method": payment.payment_method or Payment.CASH,
                    "transaction_reference": payment.transaction_reference,
                    "payment_status": payment.payment_status,
                    "remarks": payment.remarks,
                }
            )
            reference = first_sub.reference

    quotation_lines = []
    unpriced_count = 0
    if submission is not None:
        quotation_lines = _quotation_lines(submission)
        for line in quotation_lines:
            line.form_value = (
                request.POST.get(f"quote_{line.pk}", "") if quote_post else ""
            )
            line.form_error = quote_errors.get(line.pk, "")
        unpriced_count = sum(1 for line in quotation_lines if line.quoted_price is None)

    return render(
        request,
        "reception/payment_list.html",
        {
            "query": query,
            "reference": reference,
            "submissions": submissions,
            "match_count": match_count,
            "list_limit": LIST_LIMIT,
            "submission": submission,
            "payment": payment,
            "update_form": update_form,
            "flash": flash,
            "quotation_lines": quotation_lines,
            "unpriced_count": unpriced_count,
            "quote_message": quote_message,
            "not_found": bool(reference) and submission is None,
        },
    )


@reception_required
def payment_detail(request, reference):
    return redirect(_split_url(reference))
