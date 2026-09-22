from django.shortcuts import render

def customer_dashboard(request):
    return render(request, "client/customer_dashboard.html")