from django.urls import path
from . import views

app_name = "chemist"

urlpatterns = [
    path("dashbord/", views.chemist_dashboard, name="chemist_dashboard"),
    path("mineral_analysis/", views.mineral_analysis, name="mineral_analysis"),
    path(
        "metallurgical_analysis/",
        views.metallurgical_analysis,
        name="metallurgical_analysis",
    ),
    path("reassay_samples/", views.reassay_samples, name="reassay_samples"),
    path("qc_approved/", views.qc_approved, name="qc_approved"),
]
