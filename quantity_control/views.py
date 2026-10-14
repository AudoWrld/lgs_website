import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from types import SimpleNamespace

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageFilter

from accounts.decorators import qc_required
from coa.models import COA
from coa.services import attach_files, sample_has_coa, sync_coas
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

from .models import QCDecision, QCEditLog, QCReview

logger = logging.getLogger(__name__)

PAGE_SIZE = 12
DECIMAL_PLACES = Decimal("0.0001")
MAX_VALUE = Decimal("99999999")

OVERDUE_HOURS = getattr(settings, "QC_OVERDUE_HOURS", 4)
COA_NUMBER_FIELD = "coa_number"

REVIEW_STATUSES = (Sample.SUBMITTED_TO_QC, Sample.REASSAY_SUBMITTED)

KIND_ORDER = ("metallurgical", "carbon", "mineral")
KIND_LABELS = {
    "metallurgical": "Cyanide leaching",
    "carbon": "Carbon activity",
    "mineral": "Mineral analysis",
}

RECOVERY_FIELDS = (
    ("gold_recovery_12h", "recovery_12h", "Gold Recovery 12h", "show_recovery_12h"),
    ("gold_recovery_24h", "recovery_24h", "Gold Recovery 24h", "show_recovery_24h"),
    ("gold_recovery_48h", "recovery_48h", "Gold Recovery 48h", "show_recovery_48h"),
    ("gold_recovery_72h", "recovery_72h", "Gold Recovery 72h", "show_recovery_72h"),
)

SINGLE_FIELDS = (
    ("copper", "copper_final", "qc_copper_final", "Copper (ppm)"),
    ("silver", "silver_final", "qc_silver_final", "Silver (ppm)"),
    ("sulphur", "sulphur_final", "qc_sulphur_final", "Sulphur (%)"),
)


def _paginate(request, queryset):
    page = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()


def _with_lab_id(queryset):
    return [
        SimpleNamespace(sample=sample, lab_id=lab_sample_id_for(sample))
        for sample in queryset
    ]


def _sample_items(samples):
    return [
        {
            "sample": sample,
            "lab_id": lab_sample_id_for(sample),
            "submission": sample.submission,
        }
        for sample in samples
    ]


def _latest(model, sample):
    return model.objects.filter(sample=sample).order_by("-revision").first()


def _all_entries(sample):
    return {
        "metallurgical": _latest(MetallurgicalTestEntry, sample),
        "carbon": _latest(CarbonActivityEntry, sample),
        "mineral": _latest(MineralAnalysisEntry, sample),
    }


def _kinds_for(sample):
    entries = _all_entries(sample)
    return [kind for kind in KIND_ORDER if entries[kind] is not None]


def _load_entry(sample):
    test_type = get_metallurgical_type(sample)
    if test_type == Service.CARBON_ACTIVITY:
        return "carbon", _latest(CarbonActivityEntry, sample)
    if test_type in (Service.CYANIDE_CONVENTIONAL, Service.CYANIDE_OPTIMIZATION):
        return "metallurgical", _latest(MetallurgicalTestEntry, sample)
    return "mineral", _latest(MineralAnalysisEntry, sample)


def _select_entry(sample, requested=None):
    entries = _all_entries(sample)
    if requested in entries and entries[requested] is not None:
        return requested, entries[requested]
    for kind in KIND_ORDER:
        if entries[kind] is not None:
            return kind, entries[kind]
    return _load_entry(sample)


def _approved_kinds(sample):
    value = (
        QCReview.objects.filter(sample=sample)
        .values_list("approved_kinds", flat=True)
        .first()
    )
    return list(value or [])


def _review_items(samples, pending_only=False):
    items = []
    for sample in samples:
        lab_id = lab_sample_id_for(sample)
        entries = _all_entries(sample)
        done = _approved_kinds(sample)
        kinds = [kind for kind in KIND_ORDER if entries[kind] is not None]
        if pending_only:
            kinds = [kind for kind in kinds if kind not in done]
        for kind in kinds or ([] if pending_only else [None]):
            entry = entries.get(kind) if kind else None
            items.append(
                {
                    "sample": sample,
                    "lab_id": lab_id,
                    "submission": sample.submission,
                    "kind": kind or "",
                    "kind_label": KIND_LABELS.get(kind, ""),
                    "is_reassay": bool(entry and entry.is_reassay),
                }
            )
    return items


def _fmt(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


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
    if value > MAX_VALUE:
        errors.append(f"{label}: value is too large.")
        return None
    return value.quantize(DECIMAL_PLACES)


def _report_locked(sample):
    if getattr(sample, "submission_id", None) is None:
        return False
    if sample.analysis_status != Sample.QC_APPROVED:
        return False
    return sample_has_coa(sample)


def _is_editable(sample, entry):
    return (
        entry is not None
        and sample.analysis_status in (Sample.SUBMITTED_TO_QC, Sample.REASSAY_SUBMITTED)
        and not _report_locked(sample)
    )


def _apply_qc_defaults(qc_review, entries):
    qc_review.gold_test_1 = None
    qc_review.gold_test_2 = None
    qc_review.gold_replicate_1_id = None
    qc_review.gold_replicate_2_id = None
    qc_review.copper_final = None
    qc_review.silver_final = None
    qc_review.sulphur_final = None
    qc_review.carbon_activity_final = None
    qc_review.metallurgical_original = None

    mineral = entries["mineral"]
    if mineral is not None:
        elements = mineral.registered_elements
        replicates = list(mineral.replicates.all())
        if elements["gold"]:
            golds = [(r.id, r.gold_ppm) for r in replicates if r.gold_ppm is not None]
            if len(golds) >= 1:
                qc_review.gold_replicate_1_id, qc_review.gold_test_1 = golds[0]
            if len(golds) >= 2:
                qc_review.gold_replicate_2_id, qc_review.gold_test_2 = golds[1]
        if elements["copper"]:
            values = [r.copper_ppm for r in replicates if r.copper_ppm is not None]
            qc_review.copper_final = values[0] if values else None
        if elements["silver"]:
            values = [r.silver_ppm for r in replicates if r.silver_ppm is not None]
            qc_review.silver_final = values[0] if values else None
        if elements["sulphur"]:
            values = [r.sulphur for r in replicates if r.sulphur is not None]
            qc_review.sulphur_final = values[0] if values else None

    carbon = entries["carbon"]
    if carbon is not None:
        qc_review.carbon_activity_final = carbon.final_carbon_activity_percent


def _get_qc_review(sample, kind=None, entry=None):
    qc_review, _ = QCReview.objects.get_or_create(sample=sample)
    entries = _all_entries(sample)
    revision = sum(e.revision for e in entries.values() if e is not None) or None
    if qc_review.defaults_revision != revision:
        _apply_qc_defaults(qc_review, entries)
        qc_review.defaults_revision = revision
        qc_review.save()
    return qc_review


class _Edit:
    def __init__(self, request, sample, user, revision):
        self.request = request
        self.sample = sample
        self.user = user
        self.revision = revision
        self.logs = []
        self.errors = []
        self.rows_to_save = []

    def has(self, key):
        return key in self.request.POST

    def decimal(self, key, label):
        return _parse_decimal(self.request.POST.get(key), label, self.errors)

    def log(self, label, old, new):
        if old == new:
            return False
        self.logs.append(
            QCEditLog(
                sample=self.sample,
                entry_revision=self.revision,
                field_label=label,
                previous_value=_fmt(old),
                new_value=_fmt(new),
                edited_by=self.user,
            )
        )
        return True


def _edit_gold_slot(edit, qc_review, slot, replicates, labels):
    id_field = f"gold_replicate_{slot}_id"
    value_field = f"gold_test_{slot}"
    label = f"Gold Test {slot} (ppm)"
    pick_key = f"qc_gold_replicate_{slot}"
    value_key = f"qc_gold_test_{slot}"

    if not edit.has(pick_key) and not edit.has(value_key):
        return

    old_value = getattr(qc_review, value_field)
    old_id = getattr(qc_review, id_field)
    new_id = old_id

    raw_pick = (edit.request.POST.get(pick_key) or "").strip()
    if raw_pick:
        try:
            candidate = int(raw_pick)
        except ValueError:
            candidate = None
        replicate = replicates.get(candidate)
        if replicate is None or replicate.gold_ppm is None:
            edit.errors.append(f"{label}: choose a valid replicate.")
        else:
            new_id = candidate

    if new_id != old_id:
        new_value = replicates[new_id].gold_ppm
        edit.log(
            f"Gold Test {slot} — source replicate",
            labels.get(old_id, "") if old_id else "",
            labels.get(new_id, ""),
        )
        setattr(qc_review, id_field, new_id)
    else:
        new_value = edit.decimal(value_key, label) if edit.has(value_key) else old_value

    edit.log(label, old_value, new_value)
    setattr(qc_review, value_field, new_value)


def _save_mineral_edits(edit, entry, qc_review):
    elements = entry.registered_elements
    replicate_list = list(entry.replicates.all())
    replicates = {r.id: r for r in replicate_list}
    labels = {r.id: f"Replicate {i}" for i, r in enumerate(replicate_list, 1)}

    if elements.get("gold"):
        for slot in (1, 2):
            _edit_gold_slot(edit, qc_review, slot, replicates, labels)
        id_1, id_2 = qc_review.gold_replicate_1_id, qc_review.gold_replicate_2_id
        if id_1 is not None and id_1 == id_2:
            edit.errors.append(
                "Gold Test 1 and Gold Test 2 must come from different replicates."
            )

    for element, field_name, post_key, label in SINGLE_FIELDS:
        if not elements.get(element) or not edit.has(post_key):
            continue
        new = edit.decimal(post_key, label)
        edit.log(label, getattr(qc_review, field_name), new)
        setattr(qc_review, field_name, new)


def _save_carbon_edits(edit, entry, qc_review):
    if not edit.has("qc_carbon_final"):
        return
    new = edit.decimal("qc_carbon_final", "Carbon Activity (%)")
    edit.log("Carbon Activity (%)", qc_review.carbon_activity_final, new)
    qc_review.carbon_activity_final = new


def _snapshot_metallurgical(entry, qc_review):
    if qc_review.metallurgical_original is not None:
        return
    qc_review.metallurgical_original = [
        {
            "row_id": row.id,
            "parameter": row.source_parameter.display_label,
            "weight_volume": _fmt(row.weight_volume),
            "si_unit": row.si_unit,
            "gold_recovery_12h": _fmt(row.gold_recovery_12h),
            "gold_recovery_24h": _fmt(row.gold_recovery_24h),
            "gold_recovery_48h": _fmt(row.gold_recovery_48h),
            "gold_recovery_72h": _fmt(row.gold_recovery_72h),
            "remarks": row.remarks,
            "qc_included": row.qc_included,
        }
        for row in entry.rows.select_related("source_parameter")
    ]


def _save_metallurgical_edits(edit, entry, qc_review):
    _snapshot_metallurgical(entry, qc_review)

    for _row_field, _key, label, flag in RECOVERY_FIELDS:
        old = getattr(qc_review, flag)
        new = edit.request.POST.get(flag) == "on"
        edit.log(
            f"{label} — shown on COA",
            "Shown" if old else "Hidden",
            "Shown" if new else "Hidden",
        )
        setattr(qc_review, flag, new)

    for row in entry.rows.select_related("source_parameter"):
        prefix = f"row{row.id}"
        if not edit.has(f"{prefix}_weight_volume"):
            continue
        row_label = row.source_parameter.display_label
        changed = False

        weight_new = edit.decimal(
            f"{prefix}_weight_volume", f"{row_label} Weight/Volume"
        )
        if edit.log(f"{row_label} — Weight/Volume", row.weight_volume, weight_new):
            row.weight_volume = weight_new
            changed = True

        unit_new = (edit.request.POST.get(f"{prefix}_si_unit") or "").strip()
        if edit.log(f"{row_label} — SI Unit", row.si_unit, unit_new):
            row.si_unit = unit_new
            changed = True

        for field_name, key, label, _flag in RECOVERY_FIELDS:
            new_val = edit.decimal(f"{prefix}_{key}", f"{row_label} {label}")
            if edit.log(f"{row_label} — {label}", getattr(row, field_name), new_val):
                setattr(row, field_name, new_val)
                changed = True

        included_new = edit.request.POST.get(f"{prefix}_included") == "on"
        if edit.log(
            f"{row_label} — included on COA",
            "Yes" if row.qc_included else "No",
            "Yes" if included_new else "No",
        ):
            row.qc_included = included_new
            changed = True

        remarks_new = (edit.request.POST.get(f"{prefix}_remarks") or "").strip()
        if edit.log(f"{row_label} — Remarks", row.remarks, remarks_new):
            row.remarks = remarks_new
            changed = True

        if changed:
            edit.rows_to_save.append(row)


def _apply_edits(request, sample, kind, entry, qc_review, user):
    edit = _Edit(request, sample, user, entry.revision)
    if kind == "mineral":
        _save_mineral_edits(edit, entry, qc_review)
    elif kind == "carbon":
        _save_carbon_edits(edit, entry, qc_review)
    elif kind == "metallurgical":
        _save_metallurgical_edits(edit, entry, qc_review)
    return edit


def _commit_edits(edit, qc_review, user):
    for row in edit.rows_to_save:
        row.save()
    qc_review.updated_by = user
    qc_review.save()
    if edit.logs:
        QCEditLog.objects.bulk_create(edit.logs)


def _approval_errors(kind, entry, qc_review):
    if entry is None:
        return ["No submitted data was found for this sample."]
    errors = []
    prefix = f"{KIND_LABELS.get(kind, kind)}: "

    if kind == "mineral":
        elements = entry.registered_elements
        if elements.get("gold"):
            if qc_review.gold_test_1 is None:
                errors.append(f"{prefix}Gold Test 1 (ppm) is required.")
            if qc_review.gold_test_2 is None:
                errors.append(f"{prefix}Gold Test 2 (ppm) is required.")
        for element, field_name, _key, label in SINGLE_FIELDS:
            if elements.get(element) and getattr(qc_review, field_name) is None:
                errors.append(f"{prefix}{label} is required.")
    elif kind == "carbon":
        if qc_review.carbon_activity_final is None:
            errors.append(f"{prefix}Carbon Activity (%) is required.")
    elif kind == "metallurgical":
        rows = [
            r for r in entry.rows.select_related("source_parameter") if r.qc_included
        ]
        if not rows:
            errors.append(f"{prefix}Include at least one parameter on the COA.")
        for row in rows:
            label = row.source_parameter.display_label
            if row.weight_volume is None or row.weight_volume <= 0:
                errors.append(f"{prefix}{label}: Weight / Volume is required.")
            if not row.si_unit:
                errors.append(f"{prefix}{label}: SI Unit is required.")
    return errors


def _flash_errors(request, errors):
    for error in errors[:10]:
        messages.error(request, error)


def _auto_generate_coas(request, submission, sample):
    try:
        coas = sync_coas(
            submission,
            request.user,
            base_url=request.build_absolute_uri("/"),
            sample=sample,
        )
    except ValidationError as exc:
        for message in exc.messages:
            messages.warning(request, message)
        return
    except Exception:
        logger.exception("Automatic COA generation failed for %s", submission.reference)
        messages.warning(
            request,
            "Sample approved, but the COA could not be generated automatically.",
        )
        return

    if not coas:
        return

    numbers = ", ".join(c.coa_number for c in coas)
    messages.success(request, f"COA created or updated: {numbers}.")

    if not getattr(settings, "COA_BUILD_IN_BACKGROUND", True) and any(
        not c.pdf_file or not c.png_file for c in coas
    ):
        messages.warning(
            request,
            "COA saved but some files failed to build. "
            "Use “Rebuild files” on the report page.",
        )


def _review_redirect(sample, kind):
    url = reverse("qc:sample_review", kwargs={"slug": sample.slug})
    if kind:
        url = f"{url}?kind={kind}"
    return HttpResponseRedirect(url)


def _handle_post(request, sample, kind, entry):
    action = request.POST.get("action")
    back = _review_redirect(sample, kind)
    user = request.user if request.user.is_authenticated else None

    if action not in ("save_edits", "approve", "return_reassay"):
        messages.error(request, "Unknown action.")
        return back

    fully_approved = False
    required = []

    with transaction.atomic():
        locked = Sample.objects.select_for_update().get(pk=sample.pk)
        qc_review = QCReview.objects.select_for_update().get(sample=locked)
        approved_kinds = list(qc_review.approved_kinds or [])

        if action == "save_edits":
            if kind in approved_kinds or not _is_editable(locked, entry):
                messages.error(request, "This service can no longer be edited.")
                return back
            edit = _apply_edits(request, locked, kind, entry, qc_review, user)
            if edit.errors:
                _flash_errors(request, edit.errors)
                return back
            _commit_edits(edit, qc_review, user)
            if edit.logs:
                messages.success(
                    request, f"QC edits saved ({len(edit.logs)} change(s))."
                )
            else:
                messages.success(request, "No changes to save.")
            return back

        if locked.analysis_status not in REVIEW_STATUSES:
            messages.error(request, "This sample is not awaiting QC review.")
            return back

        if action == "return_reassay":
            qc_review.approved_kinds = []
            qc_review.save(update_fields=["approved_kinds", "updated_at"])
            locked.set_analysis_status(Sample.REASSAY_REQUIRED)
            QCDecision.objects.create(
                sample=locked,
                action=QCDecision.RETURNED,
                entry_revision=entry.revision if entry else None,
                decided_by=user,
            )
            messages.success(
                request, f"{lab_sample_id_for(sample)} returned for reassay."
            )
            return redirect("qc:pending_review")

        if kind in approved_kinds:
            messages.info(request, "This service is already approved.")
            return back

        if request.POST.get("edit_form") == "1":
            if not _is_editable(locked, entry):
                messages.error(request, "This sample can no longer be edited.")
                return back
            edit = _apply_edits(request, locked, kind, entry, qc_review, user)
            if edit.errors:
                _flash_errors(request, edit.errors)
                return back
            _commit_edits(edit, qc_review, user)

        problems = _approval_errors(kind, entry, qc_review)
        if problems:
            _flash_errors(request, problems)
            return back

        approved_kinds.append(kind)
        qc_review.approved_kinds = [k for k in KIND_ORDER if k in approved_kinds]
        qc_review.save(update_fields=["approved_kinds", "updated_at"])

        QCDecision.objects.create(
            sample=locked,
            action=QCDecision.APPROVED,
            reason=f"{KIND_LABELS.get(kind, kind)} approved",
            entry_revision=entry.revision if entry else None,
            decided_by=user,
        )

        required = _kinds_for(locked)
        fully_approved = all(k in qc_review.approved_kinds for k in required)
        if fully_approved:
            locked.set_analysis_status(Sample.QC_APPROVED)
        else:
            remaining = [
                KIND_LABELS[k] for k in required if k not in qc_review.approved_kinds
            ]

    if not fully_approved:
        messages.success(
            request,
            f"{KIND_LABELS.get(kind, kind)} approved. "
            f"Still to approve: {', '.join(remaining)}.",
        )
        return redirect("qc:pending_review")

    messages.success(request, f"{lab_sample_id_for(sample)} approved.")
    _auto_generate_coas(request, sample.submission, sample)
    return redirect("qc:pending_review")


@qc_required
def qc_dashboard(request):
    visible = Sample.objects.filter(submission__is_submitted=True)
    cutoff = timezone.now() - timedelta(hours=OVERDUE_HOURS)

    def base(**filters):
        return (
            visible.filter(**filters)
            .select_related("submission", "lab_mapping")
            .order_by("-updated_at", "-id")
        )

    pending = base(analysis_status=Sample.SUBMITTED_TO_QC)
    reassay = base(analysis_status=Sample.REASSAY_SUBMITTED)
    approved = base(analysis_status=Sample.QC_APPROVED)
    overdue = base(analysis_status__in=REVIEW_STATUSES, updated_at__lt=cutoff)

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
        "overdue_count": overdue.count(),
        "generated_coa_count": COA.objects.count(),
        "pending_samples": _with_lab_id(pending[:5]),
        "reassay_samples": _with_lab_id(reassay[:5]),
        "approved_samples": _with_lab_id(approved[:5]),
        "overdue_samples": _with_lab_id(overdue[:5]),
        "overdue_hours": OVERDUE_HOURS,
        "weekly_chart": weekly_chart,
    }
    return render(request, "quantity_control/qc_dashboard.html", context)


def _status_list(
    request, template, statuses, extra=None, expand=False, pending_only=False
):
    reference = request.GET.get("reference", "").strip()
    samples = (
        Sample.objects.filter(
            submission__is_submitted=True, analysis_status__in=statuses
        )
        .select_related("submission", "lab_mapping")
        .annotate(latest_activity=Max("submission__samples__updated_at"))
        .order_by("-latest_activity", "-submission_id", "id")
    )
    if extra is not None:
        samples = samples.filter(extra)
    if reference:
        samples = samples.filter(submission__reference__iexact=reference)

    page_obj, querystring = _paginate(request, samples)
    if expand:
        items = _review_items(page_obj.object_list, pending_only=pending_only)
    else:
        items = _sample_items(page_obj.object_list)

    context = {
        "reference": reference,
        "items": items,
        "page_obj": page_obj,
        "querystring": querystring,
        "total_count": samples.count(),
    }
    return render(request, template, context)


@qc_required
def pending_review(request):
    return _status_list(
        request,
        "quantity_control/pending_review.html",
        (Sample.SUBMITTED_TO_QC,),
        expand=True,
        pending_only=True,
    )


@qc_required
def reassay_review(request):
    return _status_list(
        request,
        "quantity_control/reassay_review.html",
        (Sample.REASSAY_SUBMITTED,),
        expand=True,
        pending_only=True,
    )


@qc_required
def approved_reports(request):
    return _status_list(
        request,
        "quantity_control/approved_reports.html",
        (Sample.QC_APPROVED,),
        expand=True,
    )


@qc_required
def generate_report(request):
    return redirect("qc:generated_reports")


@qc_required
def overdue_results(request):
    cutoff = timezone.now() - timedelta(hours=OVERDUE_HOURS)
    return _status_list(
        request,
        "quantity_control/pending_review.html",
        REVIEW_STATUSES,
        extra=Q(updated_at__lt=cutoff),
        expand=True,
        pending_only=True,
    )


@qc_required
def quick_search(request):
    query = request.GET.get("q", "").strip()
    if not query:
        return redirect("qc:qc_dashboard")

    coa = (
        COA.objects.filter(**{f"{COA_NUMBER_FIELD}__iexact": query})
        .select_related("submission")
        .first()
    )
    if coa is not None:
        return redirect("qc:report_detail", reference=coa.submission.reference)

    submission = Submission.objects.filter(
        is_submitted=True, reference__iexact=query
    ).first()
    if submission is not None:
        return redirect("qc:report_detail", reference=submission.reference)

    matches = list(
        Sample.objects.filter(
            submission__is_submitted=True,
            lab_mapping__lab_sample_id__icontains=query,
        )[:2]
    )
    if len(matches) == 1:
        return redirect("qc:sample_review", slug=matches[0].slug)
    if len(matches) > 1:
        messages.info(request, "Several samples match. Enter the full Laboratory ID.")
    else:
        messages.error(request, f"Nothing found for “{query}”.")
    return redirect("qc:qc_dashboard")


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


@qc_required
def sample_review(request, slug):
    sample = get_object_or_404(
        Sample.objects.filter(submission__is_submitted=True).select_related(
            "submission", "submission__client", "lab_mapping"
        ),
        slug=slug,
    )

    requested = request.POST.get("kind") or request.GET.get("kind")
    kind, entry = _select_entry(sample, requested)
    qc_review = _get_qc_review(sample, kind, entry)

    if request.method == "POST":
        return _handle_post(request, sample, kind, entry)

    approved_kinds = list(qc_review.approved_kinds or [])
    kind_approved = kind in approved_kinds

    reviewable = sample.analysis_status in REVIEW_STATUSES and not kind_approved
    report_locked = _report_locked(sample)
    editable = _is_editable(sample, entry) and not kind_approved

    services = (
        sample.sample_services.select_related("service")
        .prefetch_related("parameters")
        .all()
    )

    context = {
        "sample": sample,
        "lab_id": lab_sample_id_for(sample),
        "kind": kind,
        "kinds": [{"key": k, "label": KIND_LABELS[k]} for k in _kinds_for(sample)],
        "approved_kinds": approved_kinds,
        "kind_approved": kind_approved,
        "entry": entry,
        "services": services,
        "reviewable": reviewable,
        "editable": editable,
        "report_locked": report_locked,
        "qc_review": qc_review,
        "edit_logs": sample.qc_edit_logs.select_related("edited_by")[:20],
        "decisions": sample.qc_decisions.select_related("decided_by")[:10],
        "is_reassay": sample.analysis_status
        in (Sample.REASSAY_REQUIRED, Sample.REASSAY_SUBMITTED)
        or (entry.is_reassay if entry else False),
    }

    if kind == "mineral" and entry is not None:
        replicates = list(entry.replicates.all())
        context["elements"] = entry.registered_elements
        context["replicates"] = replicates
        context["gold_options"] = [
            {"id": r.id, "label": f"Replicate {i}", "gold_ppm": r.gold_ppm}
            for i, r in enumerate(replicates, 1)
            if r.gold_ppm is not None
        ]
        context["crm_entries"] = _crm_entries_for_sample(sample)
    elif kind == "metallurgical" and entry is not None:
        context["rows"] = entry.rows.select_related("source_parameter").all()
        context["original_rows"] = qc_review.metallurgical_original or []
    elif kind == "carbon" and entry is not None:
        context["replicates"] = entry.replicates.all()

    return render(request, "quantity_control/sample_review.html", context)


@qc_required
def generated_reports(request):
    reference = request.GET.get("reference", "").strip()
    coas = COA.objects.select_related("submission", "group").order_by(
        "-created_at", "-id"
    )

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
    coas = list(
        COA.objects.filter(submission=submission)
        .select_related("group", "approved_by")
        .order_by("coa_number")
    )

    if request.method == "POST" and request.POST.get("action") == "rebuild_files":
        rebuilt = 0
        for coa in coas:
            if coa.pdf_file and coa.png_file:
                continue
            try:
                attach_files(coa, base_url=request.build_absolute_uri("/"))
                rebuilt += 1
            except Exception:
                logger.exception("COA file rebuild failed for %s", coa.coa_number)
                messages.error(
                    request, f"Could not rebuild files for {coa.coa_number}."
                )
        if rebuilt:
            messages.success(request, f"Rebuilt files for {rebuilt} COA(s).")
        return redirect("qc:report_detail", reference=submission.reference)

    entries = [
        {
            "coa": coa,
            "samples": (
                _sample_items(
                    coa.group.samples.select_related("submission").order_by("id")
                )
                if coa.group_id
                else []
            ),
            "files_ready": bool(coa.pdf_file and coa.png_file),
            "preview_ready": bool(coa.png_file),
            "released": coa.is_client_visible,
        }
        for coa in coas
    ]
    samples = list(submission.samples.select_related("submission").order_by("id"))
    context = {
        "submission": submission,
        "sample_items": _sample_items(samples),
        "entries": entries,
        "has_missing_files": any(not e["files_ready"] for e in entries),
        "payment_pending": any(not e["released"] for e in entries),
        "all_ready": bool(entries) and all(e["released"] for e in entries),
    }
    return render(request, "quantity_control/report_detail.html", context)


@qc_required
def report_coa_preview(request, coa_id):
    coa = get_object_or_404(COA, pk=coa_id, submission__is_submitted=True)
    if not coa.png_file:
        raise Http404

    if not coa.is_client_visible:
        with coa.png_file.open("rb") as source:
            image = Image.open(source)
            image.load()
        preview = image.filter(ImageFilter.GaussianBlur(radius=12))
        output = BytesIO()
        preview.save(output, format="PNG")
        response = HttpResponse(output.getvalue(), content_type="image/png")
    else:
        response = FileResponse(
            coa.png_file.open("rb"),
            content_type="image/png",
        )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@qc_required
def report_coa_file(request, pk, kind):
    coa = get_object_or_404(COA, pk=pk)
    if kind == "pdf":
        field, content_type = coa.pdf_file, "application/pdf"
    elif kind == "png":
        field, content_type = coa.png_file, "image/png"
    else:
        raise Http404
    if not field:
        raise Http404
    return FileResponse(
        field.open("rb"),
        content_type=content_type,
        as_attachment=request.GET.get("download") == "1",
        filename=f"{coa.coa_number.replace('/', '-')}.{kind}",
    )
