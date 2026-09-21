from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import reception_required
from submissions.models import Submission

from .forms import PaymentUpdateForm
from .models import Payment, PaymentTransaction


from django.db.models import Count, Q
from django.shortcuts import render

STATUS_ORDER = ["PAID", "PARTIALLY_PAID", "UNPAID", "CREDIT", "NOT_STARTED"]

STATUS_COLORS = {
    "PAID": "#1f7a45",
    "PARTIALLY_PAID": "#f39a2b",
    "UNPAID": "#a12a2a",
    "CREDIT": "#123e5b",
    "NOT_STARTED": "#b9c0c5",
}


def _status_labels():
    labels = dict(Payment.STATUS_CHOICES)
    labels["NOT_STARTED"] = "Not Started"
    return labels


def _percent(part, whole):
    if not whole:
        return 0.0
    value = float(part) / float(whole) * 100
    return max(0.0, min(100.0, value))


@reception_required
def payment_list(request):
    labels = _status_labels()
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all").upper()
    if status not in STATUS_ORDER:
        status = "all"

    scoped = Submission.objects.filter(is_submitted=True)
    if query:
        scoped = scoped.filter(
            Q(reference__icontains=query) | Q(client__client_name__icontains=query)
        )

    raw_counts = {
        (row["payment__payment_status"] or "NOT_STARTED"): row["total"]
        for row in scoped.order_by()
        .values("payment__payment_status")
        .annotate(total=Count("id"))
    }
    total_count = sum(raw_counts.values())

    segments = []
    stops = []
    cursor = 0.0
    for key in STATUS_ORDER:
        count = raw_counts.get(key, 0)
        share = _percent(count, total_count)
        segments.append(
            {
                "key": key,
                "label": labels[key],
                "count": count,
                "share": round(share, 1),
                "color": STATUS_COLORS[key],
            }
        )
        if count:
            end = cursor + share
            stops.append(f"{STATUS_COLORS[key]} {cursor:.2f}% {end:.2f}%")
            cursor = end
    if stops:
        donut_gradient = f"conic-gradient({', '.join(stops)})"
    else:
        donut_gradient = "conic-gradient(#e4dfd3 0% 100%)"

    filters = [{"value": "all", "label": "All", "count": total_count}]
    for key in STATUS_ORDER:
        filters.append(
            {"value": key, "label": labels[key], "count": raw_counts.get(key, 0)}
        )

    kpis = [
        {"value": "all", "label": "Submissions", "count": total_count, "tone": "navy"},
        {
            "value": "PAID",
            "label": "Paid",
            "count": raw_counts.get("PAID", 0),
            "tone": "green",
        },
        {
            "value": "PARTIALLY_PAID",
            "label": "Partially Paid",
            "count": raw_counts.get("PARTIALLY_PAID", 0),
            "tone": "orange",
        },
        {
            "value": "UNPAID",
            "label": "Unpaid",
            "count": raw_counts.get("UNPAID", 0),
            "tone": "red",
        },
        {
            "value": "NOT_STARTED",
            "label": "Not Started",
            "count": raw_counts.get("NOT_STARTED", 0),
            "tone": "grey",
        },
    ]

    follow_up = list(
        scoped.filter(
            Q(payment__isnull=True)
            | Q(payment__payment_status__in=["UNPAID", "PARTIALLY_PAID"])
        )
        .select_related("client", "payment")
        .order_by("-created_at")[:6]
    )

    submissions = scoped
    if status == "NOT_STARTED":
        submissions = submissions.filter(payment__isnull=True)
    elif status != "all":
        submissions = submissions.filter(payment__payment_status=status)

    submissions = list(
        submissions.select_related("client", "payment")
        .annotate(sample_count=Count("samples", distinct=True))
        .order_by("-created_at")
    )

    return render(
        request,
        "reception/payment_list.html",
        {
            "submissions": submissions,
            "submission_count": len(submissions),
            "query": query,
            "status": status,
            "filters": filters,
            "kpis": kpis,
            "segments": segments,
            "donut_gradient": donut_gradient,
            "total_count": total_count,
            "follow_up": follow_up,
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
                return redirect(
                    "reception:payment_detail", reference=submission.reference
                )
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
