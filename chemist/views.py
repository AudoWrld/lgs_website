from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from submissions.models import Submission
from samples.models import Sample, Service
from accounts.decorators import chemist_required
from .models import (
    CarbonActivityEntry,
    CRMSequenceCounter,
    MetallurgicalTestEntry,
    MineralAnalysisEntry,
)


def _parse_decimal(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


@chemist_required
def chemist_dashboard(request):
    awaiting_mineral_count = (
        Sample.objects.filter(
            analysis_status=Sample.SUBMITTED_TO_LAB,
            sample_services__service__metallurgical_type=Service.NONE,
        )
        .distinct()
        .count()
    )

    awaiting_metallurgical_count = (
        Sample.objects.filter(
            analysis_status=Sample.SUBMITTED_TO_LAB,
            sample_services__service__metallurgical_type__in=[
                Service.CYANIDE_CONVENTIONAL,
                Service.CYANIDE_OPTIMIZATION,
                Service.CARBON_ACTIVITY,
            ],
        )
        .distinct()
        .count()
    )

    reassay_count = Sample.objects.filter(
        analysis_status=Sample.REASSAY_REQUIRED
    ).count()

    qc_approved_count = Sample.objects.filter(
        analysis_status=Sample.QC_APPROVED
    ).count()

    recent_samples = Sample.objects.select_related("submission").order_by(
        "-updated_at"
    )[:8]

    today = timezone.localdate()
    weekly_chart = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        count = Sample.objects.filter(
            analysis_status__in=[
                Sample.SUBMITTED_TO_QC,
                Sample.REASSAY_SUBMITTED,
                Sample.QC_APPROVED,
            ],
            updated_at__date=day,
        ).count()
        weekly_chart.append({"label": day.strftime("%a"), "count": count})

    context = {
        "awaiting_mineral_count": awaiting_mineral_count,
        "awaiting_metallurgical_count": awaiting_metallurgical_count,
        "reassay_count": reassay_count,
        "qc_approved_count": qc_approved_count,
        "recent_samples": recent_samples,
        "weekly_chart": weekly_chart,
    }
    return render(request, "chemist/chemist_dashboard.html", context)


@chemist_required
def mineral_analysis_search(request):
    reference = request.GET.get("reference", "").strip()
    if reference:
        return redirect("chemist:mineral_analysis_samples", reference=reference)
    return render(request, "chemist/mineral_analysis_search.html")


@chemist_required
def mineral_analysis_samples(request, reference):
    submission = Submission.objects.filter(reference__iexact=reference).first()

    samples = []
    if submission:
        samples = (
            Sample.objects.filter(
                submission=submission,
                sample_services__service__metallurgical_type=Service.NONE,
            )
            .distinct()
            .order_by("id")
        )

    context = {
        "reference": reference,
        "submission": submission,
        "samples": samples,
    }
    return render(request, "chemist/mineral_analysis_samples.html", context)


@chemist_required
def mineral_analysis_entry(request, slug):
    sample = get_object_or_404(Sample, slug=slug)
    entry, _ = MineralAnalysisEntry.objects.get_or_create(sample=sample)
    entry.ensure_replicates()

    if request.method == "POST":
        for replicate in entry.replicates.all():
            prefix = f"rep{replicate.replicate_number}"
            replicate.weight = _parse_decimal(request.POST.get(f"{prefix}_weight"))
            replicate.au_aas = _parse_decimal(request.POST.get(f"{prefix}_au_aas"))
            replicate.au_df = _parse_decimal(request.POST.get(f"{prefix}_au_df"))
            replicate.cu_aas = _parse_decimal(request.POST.get(f"{prefix}_cu_aas"))
            replicate.cu_df = _parse_decimal(request.POST.get(f"{prefix}_cu_df"))
            replicate.ag_aas = _parse_decimal(request.POST.get(f"{prefix}_ag_aas"))
            replicate.ag_df = _parse_decimal(request.POST.get(f"{prefix}_ag_df"))
            replicate.sulphur = _parse_decimal(request.POST.get(f"{prefix}_sulphur"))
            replicate.save()

        entry.refresh_status()

        if "submit_qc" in request.POST:
            try:
                entry.submit_to_qc()
                CRMSequenceCounter.register_sample_and_maybe_insert_crm(entry)
                messages.success(request, f"{sample.slug} submitted to QC.")
                return redirect(
                    "chemist:mineral_analysis_samples",
                    reference=sample.submission.reference,
                )
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Draft saved.")

        return redirect("chemist:mineral_analysis_entry", slug=sample.slug)

    context = {
        "sample": sample,
        "entry": entry,
        "elements": entry.registered_elements,
        "replicates": entry.replicates.all(),
    }
    return render(request, "chemist/mineral_analysis_entry.html", context)


@chemist_required
def metallurgical_tests_search(request):
    reference = request.GET.get("reference", "").strip()
    if reference:
        return redirect("chemist:metallurgical_tests_samples", reference=reference)
    return render(request, "chemist/metallurgical_tests_search.html")


@chemist_required
def metallurgical_tests_samples(request, reference):
    submission = Submission.objects.filter(reference__iexact=reference).first()

    samples = []
    if submission:
        samples = (
            Sample.objects.filter(
                submission=submission,
                sample_services__service__metallurgical_type__in=[
                    Service.CYANIDE_CONVENTIONAL,
                    Service.CYANIDE_OPTIMIZATION,
                    Service.CARBON_ACTIVITY,
                ],
            )
            .distinct()
            .order_by("id")
        )

    context = {
        "reference": reference,
        "submission": submission,
        "samples": samples,
    }
    return render(request, "chemist/metallurgical_tests_samples.html", context)


def _get_metallurgical_type(sample):
    sample_service = (
        sample.sample_services.filter(
            service__metallurgical_type__in=[
                Service.CYANIDE_CONVENTIONAL,
                Service.CYANIDE_OPTIMIZATION,
                Service.CARBON_ACTIVITY,
            ]
        )
        .select_related("service")
        .first()
    )
    return sample_service.service.metallurgical_type if sample_service else None


@chemist_required
def metallurgical_test_entry(request, slug):
    sample = get_object_or_404(Sample, slug=slug)
    test_type = _get_metallurgical_type(sample)

    if test_type == Service.CARBON_ACTIVITY:
        return redirect("chemist:carbon_activity_entry", slug=slug)

    entry, _ = MetallurgicalTestEntry.objects.get_or_create(
        sample=sample, defaults={"test_type": test_type}
    )
    entry.ensure_parameter_rows()

    if request.method == "POST":
        for row in entry.rows.all():
            prefix = f"row{row.id}"
            row.weight_volume = _parse_decimal(
                request.POST.get(f"{prefix}_weight_volume")
            )
            row.si_unit = request.POST.get(f"{prefix}_si_unit", "")
            row.gold_recovery_12h = _parse_decimal(
                request.POST.get(f"{prefix}_recovery_12h")
            )
            row.gold_recovery_24h = _parse_decimal(
                request.POST.get(f"{prefix}_recovery_24h")
            )
            row.gold_recovery_48h = _parse_decimal(
                request.POST.get(f"{prefix}_recovery_48h")
            )
            row.remarks = request.POST.get(f"{prefix}_remarks", "")
            row.save()

        entry.refresh_status()

        if "submit_qc" in request.POST:
            try:
                entry.submit_to_qc()
                messages.success(request, f"{sample.slug} submitted to QC.")
                return redirect(
                    "chemist:metallurgical_tests_samples",
                    reference=sample.submission.reference,
                )
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Draft saved.")

        return redirect("chemist:metallurgical_tests_entry", slug=sample.slug)

    context = {
        "sample": sample,
        "entry": entry,
        "rows": entry.rows.select_related("source_parameter").all(),
    }
    return render(request, "chemist/metallurgical_test_entry.html", context)


@chemist_required
def carbon_activity_entry(request, slug):
    sample = get_object_or_404(Sample, slug=slug)
    entry, _ = CarbonActivityEntry.objects.get_or_create(sample=sample)
    entry.ensure_replicates()

    if request.method == "POST":
        for replicate in entry.replicates.all():
            prefix = f"rep{replicate.replicate_number}"
            replicate.standard_concentration = _parse_decimal(
                request.POST.get(f"{prefix}_standard")
            )
            replicate.final_concentration_sample = _parse_decimal(
                request.POST.get(f"{prefix}_final_sample")
            )
            replicate.final_concentration_standard = _parse_decimal(
                request.POST.get(f"{prefix}_final_standard")
            )
            replicate.remarks = request.POST.get(f"{prefix}_remarks", "")
            replicate.save()

        entry.refresh_status()

        if "submit_qc" in request.POST:
            try:
                entry.submit_to_qc()
                messages.success(request, f"{sample.slug} submitted to QC.")
                return redirect(
                    "chemist:metallurgical_tests_samples",
                    reference=sample.submission.reference,
                )
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Draft saved.")

        return redirect("chemist:carbon_activity_entry", slug=sample.slug)

    context = {
        "sample": sample,
        "entry": entry,
        "replicates": entry.replicates.all(),
    }
    return render(request, "chemist/carbon_activity_entry.html", context)


@chemist_required
def reassay_samples(request):
    reference = request.GET.get("reference", "").strip()
    status = request.GET.get("status", "all")

    samples = (
        Sample.objects.filter(
            analysis_status__in=[Sample.REASSAY_REQUIRED, Sample.REASSAY_SUBMITTED]
        )
        .select_related("submission")
        .order_by("-updated_at")
    )

    if reference:
        samples = samples.filter(submission__reference__iexact=reference)

    if status == "required":
        samples = samples.filter(analysis_status=Sample.REASSAY_REQUIRED)
    elif status == "submitted":
        samples = samples.filter(analysis_status=Sample.REASSAY_SUBMITTED)

    required_count = Sample.objects.filter(
        analysis_status=Sample.REASSAY_REQUIRED
    ).count()
    submitted_count = Sample.objects.filter(
        analysis_status=Sample.REASSAY_SUBMITTED
    ).count()

    context = {
        "reference": reference,
        "status": status,
        "samples": samples,
        "required_count": required_count,
        "submitted_count": submitted_count,
        "total_count": required_count + submitted_count,
    }
    return render(request, "chemist/reassay_samples.html", context)


@chemist_required
def reassay_entry(request, slug):
    sample = get_object_or_404(Sample, slug=slug)
    test_type = _get_metallurgical_type(sample)

    if test_type == Service.CARBON_ACTIVITY:
        return redirect("chemist:carbon_activity_entry", slug=slug)
    if test_type in (Service.CYANIDE_CONVENTIONAL, Service.CYANIDE_OPTIMIZATION):
        return redirect("chemist:metallurgical_tests_entry", slug=slug)
    return redirect("chemist:mineral_analysis_entry", slug=slug)


@chemist_required
def qc_approved(request):
    reference = request.GET.get("reference", "").strip()

    samples = (
        Sample.objects.filter(analysis_status=Sample.QC_APPROVED)
        .select_related("submission")
        .order_by("-updated_at")
    )

    if reference:
        samples = samples.filter(submission__reference__iexact=reference)

    context = {
        "reference": reference,
        "samples": samples,
        "total_count": Sample.objects.filter(
            analysis_status=Sample.QC_APPROVED
        ).count(),
    }
    return render(request, "chemist/qc_approved.html", context)
