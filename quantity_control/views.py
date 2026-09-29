from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import qc_required
from coa.models import COA
from samples.models import Sample
from submissions.models import Submission

from .templatetags.qc_extras import register


PAGE_SIZE = 12


def _visible_submissions():
    return Submission.objects.filter(is_submitted=True).select_related("client")


def _paginate(request, queryset):
    page = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()


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
        {
            "label": day.strftime("%a"),
            "count": per_day.get(day, 0),
            "height": min(160, (per_day.get(day, 0) or 0) * 8),
        }
        for day in days
    ]

    context = {
        "pending_count": pending.count(),
        "reassay_count": reassay.count(),
        "approved_count": approved.count(),
        "pending_samples": list(pending[:8]),
        "reassay_samples": list(reassay[:8]),
        "approved_samples": list(approved[:8]),
        "weekly_chart": weekly_chart,
    }
    return render(request, "quantity_control/qc_dashboard.html", context)


def _sample_items(samples):
    from chemist.models import lab_sample_id_for

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
    samples = Sample.objects.filter(
        submission__is_submitted=True, analysis_status=Sample.SUBMITTED_TO_QC
    ).select_related("submission", "lab_mapping").order_by("-updated_at", "-id")

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
    samples = Sample.objects.filter(
        submission__is_submitted=True,
        analysis_status=Sample.REASSAY_SUBMITTED,
    ).select_related("submission", "lab_mapping").order_by("-updated_at", "-id")

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
    samples = Sample.objects.filter(
        submission__is_submitted=True, analysis_status=Sample.QC_APPROVED
    ).select_related("submission", "lab_mapping").order_by("-updated_at", "-id")

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
        Submission.objects.filter(is_submitted=True, reference__iexact=reference)
        .select_related("client")
    )
    samples = list(
        submission.samples.select_related("lab_mapping").order_by("id")
    )
    coa = COA.objects.filter(submission=submission).select_related(
        "group", "approved_by"
    ).first()
    context = {
        "submission": submission,
        "samples": samples,
        "coa": coa,
    }
    return render(request, "quantity_control/report_detail.html", context)