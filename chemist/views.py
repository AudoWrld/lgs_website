from django.shortcuts import render


def chemist_dashboard(request):
    return render(request, "chemist/chemist_dashboard.html")


def mineral_analysis(request):
    return render(request, "chemist/mineral_analysis.html")


def metallurgical_analysis(request):
    return render(request, "chemist/metallurgical_analysis.html")


def reassay_samples(request):
    return render(request, "chemist/reassay_samples.html")


def qc_approved(request):
    return render(request, "chemist/qc_approved.html")
