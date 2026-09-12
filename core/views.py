from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse


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
