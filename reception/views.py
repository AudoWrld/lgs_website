from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render


def reception_required(view):
    @wraps(view)
    @login_required(login_url="accounts:login")
    def wrapped(request, *args, **kwargs):
        if not request.user.is_reception:
            raise PermissionDenied("Reception access is required.")
        return view(request, *args, **kwargs)

    return wrapped


@reception_required
def reception_dashboard(request):
    return render(request, "reception/reception_dashboard.html")


@reception_required
def client_search(request):
    return render(request, "reception/client_search.html")


@reception_required
def client_register(request):
    return render(request, "reception/client_register.html")


@reception_required
def sample_registration(request):
    return render(request, "reception/sample_registration.html")


@reception_required
def coa_reporting_preference(request):
    return render(request, "reception/coa_reporting_preference.html")


@reception_required
def generate_worksheet(request):
    return render(request, "reception/generate_worksheet.html")


@reception_required
def client_submission_form(request):
    return render(request, "reception/client_submission_form.html")


@reception_required
def payment_details(request):
    return render(request, "reception/payment_details.html")


@reception_required
def add_expense(request):
    return render(request, "reception/add_expense.html")