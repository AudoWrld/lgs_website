from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import reception_required
from submissions.models import Submission

from .forms import PaymentUpdateForm
from .models import Payment, PaymentTransaction


@reception_required
def payment_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all").upper()
    valid_statuses = {choice[0] for choice in Payment.STATUS_CHOICES}
    if status not in valid_statuses:
        status = "all"

    submissions = (
        Submission.objects.filter(is_submitted=True)
        .select_related("client")
        .prefetch_related("payment")
        .annotate(sample_count=Count("samples", distinct=True))
    )

    if query:
        submissions = submissions.filter(
            Q(reference__icontains=query) | Q(client__client_name__icontains=query)
        )
    if status != "all":
        submissions = submissions.filter(payment__payment_status=status)

    return render(
        request,
        "reception/payment_list.html",
        {
            "submissions": submissions.order_by("-created_at"),
            "query": query,
            "status": status,
            "status_choices": Payment.STATUS_CHOICES,
        },
    )


@reception_required
def payment_detail(request, reference):
    # Submission.reference is unique and is the identifier staff use in the lab.
    submission = get_object_or_404(Submission, reference__iexact=reference)
    payment, _ = Payment.objects.get_or_create(submission=submission)
    payment.recalculate_gross_amount()
    payment.save(update_fields=["gross_amount"])

    if request.method == "POST":
        if payment.payment_status == Payment.PAID:
            messages.info(request, "This payment is already marked as Paid.")
            return redirect("reception:payment_detail", reference=submission.reference)

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
                return redirect("reception:payment_detail", reference=submission.reference)
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

    return render(
        request,
        "reception/payment_detail.html",
        {"submission": submission, "payment": payment, "update_form": update_form},
    )
