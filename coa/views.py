from django.shortcuts import get_object_or_404, render

from .models import COA


def verify_coa(request, token):
	coa = get_object_or_404(
		COA.objects.select_related("submission", "submission__client"),
		verification_token=token,
		submission__is_submitted=True,
	)
	return render(
		request,
		"coa/verify.html",
		{
			"coa": coa,
			"released": coa.is_client_visible,
		},
	)
