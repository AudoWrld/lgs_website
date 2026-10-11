import logging
import threading
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import quote

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.files.base import ContentFile
from django.db import connections, transaction
from django.db.models import Q
from django.utils import timezone

from payments.models import Payment
from samples.models import Sample, Service

from .models import (
    COA,
    COAGroup,
    COAGroupSample,
    COAReleaseAuthorization,
    COAReportingPreference,
)
from .pdf import Block, CoaDoc, render_coa_pdf, render_coa_png

logger = logging.getLogger(__name__)

DASH = "\u2014"
INCLUDE_REMARKS_COLUMN = True

MINERAL = "MINERAL"
BLOCK_ORDER = [
    MINERAL,
    Service.CYANIDE_CONVENTIONAL,
    Service.CYANIDE_OPTIMIZATION,
    Service.CARBON_ACTIVITY,
]
TEST_TYPE_LABELS = {
    Service.CYANIDE_CONVENTIONAL: "Cyanide Leaching Test",
    Service.CYANIDE_OPTIMIZATION: "Leaching Parameter Optimization",
    Service.CARBON_ACTIVITY: "Carbon Activity Test",
}


def _qc_review(sample):
    try:
        return sample.qc_review
    except ObjectDoesNotExist:
        from quantity_control.views import _get_qc_review, _load_entry

        kind, entry = _load_entry(sample)
        return _get_qc_review(sample, kind, entry)


def mineral_values(sample):
    qc = _qc_review(sample)
    return {
        "gold_1": qc.gold_test_1,
        "gold_2": qc.gold_test_2,
        "copper": qc.copper_final,
        "silver": qc.silver_final,
        "sulphur": qc.sulphur_final,
    }


def carbon_value(sample):
    return _qc_review(sample).carbon_activity_final


def metallurgical_rows(sample, test_type):
    from chemist.models import MetallurgicalTestEntry

    qc = _qc_review(sample)
    periods = [p for p in (12, 24, 48) if getattr(qc, f"show_recovery_{p}h")]
    entry = (
        MetallurgicalTestEntry.objects.filter(sample=sample)
        .order_by("-revision")
        .first()
    )
    if entry is None:
        return periods, []
    rows = [
        {
            "parameter": r.source_parameter.display_label,
            "weight_volume": r.weight_volume,
            "si_unit": r.si_unit,
            "r12": r.gold_recovery_12h,
            "r24": r.gold_recovery_24h,
            "r48": r.gold_recovery_48h,
            "remarks": r.remarks,
        }
        for r in entry.rows.filter(qc_included=True)
        .select_related("source_parameter")
        .order_by("id")
    ]
    if not periods:
        periods = [p for p in (12, 24, 48) if any(r[f"r{p}"] is not None for r in rows)]
    return periods, rows


def _dec(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def whole(value):
    d = _dec(value)
    if d is None:
        return DASH
    return str(int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def two_dp(value):
    d = _dec(value)
    if d is None:
        return DASH
    return f"{d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def _unique(items):
    seen = []
    for item in items:
        if item and item not in seen:
            seen.append(item)
    return seen


TEST_KEYS = ("gold", "copper", "silver", "sulphur")


def _signature(kind, services):
    methods = tuple(_unique(s.method_of_analysis for s in services))
    if kind == MINERAL:
        flags = tuple(
            any(getattr(s, f"tests_{key}") for s in services) for key in TEST_KEYS
        )
        return (flags, methods)
    return (methods,)


def _group_by_kind(samples):
    groups = {}
    for sample in samples:
        per_kind = {}
        for line in sample.sample_services.all():
            service = line.service
            kind = service.metallurgical_type
            kind = MINERAL if not kind or kind == Service.NONE else kind
            bucket = per_kind.setdefault(kind, [])
            if service not in bucket:
                bucket.append(service)
        for kind, services in per_kind.items():
            key = (kind, _signature(kind, services))
            entry = groups.setdefault(
                key, {"kind": kind, "samples": [], "services": []}
            )
            entry["samples"].append(sample)
            for service in services:
                if service not in entry["services"]:
                    entry["services"].append(service)
    order = {kind: index for index, kind in enumerate(BLOCK_ORDER)}
    ranked = sorted(groups.values(), key=lambda e: order.get(e["kind"], len(order)))
    return [(e["kind"], e) for e in ranked]


def _mineral_block(entry):
    services = entry["services"]
    wants = {
        key: any(getattr(s, f"tests_{key}") for s in services)
        for key in ("gold", "copper", "silver", "sulphur")
    }
    has_non_carbon = any(s.sample_type != Sample.CARBON for s in entry["samples"])
    show_sulphur = wants["sulphur"] and has_non_carbon

    names = [
        n
        for n, on in (
            ("Gold", wants["gold"]),
            ("Copper", wants["copper"]),
            ("Silver", wants["silver"]),
            ("Sulphur", show_sulphur),
        )
        if on
    ]
    if len(names) > 1:
        service_text = f"Analysis of {', '.join(names[:-1])} and {names[-1]} Content"
    else:
        service_text = (
            f"Analysis of {names[0]} Content" if names else "Mineral Analysis"
        )

    header = ["S/N", "Sample ID"]
    if wants["gold"]:
        header += ["Gold Test 1 (ppm)", "Gold Test 2 (ppm)"]
    if wants["copper"]:
        header.append("Copper (Cu) (ppm)")
    if wants["silver"]:
        header.append("Silver (Ag) (ppm)")
    if show_sulphur:
        header.append("Sulphur (S) (%)")

    rows = []
    for number, sample in enumerate(entry["samples"], start=1):
        values = mineral_values(sample)
        row = [str(number), sample.client_sample_id]
        if wants["gold"]:
            row += [two_dp(values["gold_1"]), two_dp(values["gold_2"])]
        if wants["copper"]:
            row.append(two_dp(values["copper"]))
        if wants["silver"]:
            row.append(two_dp(values["silver"]))
        if show_sulphur:
            row.append(
                DASH
                if sample.sample_type == Sample.CARBON
                else two_dp(values["sulphur"])
            )
        rows.append(row)

    methods = " | ".join(_unique(s.method_of_analysis for s in services))
    return Block(
        results_title="Analytical Results:",
        detail_rows=[("Services:", service_text), ("Method of Analysis:", methods)],
        header=header,
        rows=rows,
    )


def _carbon_block(entry):
    rows = [
        [str(n), s.client_sample_id, two_dp(carbon_value(s))]
        for n, s in enumerate(entry["samples"], start=1)
    ]
    methods = " | ".join(_unique(s.method_of_analysis for s in entry["services"]))
    return Block(
        results_title="Metallurgical Test Results:",
        detail_rows=[
            ("Services:", "Metallurgical Test"),
            ("Test Type:", TEST_TYPE_LABELS[Service.CARBON_ACTIVITY]),
            ("Method of Analysis:", methods),
        ],
        header=["S/N", "Sample ID", "Carbon Activity (%)"],
        rows=rows,
        metallurgical=True,
        bold_last_column=True,
    )


def _cyanide_block(kind, entry):
    optimization = kind == Service.CYANIDE_OPTIMIZATION
    per_sample = []
    periods_union = set()
    for sample in entry["samples"]:
        periods, rows = metallurgical_rows(sample, kind)
        periods_union |= set(periods)
        per_sample.append((sample, rows))
    periods = sorted(periods_union)

    show_parameter = optimization or any(len(rows) > 1 for _, rows in per_sample)
    show_remarks = INCLUDE_REMARKS_COLUMN and any(
        r["remarks"] for _, rows in per_sample for r in rows
    )

    header = ["S/N", "Sample ID"]
    if show_parameter:
        header.append("Parameter")
    if optimization:
        header.append("Weight / Volume")
    header += [f"{p} Hrs Recovery (%)" for p in periods]
    if show_remarks:
        header.append("Remarks")

    out = []
    spans = []
    for number, (sample, rows) in enumerate(per_sample, start=1):
        start = len(out)
        for index, r in enumerate(rows):
            first = index == 0
            row = [
                str(number) if first else "",
                sample.client_sample_id if first else "",
            ]
            if show_parameter:
                row.append(r["parameter"])
            if optimization:
                wv = (
                    two_dp(r["weight_volume"])
                    if r["weight_volume"] is not None
                    else DASH
                )
                row.append(f"{wv} {r['si_unit']}".strip() if wv != DASH else DASH)
            row += [two_dp(r[f"r{p}"]) for p in periods]
            if show_remarks:
                row.append(r["remarks"] or DASH)
            out.append(row)
        end = len(out) - 1
        if end > start:
            spans.append((0, start, end))
            spans.append((1, start, end))

    methods = " | ".join(_unique(s.method_of_analysis for s in entry["services"]))
    return Block(
        results_title="Metallurgical Test Results:",
        detail_rows=[
            ("Services:", "Metallurgical Test"),
            ("Test Type:", TEST_TYPE_LABELS[kind]),
            ("Method of Analysis:", methods),
        ],
        header=header,
        rows=out,
        metallurgical=True,
        spans=spans,
    )


def _static_path(relative):
    found = finders.find(relative)
    if found:
        return found
    root = getattr(settings, "STATIC_ROOT", None)
    return f"{root}/{relative}" if root else ""


def _verify_base(base_url=None):
    base = base_url or getattr(settings, "SITE_BASE_URL", "https://lgsafrica.co.tz")
    return str(base).rstrip("/")


def build_coa_doc(coa, base_url=None):
    samples = (
        list(
            coa.group.samples.filter(analysis_status=Sample.QC_APPROVED)
            .select_related("qc_review")
            .prefetch_related("sample_services__service")
            .order_by("id")
        )
        if coa.group_id
        else []
    )
    submission = coa.submission
    submitted = (
        timezone.localtime(submission.submitted_at) if submission.submitted_at else None
    )

    blocks = []
    for kind, entry in _group_by_kind(samples):
        if kind == MINERAL:
            blocks.append(_mineral_block(entry))
        elif kind == Service.CARBON_ACTIVITY:
            blocks.append(_carbon_block(entry))
        else:
            blocks.append(_cyanide_block(kind, entry))

    nature = ", ".join(
        _unique(s.other_sample_type or s.get_sample_type_display() for s in samples)
    )

    return CoaDoc(
        coa_number=coa.coa_number,
        client_name=submission.client.client_name,
        submitted_at=submitted.strftime("%Y-%m-%d %H:%M:%S") if submitted else DASH,
        issued_at=timezone.localtime(coa.created_at),
        nature_of_sample=nature,
        sample_count=len(samples),
        blocks=blocks,
        verify_url=(
            f"{_verify_base(base_url)}/verify/"
            f"{quote(coa.verification_token, safe='')}/"
        ),
        logo_path=_static_path("core/img/lgs-logo.png"),
        signature_path=_static_path("core/img/lgs-signature.png"),
        stamp_path=_static_path("core/img/lgs-stamp.png"),
    )


def attach_files(coa, base_url=None):
    pdf = render_coa_pdf(build_coa_doc(coa, base_url=base_url))
    png = render_coa_png(pdf)
    stem = coa.coa_number.replace("/", "-")
    if coa.pdf_file:
        coa.pdf_file.delete(save=False)
    if coa.png_file:
        coa.png_file.delete(save=False)
    coa.pdf_file.save(f"{stem}.pdf", ContentFile(pdf), save=False)
    coa.png_file.save(f"{stem}.png", ContentFile(png), save=False)
    coa.save(update_fields=["pdf_file", "png_file", "updated_at"])
    return coa


def next_coa_number(submission, group_number, total):
    if total == 1:
        return submission.reference
    return f"{submission.reference}-{group_number:02d}"


def payment_cleared(submission):
    payment = Payment.ensure_for(submission)
    return payment.outstanding_balance <= 0 and payment.unpriced_quotation_count == 0


def release_if_paid(submission):
    if not payment_cleared(submission):
        return 0
    return submission.coas.filter(status=COA.PAYMENT_PENDING).update(
        status=COA.READY_FOR_RELEASE, released_at=timezone.now()
    )


def sample_has_coa(sample):
    return COA.objects.filter(
        Q(group__samples=sample)
        | Q(submission_id=sample.submission_id, group__isnull=True)
    ).exists()


def _ensure_groups(pref, samples, has_coas):
    kind = pref.preference_type

    if kind == COAReportingPreference.CUSTOM_GROUP:
        if not pref.all_samples_assigned():
            raise ValidationError(
                "Every sample must be assigned to a group before a COA can be generated."
            )
        return

    if not has_coas:
        pref.groups.all().delete()

    assigned = set(
        COAGroupSample.objects.filter(group__preference=pref).values_list(
            "sample_id", flat=True
        )
    )
    missing = [
        (index, sample)
        for index, sample in enumerate(samples, start=1)
        if sample.id not in assigned
    ]
    if not missing:
        return

    if kind == COAReportingPreference.INDIVIDUAL:
        taken = set(pref.groups.values_list("group_number", flat=True))
        for index, sample in missing:
            number = index if index not in taken else max(taken | {0}) + 1
            taken.add(number)
            group = COAGroup.objects.create(preference=pref, group_number=number)
            COAGroupSample.objects.create(group=group, sample=sample)
        return

    group = pref.groups.order_by("group_number").first()
    if group is None:
        group = COAGroup.objects.create(preference=pref, group_number=1)
    COAGroupSample.objects.bulk_create(
        COAGroupSample(group=group, sample=sample) for _, sample in missing
    )


def _build_files_now(coa_ids, base_url):
    coas = COA.objects.filter(pk__in=coa_ids).select_related(
        "submission", "submission__client", "group"
    )
    for coa in coas:
        try:
            attach_files(coa, base_url=base_url)
        except Exception:
            logger.exception("COA file build failed for %s", coa.coa_number)


def _build_files_thread(coa_ids, base_url):
    try:
        _build_files_now(coa_ids, base_url)
    finally:
        connections.close_all()


def _schedule_file_build(coa_ids, base_url):
    if not coa_ids:
        return
    if getattr(settings, "COA_BUILD_IN_BACKGROUND", True):

        def start():
            threading.Thread(
                target=_build_files_thread,
                args=(list(coa_ids), base_url),
                daemon=True,
            ).start()

        transaction.on_commit(start)
    else:
        _build_files_now(coa_ids, base_url)


def sync_coas(submission, user, base_url=None, sample=None):
    touched_ids = []

    with transaction.atomic():
        try:
            pref = COAReportingPreference.objects.select_for_update().get(
                submission=submission
            )
        except COAReportingPreference.DoesNotExist:
            raise ValidationError(
                "No COA reporting preference has been set for this reference, "
                "so no COA was generated."
            )

        if not pref.is_finalized:
            raise ValidationError(
                "The COA reporting preference has not been finalized yet, "
                "so no COA was generated."
            )

        samples = list(submission.samples.order_by("id"))
        if not samples:
            return []

        _ensure_groups(pref, samples, submission.coas.exists())

        all_groups = list(
            pref.groups.order_by("group_number").prefetch_related("samples")
        )

        if pref.preference_type == COAReportingPreference.INDIVIDUAL:
            total = len(samples)
        elif pref.preference_type == COAReportingPreference.COMBINED:
            total = 1
        else:
            total = len(all_groups)

        groups = all_groups
        if sample is not None:
            groups = [
                g for g in all_groups if any(s.id == sample.id for s in g.samples.all())
            ]

        existing = {
            c.group_id: c
            for c in submission.coas.filter(group_id__in=[g.id for g in groups])
        }
        paid = payment_cleared(submission)
        now = timezone.now()

        for group in groups:
            approved = [
                s
                for s in group.samples.all()
                if s.analysis_status == Sample.QC_APPROVED
            ]
            if not approved:
                continue

            coa = existing.get(group.id)
            if coa is None:
                coa = COA.objects.create(
                    submission=submission,
                    group=group,
                    coa_number=next_coa_number(submission, group.group_number, total),
                    status=COA.READY_FOR_RELEASE if paid else COA.PAYMENT_PENDING,
                    released_at=now if paid else None,
                    approved_by=user,
                )
            else:
                COA.objects.filter(pk=coa.pk).update(created_at=now, approved_by=user)
            touched_ids.append(coa.pk)

        if touched_ids:
            _schedule_file_build(touched_ids, base_url)

    return list(COA.objects.filter(pk__in=touched_ids).order_by("coa_number"))


def generate_coas(submission, user, base_url=None):
    return sync_coas(submission, user, base_url=base_url)


def authorize_release(coa, user, reason):
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise ValidationError("A reason of at least 5 characters is required.")

    with transaction.atomic():
        locked = (
            COA.objects.select_for_update()
            .select_related("submission", "submission__payment")
            .get(pk=coa.pk)
        )
        if locked.status != COA.PAYMENT_PENDING:
            raise ValidationError("This COA is no longer awaiting release.")

        payment = getattr(locked.submission, "payment", None)
        if payment is not None and payment.outstanding_balance <= 0:
            raise ValidationError(
                "This reference is fully paid and will be released automatically."
            )

        COAReleaseAuthorization.objects.create(
            coa=locked,
            authorized_by=user,
            reason=reason,
            outstanding_at_release=payment.outstanding_balance if payment else 0,
            payment_status_at_release=payment.payment_status if payment else "UNPAID",
            credit_start_date=payment.credit_start_date if payment else None,
            credit_due_date=payment.credit_due_date if payment else None,
        )
        locked.status = COA.RELEASED
        locked.released_at = timezone.now()
        locked.save(update_fields=["status", "released_at", "updated_at"])
    return locked
