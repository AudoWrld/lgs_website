from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from PIL import Image, ImageFilter
from django.db.models import Count, Prefetch, Q

from samples.models import Sample
from submissions.models import Submission

STAGES = ["Received", "In Analysis", "Quality Review", "Certificate", "Released"]
from coa.models import COA


def _client_coas(user):
    return COA.objects.filter(
        submission__is_submitted=True,
        submission__client__user=user,
    ).select_related("submission", "group")


@login_required
def customer_dashboard(request):
    counts = _client_coas(request.user).aggregate(
        ready=Count("id", filter=Q(status__in=[COA.READY_FOR_RELEASE, COA.RELEASED])),
        pending=Count("id", filter=Q(status=COA.PAYMENT_PENDING)),
    )
    return render(request, "client/customer_dashboard.html", counts)


@login_required
def ready_for_release(request):
    coas = (
        _client_coas(request.user)
        .filter(status__in=[COA.READY_FOR_RELEASE, COA.RELEASED])
        .order_by("-created_at")
    )
    return render(request, "client/ready_for_release.html", {"items": coas})


@login_required
def pending_release(request):
    coas = (
        _client_coas(request.user)
        .filter(status=COA.PAYMENT_PENDING)
        .order_by("-created_at")
    )
    return render(request, "client/pending_release.html", {"items": coas})


@login_required
def coa_detail(request, coa_id):
    coa = get_object_or_404(_client_coas(request.user), pk=coa_id)
    if not coa.is_client_visible:
        return redirect("client:pending_release")

    if coa.status == COA.READY_FOR_RELEASE:
        COA.objects.filter(pk=coa.pk, status=COA.READY_FOR_RELEASE).update(
            status=COA.RELEASED
        )
        COA.objects.filter(pk=coa.pk, released_at__isnull=True).update(
            released_at=timezone.now()
        )
        coa.refresh_from_db()

    return render(request, "client/coa_detail.html", {"coa": coa})


@login_required
def coa_file(request, coa_id, kind):
    if kind not in ("pdf", "png"):
        raise Http404
    coa = get_object_or_404(_client_coas(request.user), pk=coa_id)
    if not coa.is_client_visible:
        raise Http404

    field = coa.pdf_file if kind == "pdf" else coa.png_file
    if not field:
        raise Http404

    stem = coa.coa_number.replace("/", "-")
    response = FileResponse(
        field.open("rb"),
        content_type="application/pdf" if kind == "pdf" else "image/png",
        as_attachment=request.GET.get("download") == "1",
        filename=f"{stem}.{kind}",
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
def coa_preview(request, coa_id):
    coa = get_object_or_404(_client_coas(request.user), pk=coa_id)
    if not coa.png_file:
        raise Http404

    with coa.png_file.open("rb") as source:
        image = Image.open(source)
        image.load()

    if not coa.is_client_visible:
        image = image.filter(ImageFilter.GaussianBlur(radius=14))

    output = BytesIO()
    image.save(output, format="PNG")
    response = HttpResponse(output.getvalue(), content_type="image/png")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _stage_for(submission):
    coas = list(submission.coas.all())
    total = submission.total
    approved = submission.approved
    in_qc = submission.in_qc
    partial = False

    if coas and all(c.is_client_visible for c in coas):
        if approved == total:
            return 5, "Released", False
        return 3, "Quality Review", True

    if coas:
        label = (
            "Awaiting Payment"
            if any(c.status == COA.PAYMENT_PENDING for c in coas)
            else "Certificate Ready"
        )
        return 4, label, approved < total

    if total and approved == total:
        return 4, "Preparing Certificate", False
    if approved + in_qc > 0:
        return 3, "Quality Review", False
    return 2, "In Analysis", False


@login_required
def my_submissions(request):
    submissions = (
        Submission.objects.filter(is_submitted=True, client__user=request.user)
        .annotate(
            total=Count("samples", distinct=True),
            approved=Count(
                "samples",
                filter=Q(samples__analysis_status=Sample.QC_APPROVED),
                distinct=True,
            ),
            in_qc=Count(
                "samples",
                filter=Q(
                    samples__analysis_status__in=[
                        Sample.SUBMITTED_TO_QC,
                        Sample.REASSAY_SUBMITTED,
                    ]
                ),
                distinct=True,
            ),
        )
        .prefetch_related("coas")
        .order_by("-updated_at", "-id")
    )

    items = []
    for submission in submissions:
        number, label, partial = _stage_for(submission)
        items.append(
            {
                "submission": submission,
                "stage_number": number,
                "stage_label": label,
                "partial": partial,
                "steps": [
                    {
                        "name": name,
                        "done": index < number,
                        "current": index == number,
                    }
                    for index, name in enumerate(STAGES, start=1)
                ],
            }
        )
    return render(request, "client/my_submissions.html", {"items": items})
