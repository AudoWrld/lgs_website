from django.shortcuts import render


def homepage(request):
    return render(request, "core/homepage.html")


def services(request):
    return render(request, "core/services.html")


def about(request):
    return render(request, "core/about.html")


def pricing(request):
    return render(request, "core/pricing.html")


def contact(request):
    return render(request, "core/contact.html")


def request_quote(request):
    return render(request, "core/request_quote.html")
