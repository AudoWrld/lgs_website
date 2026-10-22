from django.http import JsonResponse
from django.shortcuts import render

from accounts.decorators import administrator_required
from branches.models import Branch


@administrator_required
def admin_dashboard(request):
    return render(request, "administrator/dashboard.html")


@administrator_required
def branch_options(request):
    branches = (
        Branch.objects.filter(is_active=True).order_by("name").values("id", "name")
    )
    return JsonResponse({"branches": list(branches), "default_id": 1})
