import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import quote

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from payments.models import Payment
from samples.models import Sample, Service

from .models import COA, COAGroup, COAGroupSample, COAReportingPreference
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


def mineral_values(sample):
    qc = sample.qc_review
    return {
        "gold_1": qc.gold_test_1,
        "gold_2": qc.gold_test_2,
        "copper": qc.copper_final,
        "silver": qc.silver_final,
        "sulphur": qc.sulphur_final,
    }


def carbon_value(sample):
    return sample.qc_review.carbon_activity_final


def metallurgical_rows(sample, test_type):
    qc = sample.qc_review
    periods = [p for p in (12, 24, 48) if getattr(qc, f"show_recovery_{p}h")]
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
        for r in qc.entry.rows.filter(qc_included=True).select_related(
            "source_parameter"
        )
    ]
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


def _group_by_kind(samples):
    kinds = {}
    for sample in samples:
        for line in sample.sample_services.select_related("service"):
            service = line.service
            kind = service.metallurgical_type
            kind = MINERAL if not kind or kind == Service.NONE else kind
            entry = kinds.setdefault(kind, {"samples": [], "services": []})
            if sample not in entry["samples"]:
                entry["samples"].append(sample)
            if service not in entry["services"]:
                entry["services"].append(service)
    return [(k, kinds[k]) for k in BLOCK_ORDER if k in kinds]


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
    for number, (sample, rows) in enumerate(per_sample, start=1):
        for r in rows:
            row = [str(number), sample.client_sample_id]
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
    )


def _static_path(relative):
    found = finders.find(relative)
    if found:
        return found
    root = getattr(settings, "STATIC_ROOT", None)
    return f"{root}/{relative}" if root else ""


def _verify_base():
    base = getattr(settings, "SITE_BASE_URL", "https://lgsafrica.co.tz")
    return str(base).rstrip("/")


def build_coa_doc(coa):
    samples = list(coa.group.samples.order_by("id")) if coa.group_id else []
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
        verify_url=f"{_verify_base()}/verify/{quote(coa.verification_token, safe='')}",
        logo_path=_static_path("core/img/lgs-logo.png"),
        signature_path=_static_path("core/img/lgs-signature.png"),
    )


def attach_files(coa):
    pdf = render_coa_pdf(build_coa_doc(coa))
    png = render_coa_png(pdf)
    stem = coa.coa_number.replace("/", "-")
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


def generate_coas(submission, user):
    with transaction.atomic():
        pref = COAReportingPreference.objects.select_for_update().get(
            submission=submission
        )

        if not pref.is_finalized:
            raise ValidationError(
                "The COA reporting preference has not been finalized."
            )
        if submission.coas.exists():
            raise ValidationError(
                "COAs have already been generated for this reference."
            )

        samples = list(submission.samples.order_by("id"))
        if not samples or any(s.analysis_status != Sample.QC_APPROVED for s in samples):
            raise ValidationError(
                "All samples must be QC approved before generating COAs."
            )

        if pref.preference_type == COAReportingPreference.INDIVIDUAL:
            buckets = [[s] for s in samples]
        elif pref.preference_type == COAReportingPreference.COMBINED:
            buckets = [samples]
        else:
            buckets = None

        if buckets is not None:
            pref.groups.all().delete()
            for number, bucket in enumerate(buckets, start=1):
                group = COAGroup.objects.create(preference=pref, group_number=number)
                COAGroupSample.objects.bulk_create(
                    COAGroupSample(group=group, sample=s) for s in bucket
                )
        elif not pref.all_samples_assigned():
            raise ValidationError("Every sample must be assigned to a group.")

        groups = list(pref.groups.order_by("group_number"))
        paid = payment_cleared(submission)
        coas = [
            COA.objects.create(
                submission=submission,
                group=group,
                coa_number=next_coa_number(submission, group.group_number, len(groups)),
                status=COA.READY_FOR_RELEASE if paid else COA.PAYMENT_PENDING,
                released_at=timezone.now() if paid else None,
                approved_by=user,
            )
            for group in groups
        ]

    for coa in coas:
        try:
            attach_files(coa)
        except Exception:
            logger.exception("COA file build failed for %s", coa.coa_number)
    return coas
