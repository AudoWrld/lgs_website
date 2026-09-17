from django.shortcuts import render

def reception_dashboard(request):
    return render(request, "reception/reception_dashboard.html")