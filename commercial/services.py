from collections import OrderedDict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from payments.models import Payment
from samples.models import SampleService
from submissions.models import Submission

from .models import (
    CommercialInvoice,
    CommercialInvoiceLine,
    CommercialInvoiceReference,
)

ZERO = Decimal("0.00")


def _service_name(row):
    service = row.service
    return getattr(service, "name", None) or str(service)


def _sample_type(row):
    sample = row.sample
    value = getattr(sample, "other_sample_type", "") or sample.get_sample_type_display()
    return str(value).upper() or "-"


def build_lines(submission, payment):
    rows = (
        SampleService.objects.filter(sample__submission=submission)
        .select_related("service", "sample")
        .order_by("id")
    )
    grouped = OrderedDict()
    for row in rows:
        key = (_service_name(row), _sample_type(row), row.charged_price or ZERO)
        grouped[key] = grouped.get(key, 0) + 1

    lines = [
        {
            "reference": submission.reference,
            "description": name,
            "sample_type": sample_type,
            "quantity": count,
            "unit_price": price,
            "amount": price * count,
        }
        for (name, sample_type, price), count in grouped.items()
    ]
    if payment.discount and payment.discount > 0:
        lines.append(
            {
                "reference": submission.reference,
                "description": "Discount",
                "sample_type": "",
                "quantity": 0,
                "unit_price": ZERO,
                "amount": -payment.discount,
            }
        )
    return lines


def lookup(reference):
    entered = (
        Submission.objects.select_related("client")
        .filter(reference__iexact=reference.strip())
        .first()
    )
    if entered is None:
        return None

    client = entered.client
    submissions = (
        Submission.objects.filter(client=client)
        .select_related("commercial_link__invoice")
        .order_by("submitted_at", "id")
    )

    eligible = []
    skipped = []
    already = None

    for submission in submissions:
        link = getattr(submission, "commercial_link", None)
        if link is not None:
            if submission.pk == entered.pk:
                already = link.invoice
            continue

        if not submission.is_submitted:
            if submission.pk == entered.pk:
                skipped.append(
                    {
                        "submission": submission,
                        "reason": "Not yet submitted to the lab.",
                    }
                )
            continue

        payment = Payment.ensure_for(submission)

        if payment.unpriced_quotation_count:
            skipped.append(
                {
                    "submission": submission,
                    "reason": "A quotation price has not been entered for every quoted service.",
                }
            )
            continue

        if payment.net_amount_payable <= 0:
            skipped.append(
                {"submission": submission, "reason": "No charges on this reference."}
            )
            continue

        if payment.outstanding_balance <= 0:
            if submission.pk == entered.pk:
                skipped.append(
                    {
                        "submission": submission,
                        "reason": "Already fully paid. Only unpaid references are invoiced.",
                    }
                )
            continue

        lines = build_lines(submission, payment)
        eligible.append(
            {
                "submission": submission,
                "payment": payment,
                "lines": lines,
                "total": payment.net_amount_payable,
            }
        )

    grand_total = sum((item["total"] for item in eligible), ZERO)
    paid_total = sum((item["payment"].total_amount_paid for item in eligible), ZERO)

    return {
        "entered": entered,
        "client": client,
        "eligible": eligible,
        "skipped": skipped,
        "already": already,
        "grand_total": grand_total,
        "paid_total": paid_total,
        "outstanding_total": max(grand_total - paid_total, ZERO),
    }


def create_invoice(client_id, submission_ids, user):
    ids = {int(pk) for pk in submission_ids}
    if not ids:
        raise ValidationError("Select at least one reference to invoice.")

    with transaction.atomic():
        submissions = list(
            Submission.objects.select_for_update()
            .filter(pk__in=ids, client_id=client_id, is_submitted=True)
            .order_by("submitted_at", "id")
        )
        if len(submissions) != len(ids):
            raise ValidationError(
                "Some references are not eligible or belong to a different customer."
            )

        if CommercialInvoiceReference.objects.filter(
            submission__in=submissions
        ).exists():
            raise ValidationError("One or more references have already been invoiced.")

        invoice = CommercialInvoice.objects.create(
            client_id=client_id,
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )

        position = 0
        total = ZERO
        for submission in submissions:
            payment = Payment.ensure_for(submission)
            if payment.unpriced_quotation_count or payment.net_amount_payable <= 0:
                raise ValidationError(
                    f"{submission.reference} is not eligible for invoicing."
                )
            if payment.outstanding_balance <= 0:
                raise ValidationError(f"{submission.reference} is already fully paid.")
            for line in build_lines(submission, payment):
                position += 1
                CommercialInvoiceLine.objects.create(
                    invoice=invoice, position=position, **line
                )
            CommercialInvoiceReference.objects.create(
                invoice=invoice,
                submission=submission,
                amount=payment.net_amount_payable,
            )
            total += payment.net_amount_payable

        invoice.total_charges = total
        invoice.save(update_fields=["total_charges"])
        return invoice
