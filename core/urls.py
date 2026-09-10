from django.urls import path, include
from core import views

urlpatterns = [
    path("", views.homepage, name="homepage"),
    path("services", views.services, name="services"),
    path("about", views.about, name="about"),
    path("pricing", views.pricing, name="pricing"),
    path("contact", views.contact, name="contact"),
    path("request-quote", views.request_quote, name="request_quote"),
]
