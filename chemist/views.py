from django.shortcuts import render

def chemist_dashboard(request):
    return render(request, "chemist/chemist_dashboard.html")