from datetime import timedelta
from types import SimpleNamespace

from django.contrib import messages
from django.core.paginator import Paginator
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

PAGE_SIZE = 12


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

    if request.method == "POST":
        if not reviewable:
            messages.error(request, "This sample is not awaiting QC review.")
            return redirect("qc:sample_review", slug=sample.slug)

        action = request.POST.get("action")
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

    context = {
        "sample": sample,
        "lab_id": lab_sample_id_for(sample),
        "kind": kind,
        "entry": entry,
        "services": services,
        "reviewable": reviewable,
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
