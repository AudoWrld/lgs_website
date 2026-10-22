from django.shortcuts import render
from accounts.decorators import administrator_required


@administrator_required
def admin_dashboard(request):
    return render(request, "administrator/dashboard.html")
