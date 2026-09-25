from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from samples.models import Sample


@login_required
def chemist_dashboard(request):
    context = {
        "awaiting_mineral_count": Sample.objects.filter(
            analysis_status=Sample.SUBMITTED_TO_LAB
        )
        .exclude(sample_type=Sample.PROCESS_SOLUTION)
        .count(),
        "awaiting_metallurgical_count": Sample.objects.filter(
            analysis_status=Sample.SUBMITTED_TO_LAB
        ).count(),
        "reassay_count": Sample.objects.filter(
            analysis_status=Sample.REASSAY_REQUIRED
        ).count(),
        "qc_approved_count": Sample.objects.filter(
            analysis_status=Sample.QC_APPROVED
        ).count(),
        "recent_samples": Sample.objects.select_related("submission").order_by(
            "-updated_at"
        )[:8],
        "weekly_chart": [],
    }
    return render(request, "chemist/chemist_dashboard.html", context)


def mineral_analysis(request):
    return render(request, "chemist/mineral_analysis.html")


def metallurgical_analysis(request):
    return render(request, "chemist/metallurgical_analysis.html")


def reassay_samples(request):
    return render(request, "chemist/reassay_samples.html")


def qc_approved(request):
    return render(request, "chemist/qc_approved.html")
