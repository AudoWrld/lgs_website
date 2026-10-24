from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import chemist_required
from samples.models import Sample, Service
from submissions.models import Submission
from worksheet.models import Worksheet, WorksheetRow

from .models import (
    CYANIDE_TYPES,
    METALLURGICAL_TYPES,
    CarbonActivityEntry,
    CRMEntry,
    MetallurgicalTestEntry,
    MineralAnalysisEntry,
    _quantize,
    format_lab_sample_id,
    get_metallurgical_type,
    lab_sample_id_for,
    latest_carbon_worksheet,
    latest_mineral_worksheet,
    mineral_worksheets,
    worksheet_elements,
    worksheet_rows_for_sample,
)

MINERAL_FIELDS = (
    ("weight", "Weight"),
    ("au_aas", "Au AAS"),
    ("au_df", "Au DF"),
    ("cu_aas", "Cu AAS"),
    ("cu_df", "Cu DF"),
    ("ag_aas", "Ag AAS"),
    ("ag_df", "Ag DF"),
    ("sulphur", "S"),
)

METALLURGICAL_FIELDS = (
    ("weight_volume", "weight_volume", "Weight / Volume"),
    ("gold_recovery_12h", "recovery_12h", "Gold recovery at 12 hours"),
    ("gold_recovery_24h", "recovery_24h", "Gold recovery at 24 hours"),
    ("gold_recovery_48h", "recovery_48h", "Gold recovery at 48 hours"),
    ("gold_recovery_72h", "recovery_72h", "Gold recovery at 72 hours"),
)

CARBON_FIELDS = (
    ("standard_concentration", "standard", "Standard concentration"),
    ("final_concentration_sample", "final_sample", "Final concentration in sample"),
    (
        "final_concentration_standard",
        "final_standard",
        "Final carbon in Standard concentration",
    ),
)

MINERAL_ROUTE = "chemist:mineral_analysis_entry"
CYANIDE_ROUTE = "chemist:metallurgical_tests_entry"
CARBON_ROUTE = "chemist:carbon_activity_entry"

MINERAL_LIST_ROUTE = "chemist:mineral_analysis_samples"
METALLURGICAL_LIST_ROUTE = "chemist:metallurgical_tests_samples"

ROUTE_LABELS = {
    MINERAL_ROUTE: "Mineral analysis",
    CYANIDE_ROUTE: "Cyanide leaching",
    CARBON_ROUTE: "Carbon activity",
}

SECTION_LISTS = {
    MINERAL_ROUTE: MINERAL_LIST_ROUTE,
    CYANIDE_ROUTE: METALLURGICAL_LIST_ROUTE,
    CARBON_ROUTE: METALLURGICAL_LIST_ROUTE,
}

SECTION_LABELS = {
    MINERAL_LIST_ROUTE: "mineral analysis",
    METALLURGICAL_LIST_ROUTE: "metallurgical tests",
}

ENTRY_MODELS = {
    MINERAL_ROUTE: MineralAnalysisEntry,
    CYANIDE_ROUTE: MetallurgicalTestEntry,
    CARBON_ROUTE: CarbonActivityEntry,
}

MAX_REPORTED_ERRORS = 10
PAGE_SIZE = 10


class _PostReader:
    def __init__(self, data):
        self.data = data
        self.errors = []

    def decimal(self, key, label):
        raw = (self.data.get(key) or "").strip()
        if not raw:
            return None
        try:
            value = Decimal(raw)
        except InvalidOperation:
            self.errors.append(f"{label} must be a valid number.")
            return None
        if not value.is_finite():
            self.errors.append(f"{label} must be a valid number.")
            return None
        return value

    def text(self, key):
        return (self.data.get(key) or "").strip()


def _check(reader, instance, label):
    try:
        instance.clean_fields(
            exclude=[
                "entry",
                "source_parameter",
                "worksheet_row",
                *instance.RESULT_FIELDS,
            ]
        )
    except ValidationError as exc:
        for field, field_errors in exc.message_dict.items():
            name = str(instance._meta.get_field(field).verbose_name).capitalize()
            for message in field_errors:
                reader.errors.append(f"{label} {name}: {message}")


def _report_errors(request, errors):
    for error in errors[:MAX_REPORTED_ERRORS]:
        messages.error(request, error)
    remaining = len(errors) - MAX_REPORTED_ERRORS
    if remaining > 0:
        messages.error(request, f"{remaining} more error(s) not shown.")


def _paginate(request, queryset):
    page = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()


def _branch(request):
    return request.user.branch


def _visible_samples(request):
    return Sample.objects.filter(
        submission__is_submitted=True,
        submission__branch=_branch(request),
    )


def _get_sample(request, slug):
    return get_object_or_404(_visible_samples(request), slug=slug)


def _find_submission(request, reference):
    return Submission.objects.filter(
        branch=_branch(request),
        reference__iexact=reference,
        is_submitted=True,
    ).first()


def _route_name(sample):
    test_type = get_metallurgical_type(sample)
    if test_type == Service.CARBON_ACTIVITY:
        return CARBON_ROUTE
    if test_type in CYANIDE_TYPES:
        return CYANIDE_ROUTE
    return MINERAL_ROUTE


def _kinds(sample):
    kinds = set()
    for line in sample.sample_services.select_related("service"):
        kind = line.service.metallurgical_type
        kinds.add(kind if kind else Service.NONE)
    return kinds


def _routes(sample):
    kinds = _kinds(sample)
    routes = []
    if Service.NONE in kinds:
        routes.append(MINERAL_ROUTE)
    if any(kind in CYANIDE_TYPES for kind in kinds):
        routes.append(CYANIDE_ROUTE)
    if Service.CARBON_ACTIVITY in kinds:
        routes.append(CARBON_ROUTE)
    if not routes:
        routes.append(_route_name(sample))
    return routes


def _cyanide_type(sample):
    kinds = _kinds(sample)
    for test_type in (Service.CYANIDE_CONVENTIONAL, Service.CYANIDE_OPTIMIZATION):
        if test_type in kinds:
            return test_type
    return get_metallurgical_type(sample)


def _misrouted(sample, expected):
    routes = _routes(sample)
    if expected in routes:
        return None
    return redirect(routes[0], slug=sample.slug)


def _is_read_only(sample, entry):
    return (
        entry.status == entry.SUBMITTED_TO_QC
        or sample.analysis_status not in entry.EDITABLE_SAMPLE_STATUSES
    )


def _latest_entry(model, sample):
    return model.objects.filter(sample=sample).order_by("-revision").first()


def _open_entry(model, sample, user):
    entry = model.current_for(sample, user)
    if entry is None:
        entry = _latest_entry(model, sample)
    return entry


def _no_entry(request, list_route, sample):
    messages.error(request, "This sample is not available for data entry.")
    return redirect(list_route, reference=sample.submission.reference)


def _no_worksheet(request):
    messages.error(
        request,
        "The worksheet for this sample has not been generated. Data entry is unavailable.",
    )
    return redirect("chemist:chemist_dashboard")


def _metallurgical_worksheet_rows(sample, test_type=None):
    if test_type is None:
        test_type = get_metallurgical_type(sample)
    if test_type == Service.CARBON_ACTIVITY:
        worksheet = latest_carbon_worksheet(sample.submission)
    else:
        worksheet_type = {
            Service.CYANIDE_CONVENTIONAL: Worksheet.CONVENTIONAL_CYANIDE_LEACHING,
            Service.CYANIDE_OPTIMIZATION: Worksheet.PARAMETER_OPTIMIZATION,
        }.get(test_type)
        if worksheet_type is None:
            return []
        worksheet = (
            Worksheet.objects.filter(
                submission=sample.submission, worksheet_type=worksheet_type
            )
            .order_by("-generated_at", "-id")
            .first()
        )
    if worksheet is None:
        return []
    return list(
        worksheet.rows.filter(
            lab_sample_mapping__sample=sample,
            row_type__in=(WorksheetRow.SAMPLE_ROW, WorksheetRow.REPLICATE_ROW),
        ).order_by("row_number")
    )


def _rows_for_route(sample, route):
    if route == MINERAL_ROUTE:
        return worksheet_rows_for_sample(sample)
    if route == CARBON_ROUTE:
        return _metallurgical_worksheet_rows(sample, Service.CARBON_ACTIVITY)
    return _metallurgical_worksheet_rows(sample, _cyanide_type(sample))


def _route_pending(sample, route):
    entry = _latest_entry(ENTRY_MODELS[route], sample)
    return entry is None or entry.status != entry.SUBMITTED_TO_QC


def _can_open(sample, route):
    if _latest_entry(ENTRY_MODELS[route], sample) is not None:
        return True
    return bool(_rows_for_route(sample, route))


def _pending_crm(submission):
    return any(
        item["kind"] == "crm" and item["state"] != "submitted"
        for item in _mineral_worksheet_items(submission)
    )


def _pending_sections(submission, skip_sample=None, skip_route=None):
    candidates = Sample.objects.filter(
        submission=submission,
        submission__is_submitted=True,
        analysis_status__in=MineralAnalysisEntry.EDITABLE_SAMPLE_STATUSES,
    ).order_by("id")
    sections = []
    for candidate in candidates:
        for route in _routes(candidate):
            if (
                skip_sample is not None
                and candidate.pk == skip_sample.pk
                and route == skip_route
            ):
                continue
            section = SECTION_LISTS[route]
            if section in sections:
                continue
            if _route_pending(candidate, route) and _can_open(candidate, route):
                sections.append(section)

    if MINERAL_LIST_ROUTE not in sections and _pending_crm(submission):
        sections.insert(0, MINERAL_LIST_ROUTE)
    return sections


def _finalize(request, sample, entry, list_route, entry_route):
    if "submit_qc" in request.POST:
        try:
            entry.submit_to_qc(request.user)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect(entry_route, slug=sample.slug)
        messages.success(request, f"{lab_sample_id_for(sample)} submitted to QC.")
        sections = _pending_sections(sample.submission, sample, entry_route)
        target = list_route
        if sections:
            target = list_route if list_route in sections else sections[0]
            if target == list_route:
                extra = " (or CRM)" if target == MINERAL_LIST_ROUTE else ""
                messages.info(
                    request,
                    f"Choose the next {SECTION_LABELS[target]} item{extra} from the list.",
                )
            else:
                messages.info(
                    request,
                    f"Continue with {SECTION_LABELS[target]} for this reference.",
                )
        return redirect(target, reference=sample.submission.reference)

    messages.success(request, "Draft saved.")
    return redirect(entry_route, slug=sample.slug)


def _format_result(value):
    if value is None:
        return None
    return format(value, "f")


@chemist_required
def chemist_dashboard(request):
    visible = _visible_samples(request)

    awaiting_mineral_count = (
        visible.filter(
            analysis_status=Sample.SUBMITTED_TO_LAB,
            sample_services__service__metallurgical_type=Service.NONE,
        )
        .distinct()
        .count()
    )

    awaiting_metallurgical_count = (
        visible.filter(
            analysis_status=Sample.SUBMITTED_TO_LAB,
            sample_services__service__metallurgical_type__in=METALLURGICAL_TYPES,
        )
        .distinct()
        .count()
    )

    reassay_count = visible.filter(analysis_status=Sample.REASSAY_REQUIRED).count()
    qc_approved_count = visible.filter(analysis_status=Sample.QC_APPROVED).count()
    in_qc_count = visible.filter(analysis_status=Sample.SUBMITTED_TO_QC).count()
    reassay_submitted_count = visible.filter(
        analysis_status=Sample.REASSAY_SUBMITTED
    ).count()

    recent_samples = visible.select_related("submission").order_by("-updated_at")[:8]

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
        "branch": _branch(request),
        "awaiting_mineral_count": awaiting_mineral_count,
        "awaiting_metallurgical_count": awaiting_metallurgical_count,
        "reassay_count": reassay_count,
        "qc_approved_count": qc_approved_count,
        "in_qc_count": in_qc_count,
        "reassay_submitted_count": reassay_submitted_count,
        "recent_samples": recent_samples,
        "weekly_chart": weekly_chart,
    }
    return render(request, "chemist/chemist_dashboard.html", context)


@chemist_required
def mineral_analysis_search(request):
    reference = request.GET.get("reference", "").strip()
    if reference:
        return redirect(MINERAL_LIST_ROUTE, reference=reference)
    return render(request, "chemist/mineral_analysis_search.html")


def _mineral_worksheet_items(submission):
    worksheets = mineral_worksheets(submission)
    if not worksheets:
        return []

    owner = {}
    for worksheet in worksheets:
        sample_ids = worksheet.rows.filter(
            row_type__in=(WorksheetRow.SAMPLE_ROW, WorksheetRow.REPLICATE_ROW),
            lab_sample_mapping__isnull=False,
        ).values_list("lab_sample_mapping__sample", flat=True)
        for sample_id in set(sample_ids):
            owner.setdefault(sample_id, worksheet.pk)

    active_ids = set(owner.values()) | {worksheets[0].pk}
    active = [w for w in reversed(worksheets) if w.pk in active_ids]

    items = []
    for worksheet in active:
        elements = worksheet_elements(worksheet)
        rows = worksheet.rows.select_related("lab_sample_mapping__sample").order_by(
            "row_number"
        )
        crm_data = {
            crm.worksheet_row_id: crm
            for crm in CRMEntry.objects.filter(worksheet_row__worksheet=worksheet)
        }

        by_sample = {}
        for row in rows:
            number = row.display_number or row.row_number
            if (
                row.row_type in (WorksheetRow.SAMPLE_ROW, WorksheetRow.REPLICATE_ROW)
                and row.lab_sample_mapping_id
            ):
                sample = row.lab_sample_mapping.sample
                if owner.get(sample.pk) != worksheet.pk:
                    continue
                item = by_sample.get(sample.pk)
                if item is None:
                    item = {
                        "kind": "sample",
                        "sample": sample,
                        "lab_id": format_lab_sample_id(
                            row.lab_sample_mapping.lab_sample_id
                        ),
                        "first": number,
                        "last": number,
                    }
                    by_sample[sample.pk] = item
                    items.append(item)
                item["last"] = number
            elif row.row_type == WorksheetRow.CRM_ROW:
                crm = crm_data.get(row.pk)
                if crm is None or not crm.has_data:
                    state = "pending"
                elif crm.status == CRMEntry.SUBMITTED_TO_QC:
                    state = "submitted"
                elif crm.is_complete(elements):
                    state = "complete"
                else:
                    state = "partial"
                items.append(
                    {"kind": "crm", "number": number, "row_id": row.pk, "state": state}
                )

    sample_ids = [item["sample"].pk for item in items if item["kind"] == "sample"]
    latest = {}
    for entry in MineralAnalysisEntry.objects.filter(sample_id__in=sample_ids).order_by(
        "-revision"
    ):
        latest.setdefault(entry.sample_id, entry)

    for item in items:
        if item["kind"] != "sample":
            continue
        sample = item["sample"]
        entry = latest.get(sample.pk)
        item["submitted"] = (
            entry is not None
            and entry.status == MineralAnalysisEntry.SUBMITTED_TO_QC
            and not (
                sample.analysis_status == Sample.REASSAY_REQUIRED
                and not entry.is_reassay
            )
        )
    return items


@chemist_required
def mineral_analysis_samples(request, reference):
    submission = _find_submission(request, reference)

    items = []
    sample_count = 0
    worksheet_missing = False
    if submission:
        mineral_samples_exist = (
            _visible_samples(request)
            .filter(
                submission=submission,
                sample_services__service__metallurgical_type=Service.NONE,
            )
            .exists()
        )
        worksheet_missing = (
            latest_mineral_worksheet(submission) is None and mineral_samples_exist
        )
        if not worksheet_missing:
            items = _mineral_worksheet_items(submission)
        sample_count = sum(1 for item in items if item["kind"] == "sample")

    context = {
        "reference": reference,
        "submission": submission,
        "items": items,
        "sample_count": sample_count,
        "worksheet_missing": worksheet_missing,
    }
    return render(request, "chemist/mineral_analysis_samples.html", context)


@chemist_required
def mineral_analysis_entry(request, slug):
    sample = _get_sample(request, slug)
    misrouted = _misrouted(sample, MINERAL_ROUTE)
    if misrouted:
        return misrouted

    if not _can_open(sample, MINERAL_ROUTE):
        return _no_worksheet(request)

    entry = _open_entry(MineralAnalysisEntry, sample, request.user)
    if entry is None:
        return _no_entry(request, MINERAL_LIST_ROUTE, sample)

    entry.ensure_replicates()
    replicates = list(
        entry.replicates.select_related("worksheet_row__lab_sample_mapping")
    )
    read_only = _is_read_only(sample, entry)

    def render_entry():
        context = {
            "sample": sample,
            "entry": entry,
            "lab_id": lab_sample_id_for(sample),
            "elements": entry.registered_elements,
            "replicates": replicates,
            "read_only": read_only,
        }
        return render(request, "chemist/mineral_analysis_entry.html", context)

    if request.method == "POST":
        if read_only:
            messages.error(request, "This entry is locked and can no longer be edited.")
            return redirect(MINERAL_ROUTE, slug=sample.slug)

        reader = _PostReader(request.POST)
        for replicate in replicates:
            number = replicate.replicate_number
            prefix = f"rep{number}"
            for field, label in MINERAL_FIELDS:
                setattr(
                    replicate,
                    field,
                    reader.decimal(f"{prefix}_{field}", f"Replicate {number} {label}"),
                )

        for replicate in replicates:
            _check(reader, replicate, f"Replicate {replicate.replicate_number}")

        if reader.errors:
            _report_errors(request, reader.errors)
            return render_entry()

        with transaction.atomic():
            for replicate in replicates:
                replicate.save()
            entry.refresh_status(request.user)

        return _finalize(
            request,
            sample,
            entry,
            MINERAL_LIST_ROUTE,
            MINERAL_ROUTE,
        )

    return render_entry()


@chemist_required
@require_POST
def mineral_analysis_preview(request, slug):
    sample = _get_sample(request, slug)
    if not _can_open(sample, MINERAL_ROUTE):
        return JsonResponse(
            {"error": "The worksheet for this sample has not been generated."},
            status=404,
        )
    entry = (
        MineralAnalysisEntry.objects.filter(sample=sample).order_by("-revision").first()
    )
    if entry is None:
        return JsonResponse({"results": {}})

    reader = _PostReader(request.POST)
    replicates = list(entry.replicates.select_related("entry__sample"))
    for replicate in replicates:
        number = replicate.replicate_number
        prefix = f"rep{number}"
        for field, label in MINERAL_FIELDS:
            setattr(replicate, field, reader.decimal(f"{prefix}_{field}", label))

    results = {}
    for replicate in replicates:
        try:
            replicate.calculate()
        except ArithmeticError:
            replicate.gold_ppm = None
            replicate.copper_ppm = None
            replicate.silver_ppm = None
        results[str(replicate.replicate_number)] = {
            "gold": _format_result(replicate.gold_ppm),
            "copper": _format_result(replicate.copper_ppm),
            "silver": _format_result(replicate.silver_ppm),
        }
    return JsonResponse({"results": results})


@chemist_required
def mineral_crm_entry(request, row_id):
    row = get_object_or_404(
        WorksheetRow.objects.select_related("worksheet__submission"),
        pk=row_id,
        row_type=WorksheetRow.CRM_ROW,
        worksheet__worksheet_type=Worksheet.MINERAL_ANALYSIS,
        worksheet__submission__is_submitted=True,
        worksheet__submission__branch=_branch(request),
    )
    submission = row.worksheet.submission
    elements = worksheet_elements(row.worksheet)
    crm, _ = CRMEntry.objects.get_or_create(worksheet_row=row)
    read_only = crm.is_locked

    def render_entry():
        context = {
            "crm": crm,
            "submission": submission,
            "elements": elements,
            "read_only": read_only,
        }
        return render(request, "chemist/mineral_crm_entry.html", context)

    if request.method == "POST":
        if read_only:
            messages.error(
                request, "This CRM was submitted to QC and can no longer be edited."
            )
            return redirect("chemist:mineral_crm_entry", row_id=row.pk)

        reader = _PostReader(request.POST)
        for field, label in MINERAL_FIELDS:
            setattr(crm, field, reader.decimal(f"crm_{field}", f"CRM {label}"))
        _check(reader, crm, "CRM")

        if reader.errors:
            _report_errors(request, reader.errors)
            return render_entry()

        with transaction.atomic():
            crm.entered_by = request.user
            crm.save()
            crm.refresh_status(elements, request.user)

        if "submit_qc" in request.POST:
            try:
                crm.submit_to_qc(elements, request.user)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
                return redirect("chemist:mineral_crm_entry", row_id=row.pk)
            messages.success(request, "CRM submitted to QC.")
            sections = _pending_sections(submission)
            target = MINERAL_LIST_ROUTE
            if sections:
                target = (
                    MINERAL_LIST_ROUTE
                    if MINERAL_LIST_ROUTE in sections
                    else sections[0]
                )
                if target == MINERAL_LIST_ROUTE:
                    messages.info(
                        request,
                        "Choose the next mineral analysis item (or CRM) from the list.",
                    )
                else:
                    messages.info(
                        request,
                        f"Continue with {SECTION_LABELS[target]} for this reference.",
                    )
            return redirect(target, reference=submission.reference)

        messages.success(request, "Draft saved.")
        return redirect("chemist:mineral_crm_entry", row_id=row.pk)

    return render_entry()


@chemist_required
def metallurgical_tests_search(request):
    reference = request.GET.get("reference", "").strip()
    if reference:
        return redirect(METALLURGICAL_LIST_ROUTE, reference=reference)
    return render(request, "chemist/metallurgical_tests_search.html")


@chemist_required
def metallurgical_tests_samples(request, reference):
    submission = _find_submission(request, reference)

    items = []
    worksheet_missing_count = 0
    if submission:
        candidates = list(
            _visible_samples(request)
            .filter(submission=submission)
            .filter(
                Q(sample_services__service__metallurgical_type__in=METALLURGICAL_TYPES)
                | Q(metallurgical_test_entries__isnull=False)
                | Q(carbon_activity_entries__isnull=False)
            )
            .distinct()
            .order_by("id")
        )
        for sample in candidates:
            for route in _routes(sample):
                if route == MINERAL_ROUTE:
                    continue
                if _can_open(sample, route):
                    items.append(
                        {
                            "sample": sample,
                            "lab_id": lab_sample_id_for(sample),
                            "route": route,
                            "label": ROUTE_LABELS[route],
                            "url": reverse(route, kwargs={"slug": sample.slug}),
                            "submitted": not _route_pending(sample, route),
                        }
                    )
                else:
                    worksheet_missing_count += 1

    context = {
        "reference": reference,
        "submission": submission,
        "items": items,
        "sample_count": len(items),
        "pending_count": sum(1 for item in items if not item["submitted"]),
        "worksheet_missing_count": worksheet_missing_count,
    }
    return render(request, "chemist/metallurgical_tests_samples.html", context)


@chemist_required
def metallurgical_test_entry(request, slug):
    sample = _get_sample(request, slug)
    misrouted = _misrouted(sample, CYANIDE_ROUTE)
    if misrouted:
        return misrouted

    if not _can_open(sample, CYANIDE_ROUTE):
        return _no_worksheet(request)

    entry = _open_entry(MetallurgicalTestEntry, sample, request.user)
    if entry is None:
        return _no_entry(request, METALLURGICAL_LIST_ROUTE, sample)

    entry.ensure_parameter_rows()
    rows = list(entry.rows.select_related("source_parameter", "worksheet_row"))
    read_only = _is_read_only(sample, entry)

    def render_entry():
        context = {
            "sample": sample,
            "lab_id": lab_sample_id_for(sample),
            "entry": entry,
            "rows": rows,
            "read_only": read_only,
        }
        return render(request, "chemist/metallurgical_test_entry.html", context)

    if request.method == "POST":
        if read_only:
            messages.error(request, "This entry is locked and can no longer be edited.")
            return redirect(CYANIDE_ROUTE, slug=sample.slug)

        reader = _PostReader(request.POST)
        for row in rows:
            prefix = f"row{row.id}"
            label = row.source_parameter.display_label
            for field, key, field_label in METALLURGICAL_FIELDS:
                setattr(
                    row,
                    field,
                    reader.decimal(f"{prefix}_{key}", f"{label} {field_label}"),
                )
            row.si_unit = reader.text(f"{prefix}_si_unit")
            if row.si_unit and row.si_unit not in row.allowed_units:
                reader.errors.append(
                    f"{label} SI unit must be one of: {', '.join(row.allowed_units)}."
                )
            row.remarks = reader.text(f"{prefix}_remarks")
            _check(reader, row, label)

        if reader.errors:
            _report_errors(request, reader.errors)
            return render_entry()

        with transaction.atomic():
            for row in rows:
                row.save()
            entry.refresh_status(request.user)

        return _finalize(
            request,
            sample,
            entry,
            METALLURGICAL_LIST_ROUTE,
            CYANIDE_ROUTE,
        )

    return render_entry()


@chemist_required
def carbon_activity_entry(request, slug):
    sample = _get_sample(request, slug)
    misrouted = _misrouted(sample, CARBON_ROUTE)
    if misrouted:
        return misrouted

    if not _can_open(sample, CARBON_ROUTE):
        return _no_worksheet(request)

    entry = _open_entry(CarbonActivityEntry, sample, request.user)
    if entry is None:
        return _no_entry(request, METALLURGICAL_LIST_ROUTE, sample)

    entry.ensure_replicates()
    replicates = list(
        entry.replicates.select_related("worksheet_row__lab_sample_mapping")
    )
    read_only = _is_read_only(sample, entry)

    def render_entry():
        context = {
            "sample": sample,
            "lab_id": lab_sample_id_for(sample),
            "entry": entry,
            "replicates": replicates,
            "read_only": read_only,
        }
        return render(request, "chemist/carbon_activity_entry.html", context)

    if request.method == "POST":
        if read_only:
            messages.error(request, "This entry is locked and can no longer be edited.")
            return redirect(CARBON_ROUTE, slug=sample.slug)

        reader = _PostReader(request.POST)
        for replicate in replicates:
            number = replicate.replicate_number
            prefix = f"rep{number}"
            for field, key, label in CARBON_FIELDS:
                setattr(
                    replicate,
                    field,
                    reader.decimal(f"{prefix}_{key}", f"Replicate {number} {label}"),
                )
            replicate.remarks = reader.text(f"{prefix}_remarks")
            _check(reader, replicate, f"Replicate {number}")

        if reader.errors:
            _report_errors(request, reader.errors)
            return render_entry()

        with transaction.atomic():
            for replicate in replicates:
                replicate.save()
            entry.recalculate_final_activity()
            entry.refresh_status(request.user)

        return _finalize(
            request,
            sample,
            entry,
            METALLURGICAL_LIST_ROUTE,
            CARBON_ROUTE,
        )

    return render_entry()


@chemist_required
@require_POST
def carbon_activity_preview(request, slug):
    sample = _get_sample(request, slug)
    entry = (
        CarbonActivityEntry.objects.filter(sample=sample).order_by("-revision").first()
    )
    if entry is None:
        return JsonResponse({"results": {}, "final": None})

    reader = _PostReader(request.POST)
    results = {}
    activities = []

    for replicate in entry.replicates.all():
        number = replicate.replicate_number
        prefix = f"rep{number}"
        for field, key, label in CARBON_FIELDS:
            setattr(replicate, field, reader.decimal(f"{prefix}_{key}", label))
        try:
            replicate.calculate()
        except ArithmeticError:
            replicate.activity_percent = None
        results[str(number)] = {"activity": _format_result(replicate.activity_percent)}
        if replicate.activity_percent is not None:
            activities.append(replicate.activity_percent)

    final = None
    if activities and len(activities) == entry.required_replicate_count:
        try:
            average = sum(activities) / Decimal(len(activities))
            final = _format_result(_quantize(average * Decimal("0.80")))
        except ArithmeticError:
            final = None

    return JsonResponse({"results": results, "final": final})


@chemist_required
def reassay_samples(request):
    reference = request.GET.get("reference", "").strip()
    status = request.GET.get("status", "all")

    visible = _visible_samples(request)

    samples = (
        visible.filter(
            analysis_status__in=[Sample.REASSAY_REQUIRED, Sample.REASSAY_SUBMITTED]
        )
        .select_related("submission", "lab_mapping")
        .order_by("-updated_at", "-id")
    )

    if reference:
        samples = samples.filter(submission__reference__iexact=reference)

    if status == "required":
        samples = samples.filter(analysis_status=Sample.REASSAY_REQUIRED)
    elif status == "submitted":
        samples = samples.filter(analysis_status=Sample.REASSAY_SUBMITTED)

    page_obj, querystring = _paginate(request, samples)

    items = [
        {"sample": sample, "lab_id": lab_sample_id_for(sample)}
        for sample in page_obj.object_list
    ]

    required_count = visible.filter(analysis_status=Sample.REASSAY_REQUIRED).count()
    submitted_count = visible.filter(analysis_status=Sample.REASSAY_SUBMITTED).count()

    context = {
        "reference": reference,
        "status": status,
        "items": items,
        "page_obj": page_obj,
        "querystring": querystring,
        "required_count": required_count,
        "submitted_count": submitted_count,
        "total_count": required_count + submitted_count,
    }
    return render(request, "chemist/reassay_samples.html", context)


@chemist_required
def reassay_entry(request, slug):
    sample = _get_sample(request, slug)
    return redirect(_routes(sample)[0], slug=sample.slug)


@chemist_required
def qc_approved(request):
    reference = request.GET.get("reference", "").strip()
    visible = _visible_samples(request)

    samples = (
        visible.filter(analysis_status=Sample.QC_APPROVED)
        .select_related("submission", "lab_mapping")
        .order_by("-updated_at", "-id")
    )

    if reference:
        samples = samples.filter(submission__reference__iexact=reference)

    page_obj, querystring = _paginate(request, samples)

    items = [
        {
            "sample": sample,
            "lab_id": lab_sample_id_for(sample),
            "route": _routes(sample)[0],
        }
        for sample in page_obj.object_list
    ]

    context = {
        "reference": reference,
        "items": items,
        "page_obj": page_obj,
        "querystring": querystring,
        "total_count": visible.filter(analysis_status=Sample.QC_APPROVED).count(),
    }
    return render(request, "chemist/qc_approved.html", context)
