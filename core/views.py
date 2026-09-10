from django.shortcuts import render


def homepage(request):
    return render(request, "homepage.html")


def services(request):
    return render(request, "services.html")


def about(request):
    return render(request, "about.html")


def pricing(request):
    return render(request, "pricing.html")


def contact(request):
    return render(request, "contact.html")


def request_quote(request):
    return render(request, "request_quote.html")
