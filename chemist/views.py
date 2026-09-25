from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Q
from samples.models import Sample, Service
from accounts.decorators import chemist_required


@chemist_required
def chemist_dashboard(request):
    today = timezone.localdate()
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]

    per_day = dict(
        Sample.objects.filter(updated_at__date__gte=days[0])
        .annotate(day=TruncDate("updated_at"))
        .values("day")
        .annotate(total=Count("id"))
        .values_list("day", "total")
    )
    weekly_chart = [
        {"label": day.strftime("%a"), "count": per_day.get(day, 0)} for day in days
    ]

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

    context = {
        "awaiting_mineral_count": awaiting_mineral_count,
        "awaiting_metallurgical_count": awaiting_metallurgical_count,
        "reassay_count": Sample.objects.filter(
            analysis_status=Sample.REASSAY_REQUIRED
        ).count(),
        "qc_approved_count": Sample.objects.filter(
            analysis_status=Sample.QC_APPROVED
        ).count(),
        "recent_samples": Sample.objects.select_related("submission").order_by(
            "-updated_at"
        )[:8],
        "weekly_chart": weekly_chart,
    }
    return render(request, "chemist/chemist_dashboard.html", context)


@chemist_required
def mineral_analysis(request):
    return render(request, "chemist/mineral_analysis.html")


@chemist_required
def metallurgical_analysis(request):
    return render(request, "chemist/metallurgical_analysis.html")


@chemist_required
def reassay_samples(request):
    return render(request, "chemist/reassay_samples.html")


@chemist_required
def qc_approved(request):
    return render(request, "chemist/qc_approved.html")
