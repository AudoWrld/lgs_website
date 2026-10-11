from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import get_object_or_404, redirect

from .models import COA


def verify_coa(request, token):
    coa = get_object_or_404(
        COA.objects.select_related("submission", "submission__client"),
        verification_token=token,
        submission__is_submitted=True,
    )

    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())

    client = getattr(request.user, "client_profile", None)
    if client is not None and coa.submission.client_id == client.pk:
        return redirect("client:coa_detail", coa_id=coa.pk)

    if request.user.is_qc or request.user.is_administrator or request.user.is_superuser:
        return redirect("qc:report_detail", reference=coa.submission.reference)

    messages.error(request, "This certificate does not belong to your account.")
    return redirect("client:customer_dashboard")