from django.shortcuts import render

from accounts.decorators import accountant_required


@accountant_required
def dashboard(request):
	return render(request, "accountant/dashboard.html")
