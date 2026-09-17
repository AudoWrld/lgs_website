from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required(login_url="accounts:login")
def reception_dashboard(request):
    return render(request, "reception/reception_dashboard.html")


@login_required(login_url="accounts:login")
def client_search(request):
    return render(request, "reception/client_search.html")


@login_required(login_url="accounts:login")
def client_register(request):
    return render(request, "reception/client_register.html")


@login_required(login_url="accounts:login")
def sample_registration(request):
    return render(request, "reception/sample_registration.html")


@login_required(login_url="accounts:login")
def coa_reporting_preference(request):
    return render(request, "reception/coa_reporting_preference.html")


@login_required(login_url="accounts:login")
def generate_worksheet(request):
    return render(request, "reception/generate_worksheet.html")


@login_required(login_url="accounts:login")
def client_submission_form(request):
    return render(request, "reception/client_submission_form.html")


@login_required(login_url="accounts:login")
def payment_details(request):
    return render(request, "reception/payment_details.html")


@login_required(login_url="accounts:login")
def add_expense(request):
    return render(request, "reception/add_expense.html")