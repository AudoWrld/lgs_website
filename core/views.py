from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.shortcuts import render, redirect
from .models import QuoteRequest


def homepage(request):
    return render(request, "core/homepage.html")


def services(request):
    return render(request, "core/services.html")


def about(request):
    return render(request, "core/about.html")


def pricing(request):
    submitted = False
    reference_number = None

    if request.method == "POST":
        full_name = request.POST.get("name", "").strip()
        company = request.POST.get("company", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        services = request.POST.getlist("services")
        methods = request.POST.getlist("methods")
        sample_type = request.POST.get("sample_type", "").strip()
        sample_quantity = request.POST.get("quantity", "").strip()
        sample_unit = request.POST.get("unit", "").strip()
        technical_requirements = request.POST.get("technical_requirements", "").strip()
        message = request.POST.get("message", "").strip()

        if full_name and email and phone and message and services and methods:
            quote_request = QuoteRequest.objects.create(
                full_name=full_name,
                company=company,
                email=email,
                phone=phone,
                services=services,
                methods=methods,
                sample_type=sample_type,
                sample_quantity=sample_quantity,
                sample_unit=sample_unit,
                technical_requirements=technical_requirements,
                message=message,
            )
            submitted = True
            reference_number = quote_request.reference_number

    context = {
        "submitted": submitted,
        "reference_number": reference_number,
    }
    return render(request, "core/pricing.html", context)


def contact(request):
    return render(request, "core/contact.html")


def request_quote(request):
    return redirect("pricing", permanent=True)


def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse("sitemap"))
    content = f"User-agent: *\nAllow: /\nSitemap: {sitemap_url}\n"
    return HttpResponse(content, content_type="text/plain")


def sitemap_xml(request):
    page_names = ["homepage", "services", "about", "pricing", "contact"]
    urls = "\n".join(
        f"  <url><loc>{request.build_absolute_uri(reverse(page_name))}</loc></url>"
        for page_name in page_names
    )
    content = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n'
    return HttpResponse(content, content_type="application/xml")
