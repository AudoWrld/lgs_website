from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.decorators import reception_required
from submissions.models import Submission

from .forms import PaymentUpdateForm
from .models import Payment, PaymentTransaction

LIST_LIMIT = 60


def _split_url(reference="", query=""):
    url = reverse("reception:payment_details")
    params = {}
    if reference:
        params["ref"] = reference
    if query:
        params["q"] = query
    return f"{url}?{urlencode(params)}" if params else url


@reception_required
def payment_list(request):
    query = request.GET.get("q", "").strip()
    reference = request.GET.get("ref", "").strip()

    submission = None
    payment = None
    update_form = None

    if reference:
        submission = (
            Submission.objects.filter(is_submitted=True, reference__iexact=reference)
            .select_related("client")
            .first()
        )

    if submission:
        payment, _ = Payment.objects.get_or_create(submission=submission)
        payment.recalculate_gross_amount()
        payment.save(update_fields=["gross_amount"])

        if request.method == "POST":
            if payment.payment_status == Payment.PAID:
                messages.info(request, "This payment is already marked as Paid.")
                return redirect(_split_url(submission.reference, query))

            update_form = PaymentUpdateForm(request.POST)
            if update_form.is_valid():
                cleaned = update_form.cleaned_data
                additional_paid = cleaned["additional_amount_paid"] or 0
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
                else:
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
                    messages.success(
                        request,
                        f"Payment updated for {submission.reference} — "
                        f"Total Paid: TZS {payment.total_amount_paid:,.2f}, "
                        f"Status: {payment.get_payment_status_display()}.",
                    )
                    return redirect(_split_url(submission.reference, query))
        else:
            update_form = PaymentUpdateForm(
                initial={
                    "discount": payment.discount,
                    "payment_method": payment.payment_method or Payment.CASH,
                    "transaction_reference": payment.transaction_reference,
                    "payment_status": payment.payment_status,
                    "remarks": payment.remarks,
                }
            )

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
            "not_found": bool(reference) and submission is None,
        },
    )


@reception_required
def payment_detail(request, reference):
    return redirect(_split_url(reference))
