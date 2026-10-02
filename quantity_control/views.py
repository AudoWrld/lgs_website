from datetime import timedelta
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import qc_required
from coa.models import COA
from samples.models import Sample, Service
from submissions.models import Submission

from chemist.models import (
    CRMEntry,
    CarbonActivityEntry,
    MetallurgicalTestEntry,
    MineralAnalysisEntry,
    get_metallurgical_type,
    lab_sample_id_for,
    worksheet_rows_for_sample,
)
from worksheet.models import WorksheetRow

from .models import QCEditLog, QCReview

PAGE_SIZE = 12

RECOVERY_FIELDS = (
    ("gold_recovery_12h", "recovery_12h", "Gold Recovery 12h"),
    ("gold_recovery_24h", "recovery_24h", "Gold Recovery 24h"),
    ("gold_recovery_48h", "recovery_48h", "Gold Recovery 48h"),
)


def _visible_submissions():
    return Submission.objects.filter(is_submitted=True).select_related("client")


def _paginate(request, queryset):
    page = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()


def _lab_id(sample):
    mapping = getattr(sample, "lab_mapping", None)
    if mapping is None:
        return sample.slug.upper()
    prefix, _, suffix = mapping.lab_sample_id.rpartition("-")
    if not prefix:
        return mapping.lab_sample_id
    return f"{prefix}-{suffix.lstrip('0') or '0'}"


def _with_lab_id(queryset):
    return [
        SimpleNamespace(sample=sample, lab_id=_lab_id(sample)) for sample in queryset
    ]


@qc_required
def qc_dashboard(request):
    visible = Sample.objects.filter(submission__is_submitted=True)

    pending = (
        visible.filter(analysis_status=Sample.SUBMITTED_TO_QC)
        .select_related("submission", "lab_mapping")
        .order_by("-updated_at")
    )
    reassay = (
        visible.filter(analysis_status=Sample.REASSAY_SUBMITTED)
        .select_related("submission", "lab_mapping")
        .order_by("-updated_at")
    )
    approved = (
        visible.filter(analysis_status=Sample.QC_APPROVED)
        .select_related("submission", "lab_mapping")
        .order_by("-updated_at")
    )

    today = timezone.localdate()
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    per_day = dict(
        visible.filter(
            analysis_status__in=[
                Sample.SUBMITTED_TO_QC,
                Sample.REASSAY_SUBMITTED,
                Sample.QC_APPROVED,
            ],
            updated_at__date__gte=days[0],
        )
        .annotate(day=TruncDate("updated_at"))
        .order_by()
        .values("day")
        .annotate(total=Count("id"))
        .values_list("day", "total")
    )
    weekly_chart = [
        {"label": day.strftime("%a"), "count": per_day.get(day, 0)} for day in days
    ]

    context = {
        "pending_count": pending.count(),
        "reassay_count": reassay.count(),
        "approved_count": approved.count(),
        "pending_samples": _with_lab_id(pending[:5]),
        "reassay_samples": _with_lab_id(reassay[:5]),
        "approved_samples": _with_lab_id(approved[:5]),
        "weekly_chart": weekly_chart,
    }
    return render(request, "quantity_control/qc_dashboard.html", context)


def _sample_items(samples):
    return [
        {
            "sample": sample,
            "lab_id": lab_sample_id_for(sample),
            "submission": sample.submission,
        }
        for sample in samples
    ]


@qc_required
def pending_review(request):
    reference = request.GET.get("reference", "").strip()
    samples = (
        Sample.objects.filter(
            submission__is_submitted=True, analysis_status=Sample.SUBMITTED_TO_QC
        )
        .select_related("submission", "lab_mapping")
        .order_by("-updated_at", "-id")
    )

    if reference:
        samples = samples.filter(submission__reference__iexact=reference)

    page_obj, querystring = _paginate(request, samples)
    context = {
        "reference": reference,
        "items": _sample_items(page_obj.object_list),
        "page_obj": page_obj,
        "querystring": querystring,
        "total_count": samples.count(),
    }
    return render(request, "quantity_control/pending_review.html", context)


@qc_required
def reassay_review(request):
    reference = request.GET.get("reference", "").strip()
    samples = (
        Sample.objects.filter(
            submission__is_submitted=True,
            analysis_status=Sample.REASSAY_SUBMITTED,
        )
        .select_related("submission", "lab_mapping")
        .order_by("-updated_at", "-id")
    )

    if reference:
        samples = samples.filter(submission__reference__iexact=reference)

    page_obj, querystring = _paginate(request, samples)
    context = {
        "reference": reference,
        "items": _sample_items(page_obj.object_list),
        "page_obj": page_obj,
        "querystring": querystring,
        "total_count": samples.count(),
    }
    return render(request, "quantity_control/reassay_review.html", context)


@qc_required
def approved_reports(request):
    reference = request.GET.get("reference", "").strip()
    samples = (
        Sample.objects.filter(
            submission__is_submitted=True, analysis_status=Sample.QC_APPROVED
        )
        .select_related("submission", "lab_mapping")
        .order_by("-updated_at", "-id")
    )

    if reference:
        samples = samples.filter(submission__reference__iexact=reference)

    page_obj, querystring = _paginate(request, samples)
    context = {
        "reference": reference,
        "items": _sample_items(page_obj.object_list),
        "page_obj": page_obj,
        "querystring": querystring,
        "total_count": samples.count(),
    }
    return render(request, "quantity_control/approved_reports.html", context)


def _crm_entries_for_sample(sample):
    rows = worksheet_rows_for_sample(sample)
    if not rows:
        return []
    last = rows[-1]
    following = last.worksheet.rows.filter(row_number__gt=last.row_number).order_by(
        "row_number"
    )
    crm_rows = []
    for row in following:
        if row.row_type == WorksheetRow.BLANK_ROW:
            continue
        if row.row_type != WorksheetRow.CRM_ROW:
            break
        crm_rows.append(row)
    return [
        crm
        for crm in (
            CRMEntry.objects.filter(worksheet_row=row).first() for row in crm_rows
        )
        if crm is not None
    ]


def _apply_qc_defaults(qc_review, kind, entry):
    if entry is None:
        return
    if kind == "mineral":
        elements = entry.registered_elements
        replicates = list(entry.replicates.all())
        if elements["gold"]:
            golds = [r.gold_ppm for r in replicates if r.gold_ppm is not None]
            if len(golds) >= 1:
                qc_review.gold_test_1 = golds[0]
            if len(golds) >= 2:
                qc_review.gold_test_2 = golds[1]
        if elements["copper"]:
            coppers = [r.copper_ppm for r in replicates if r.copper_ppm is not None]
            if coppers:
                qc_review.copper_final = coppers[0]
        if elements["silver"]:
            silvers = [r.silver_ppm for r in replicates if r.silver_ppm is not None]
            if silvers:
                qc_review.silver_final = silvers[0]
        if elements["sulphur"]:
            sulphurs = [r.sulphur for r in replicates if r.sulphur is not None]
            if sulphurs:
                qc_review.sulphur_final = sulphurs[0]
    elif kind == "carbon":
        if entry.final_carbon_activity_percent is not None:
            qc_review.carbon_activity_final = entry.final_carbon_activity_percent


def _get_qc_review(sample, kind, entry):
    qc_review, _ = QCReview.objects.get_or_create(sample=sample)
    current_revision = entry.revision if entry is not None else None
    if qc_review.defaults_revision != current_revision:
        _apply_qc_defaults(qc_review, kind, entry)
        qc_review.defaults_revision = current_revision
        qc_review.save()
    return qc_review


def _parse_decimal(raw, label, errors):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        errors.append(f"{label}: enter a valid number.")
        return None
    if not value.is_finite() or value < 0:
        errors.append(f"{label}: enter a valid non-negative number.")
        return None
    return value


def _log_change(logs, sample, user, label, old, new):
    old_text = "" if old is None else str(old)
    new_text = "" if new is None else str(new)
    if old_text == new_text:
        return
    logs.append(
        QCEditLog(
            sample=sample,
            field_label=label,
            previous_value=old_text,
            new_value=new_text,
            edited_by=user,
        )
    )


def _save_mineral_edits(request, sample, entry, qc_review, user, logs, errors):
    elements = entry.registered_elements
    field_map = (
        ("gold", "gold_test_1", "qc_gold_test_1", "Gold Test 1 (ppm)"),
        ("gold", "gold_test_2", "qc_gold_test_2", "Gold Test 2 (ppm)"),
        ("copper", "copper_final", "qc_copper_final", "Copper (ppm)"),
        ("silver", "silver_final", "qc_silver_final", "Silver (ppm)"),
        ("sulphur", "sulphur_final", "qc_sulphur_final", "Sulphur (%)"),
    )
    for element, field_name, post_key, label in field_map:
        if not elements.get(element):
            continue
        old = getattr(qc_review, field_name)
        new = _parse_decimal(request.POST.get(post_key), label, errors)
        _log_change(logs, sample, user, label, old, new)
        setattr(qc_review, field_name, new)


def _save_carbon_edits(request, sample, entry, qc_review, user, logs, errors):
    old = qc_review.carbon_activity_final
    new = _parse_decimal(
        request.POST.get("qc_carbon_final"), "Carbon Activity (%)", errors
    )
    _log_change(logs, sample, user, "Carbon Activity (%)", old, new)
    qc_review.carbon_activity_final = new


def _save_metallurgical_edits(request, sample, entry, qc_review, user, logs, errors):
    period_fields = (
        ("show_recovery_12h", "Gold Recovery 12h — shown on COA"),
        ("show_recovery_24h", "Gold Recovery 24h — shown on COA"),
        ("show_recovery_48h", "Gold Recovery 48h — shown on COA"),
    )
    for field_name, label in period_fields:
        old = getattr(qc_review, field_name)
        new = request.POST.get(field_name) == "on"
        if new != old:
            logs.append(
                QCEditLog(
                    sample=sample,
                    field_label=label,
                    previous_value="Shown" if old else "Hidden",
                    new_value="Shown" if new else "Hidden",
                    edited_by=user,
                )
            )
        setattr(qc_review, field_name, new)

    rows = list(entry.rows.select_related("source_parameter"))
    for row in rows:
        prefix = f"row{row.id}"
        row_label = row.source_parameter.display_label
        changed = False

        wv_new = _parse_decimal(
            request.POST.get(f"{prefix}_weight_volume"),
            f"{row_label} Weight/Volume",
            errors,
        )
        if wv_new != row.weight_volume:
            _log_change(
                logs,
                sample,
                user,
                f"{row_label} — Weight/Volume",
                row.weight_volume,
                wv_new,
            )
            row.weight_volume = wv_new
            changed = True

        si_new = (request.POST.get(f"{prefix}_si_unit") or "").strip()
        if si_new != row.si_unit:
            _log_change(
                logs, sample, user, f"{row_label} — SI Unit", row.si_unit, si_new
            )
            row.si_unit = si_new
            changed = True

        for field_name, key, label in RECOVERY_FIELDS:
            new_val = _parse_decimal(
                request.POST.get(f"{prefix}_{key}"), f"{row_label} {label}", errors
            )
            old_val = getattr(row, field_name)
            if new_val != old_val:
                _log_change(
                    logs, sample, user, f"{row_label} — {label}", old_val, new_val
                )
                setattr(row, field_name, new_val)
                changed = True

        included_new = request.POST.get(f"{prefix}_included") == "on"
        if included_new != row.qc_included:
            _log_change(
                logs,
                sample,
                user,
                f"{row_label} — included on COA",
                "Yes" if row.qc_included else "No",
                "Yes" if included_new else "No",
            )
            row.qc_included = included_new
            changed = True

        remarks_new = (request.POST.get(f"{prefix}_remarks") or "").strip()
        if remarks_new != row.remarks:
            row.remarks = remarks_new
            changed = True

        if changed:
            row.save()


@qc_required
def sample_review(request, slug):
    sample = get_object_or_404(
        Sample.objects.filter(submission__is_submitted=True).select_related(
            "submission", "submission__client", "lab_mapping"
        ),
        slug=slug,
    )

    test_type = get_metallurgical_type(sample)
    kind = "mineral"
    entry = (
        MineralAnalysisEntry.objects.filter(sample=sample).order_by("-revision").first()
    )

    if test_type == Service.CARBON_ACTIVITY:
        kind = "carbon"
        entry = (
            CarbonActivityEntry.objects.filter(sample=sample)
            .order_by("-revision")
            .first()
        )
    elif test_type in (Service.CYANIDE_CONVENTIONAL, Service.CYANIDE_OPTIMIZATION):
        kind = "metallurgical"
        entry = (
            MetallurgicalTestEntry.objects.filter(sample=sample)
            .order_by("-revision")
            .first()
        )

    reviewable = sample.analysis_status in (
        Sample.SUBMITTED_TO_QC,
        Sample.REASSAY_SUBMITTED,
    )
    report_locked = COA.objects.filter(submission=sample.submission).exists()
    editable = (
        not report_locked
        and sample.analysis_status
        in (Sample.SUBMITTED_TO_QC, Sample.REASSAY_SUBMITTED, Sample.QC_APPROVED)
        and entry is not None
    )

    qc_review = _get_qc_review(sample, kind, entry)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "save_edits":
            if not editable:
                messages.error(request, "This sample can no longer be edited.")
                return redirect("qc:sample_review", slug=sample.slug)

            user = request.user if request.user.is_authenticated else None
            logs = []
            errors = []

            if kind == "mineral":
                _save_mineral_edits(
                    request, sample, entry, qc_review, user, logs, errors
                )
            elif kind == "carbon":
                _save_carbon_edits(
                    request, sample, entry, qc_review, user, logs, errors
                )
            elif kind == "metallurgical":
                _save_metallurgical_edits(
                    request, sample, entry, qc_review, user, logs, errors
                )

            if errors:
                for error in errors[:10]:
                    messages.error(request, error)
                return redirect("qc:sample_review", slug=sample.slug)

            with transaction.atomic():
                qc_review.updated_by = user
                qc_review.save()
                if logs:
                    QCEditLog.objects.bulk_create(logs)

            if logs:
                messages.success(request, f"QC edits saved ({len(logs)} change(s)).")
            else:
                messages.success(request, "No changes to save.")
            return redirect("qc:sample_review", slug=sample.slug)

        if not reviewable:
            messages.error(request, "This sample is not awaiting QC review.")
            return redirect("qc:sample_review", slug=sample.slug)

        if action == "approve":
            sample.set_analysis_status(Sample.QC_APPROVED)
            messages.success(request, f"{lab_sample_id_for(sample)} approved.")
            return redirect("qc:pending_review")
        if action == "return_reassay":
            sample.set_analysis_status(Sample.REASSAY_REQUIRED)
            messages.success(
                request, f"{lab_sample_id_for(sample)} returned for reassay."
            )
            return redirect("qc:pending_review")

        messages.error(request, "Unknown action.")
        return redirect("qc:sample_review", slug=sample.slug)

    services = (
        sample.sample_services.select_related("service")
        .prefetch_related("parameters")
        .all()
    )
    edit_logs = sample.qc_edit_logs.select_related("edited_by")[:20]

    context = {
        "sample": sample,
        "lab_id": lab_sample_id_for(sample),
        "kind": kind,
        "entry": entry,
        "services": services,
        "reviewable": reviewable,
        "editable": editable,
        "report_locked": report_locked,
        "qc_review": qc_review,
        "edit_logs": edit_logs,
        "is_reassay": sample.analysis_status
        in (Sample.REASSAY_REQUIRED, Sample.REASSAY_SUBMITTED)
        or (entry.is_reassay if entry else False),
    }

    if kind == "mineral" and entry is not None:
        context["elements"] = entry.registered_elements
        context["replicates"] = entry.replicates.all()
        context["crm_entries"] = _crm_entries_for_sample(sample)
    elif kind == "metallurgical" and entry is not None:
        context["rows"] = entry.rows.select_related("source_parameter").all()
    elif kind == "carbon" and entry is not None:
        context["replicates"] = entry.replicates.all()

    return render(request, "quantity_control/sample_review.html", context)


@qc_required
def generated_reports(request):
    reference = request.GET.get("reference", "").strip()
    coas = COA.objects.select_related("submission", "group").order_by("-created_at")

    if reference:
        coas = coas.filter(submission__reference__iexact=reference)

    page_obj, querystring = _paginate(request, coas)
    context = {
        "reference": reference,
        "items": list(page_obj.object_list),
        "page_obj": page_obj,
        "querystring": querystring,
        "total_count": coas.count(),
    }
    return render(request, "quantity_control/generated_reports.html", context)


@qc_required
def report_detail(request, reference):
    submission = get_object_or_404(
        Submission.objects.filter(
            is_submitted=True, reference__iexact=reference
        ).select_related("client")
    )
    samples = list(submission.samples.select_related("lab_mapping").order_by("id"))
    coa = (
        COA.objects.filter(submission=submission)
        .select_related("group", "approved_by")
        .first()
    )
    context = {
        "submission": submission,
        "samples": samples,
        "coa": coa,
    }
    return render(request, "quantity_control/report_detail.html", context)
