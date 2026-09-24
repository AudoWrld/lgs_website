from django.urls import path
from . import views

app_name = "chemist"

urlpatterns = [
    path("dashbord/", views.chemist_dashboard, name="chemist_dashboard"),
]
