from django.shortcuts import render

from accounts.decorators import accountant_required


@accountant_required
def dashboard(request):
	return render(request, "accountant/dashboard.html")


@accountant_required
def placeholder(request, heading):
	return render(request, "accountant/placeholder.html", {"heading": heading})
