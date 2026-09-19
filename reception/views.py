from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from accounts.decorators import reception_required
from accounts.forms import ClientForm, ClientSearchForm
from accounts.models import Client, ClientEditLog
from accounts.utils import generate_temp_password, normalize_tz_phone
from samples.forms import SampleForm
from samples.models import Sample
from submissions.models import Submission

PAGE_SIZE = 10

SORT_OPTIONS = {
    "newest": ("-created_at",),
    "oldest": ("created_at",),
    "samples": ("-sample_count", "-created_at"),
    "reference": ("reference",),
}

User = get_user_model()


@reception_required
def reception_dashboard(request):
    return render(request, "reception/reception_dashboard.html")


@reception_required
def client_search(request):
    form = ClientSearchForm(request.GET or None)
    results = []
    searched = False

    if form.is_valid():
        searched = True
        query = form.cleaned_data["query"]
        normalized_phone = normalize_tz_phone(query)

        results = (
            Client.objects.filter(
                Q(client_name__icontains=query)
                | Q(contact_person__icontains=query)
                | Q(email__icontains=query)
                | Q(whatsapp_number=normalized_phone)
                | Q(whatsapp_number__icontains=query)
            )
            .distinct()
            .order_by("client_name")
        )

    return render(
        request,
        "reception/client_search.html",
        {"form": form, "results": results, "searched": searched},
    )


def _start_submission_for_client(request, client):
    submission = Submission.objects.create(
        client=client,
        registered_by=request.user,
    )
    request.session["active_client_id"] = client.pk
    request.session["active_submission_id"] = submission.pk
    return submission


@reception_required
def client_submissions(request, slug):
    client = get_object_or_404(Client, slug=slug)
    submissions = client.submissions.prefetch_related("samples")
    return render(
        request,
        "reception/client_submissions.html",
        {"client": client, "submissions": submissions},
    )


@reception_required
def client_new_submission(request, slug):
    client = get_object_or_404(Client, slug=slug)
    submission = _start_submission_for_client(request, client)
    messages.success(request, f"New submission {submission.reference} started.")
    return redirect("reception:sample_registration_detail", submission_id=submission.pk)


@reception_required
def submission_use(request, slug, submission_id):
    client = get_object_or_404(Client, slug=slug)
    submission = get_object_or_404(Submission, pk=submission_id, client=client)
    request.session["active_client_id"] = client.pk
    request.session["active_submission_id"] = submission.pk
    messages.success(request, f"Using submission {submission.reference}.")
    return redirect("reception:sample_registration_detail", submission_id=submission.pk)


@reception_required
def client_edit(request, slug):
    client = get_object_or_404(Client, slug=slug)

    if request.method == "POST":
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            previous = {
                "client_type": client.client_type,
                "client_name": client.client_name,
                "contact_person": client.contact_person,
                "email": client.email,
                "whatsapp_number": client.whatsapp_number,
            }

            updated_client = form.save(commit=False)
            changed = any(
                getattr(updated_client, field) != previous[field] for field in previous
            )

            if changed:
                ClientEditLog.objects.create(
                    client=client,
                    edited_by=request.user,
                    previous_client_type=previous["client_type"],
                    previous_client_name=previous["client_name"],
                    previous_contact_person=previous["contact_person"],
                    previous_email=previous["email"],
                    previous_whatsapp_number=previous["whatsapp_number"],
                )

            updated_client.save()
            messages.success(
                request, f"Client information updated for {updated_client.client_name}."
            )
            return redirect("reception:client_search")
    else:
        form = ClientForm(instance=client)

    return render(
        request, "reception/client_edit.html", {"form": form, "client": client}
    )


@reception_required
def client_register(request):
    duplicates = []
    form = ClientForm(request.POST or None)

    if request.method == "POST":
        confirmed = request.POST.get("confirm_new") == "1"

        if form.is_valid():
            cleaned = form.cleaned_data
            duplicates = Client.find_possible_duplicates(
                client_name=cleaned["client_name"],
                email=cleaned["email"],
                whatsapp_number=cleaned["whatsapp_number"],
            )

            if duplicates.exists() and not confirmed:
                messages.warning(
                    request,
                    "POSSIBLE EXISTING CLIENT FOUND — please review before creating a new record.",
                )
            else:
                temp_password = generate_temp_password()

                portal_user = User.objects.create_customer(
                    email=cleaned["email"],
                    password=temp_password,
                    created_by=request.user,
                    whatsapp_number=cleaned["whatsapp_number"],
                    must_change_password=True,
                )

                client = form.save(commit=False)
                client.portal_user = portal_user
                client.registered_by = request.user
                client.save()

                request.session["last_registered_temp_password"] = temp_password
                request.session["last_registered_client_id"] = client.pk

                submission = _start_submission_for_client(request, client)

                messages.success(
                    request,
                    f"Client registered: {client.client_name} — submission {submission.reference} started.",
                )
                return redirect(
                    "reception:sample_registration_detail",
                    submission_id=submission.pk,
                )

    return render(
        request,
        "reception/client_register.html",
        {"form": form, "duplicates": duplicates},
    )


def build_stats():
    today = timezone.localdate()
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    per_day = dict(
        Submission.objects.filter(created_at__date__gte=days[0])
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .values_list("day", "total")
    )
    week_counts = [per_day.get(day, 0) for day in days]
    return {
        "total": Submission.objects.count(),
        "today": Submission.objects.filter(created_at__date=today).count(),
        "pending": Submission.objects.filter(is_submitted=False).count(),
        "submitted": Submission.objects.filter(is_submitted=True).count(),
        "total_samples": Sample.objects.count(),
        "week_labels": [day.strftime("%a") for day in days],
        "week_counts": week_counts,
        "week_total": sum(week_counts),
    }


def parse_date_param(value):
    try:
        return parse_date(value) if value else None
    except ValueError:
        return None


@reception_required
def submission_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")
    if status not in ("all", "pending", "submitted"):
        status = "all"
    sort = request.GET.get("sort", "newest")
    if sort not in SORT_OPTIONS:
        sort = "newest"
    date_from = parse_date_param(request.GET.get("date_from"))
    date_to = parse_date_param(request.GET.get("date_to"))

    submissions = Submission.objects.select_related("client", "registered_by").annotate(
        sample_count=Count("samples", distinct=True),
        test_count=Count("samples__sample_services", distinct=True),
    )

    if query:
        submissions = submissions.filter(
            Q(reference__icontains=query)
            | Q(client__client_name__icontains=query)
            | Q(client__contact_person__icontains=query)
            | Q(
                pk__in=Sample.objects.filter(client_sample_id__icontains=query).values(
                    "submission_id"
                )
            )
        )
    if status == "pending":
        submissions = submissions.filter(is_submitted=False)
    elif status == "submitted":
        submissions = submissions.filter(is_submitted=True)
    if date_from:
        submissions = submissions.filter(created_at__date__gte=date_from)
    if date_to:
        submissions = submissions.filter(created_at__date__lte=date_to)

    submissions = submissions.order_by(*SORT_OPTIONS[sort])

    paginator = Paginator(submissions, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    page_obj.object_list = list(page_obj.object_list)

    type_labels = dict(Sample.SAMPLE_TYPE_CHOICES)
    breakdown = {}
    type_rows = (
        Sample.objects.filter(
            submission_id__in=[item.pk for item in page_obj.object_list]
        )
        .values("submission_id", "sample_type")
        .annotate(total=Count("id"))
        .order_by("sample_type")
    )
    for row in type_rows:
        label = type_labels.get(row["sample_type"], row["sample_type"])
        breakdown.setdefault(row["submission_id"], []).append(
            f"{label} × {row['total']}"
        )

    for item in page_obj.object_list:
        item.type_summary = breakdown.get(item.pk, [])

    active = {
        "q": query,
        "status": status if status != "all" else "",
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "sort": sort if sort != "newest" else "",
    }
    active = {key: value for key, value in active.items() if value}
    without_status = {key: value for key, value in active.items() if key != "status"}

    context = {
        "page_obj": page_obj,
        "page_range": paginator.get_elided_page_range(
            number=page_obj.number, on_each_side=1, on_ends=1
        ),
        "ellipsis": paginator.ELLIPSIS,
        "stats": build_stats(),
        "query": query,
        "status": status,
        "sort": sort,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "qs_page": urlencode(active),
        "qs_status": urlencode(without_status),
        "has_filters": bool(active),
    }
    return render(request, "reception/submission_list.html", context)


@reception_required
def sample_registration_detail(request, submission_id):
    submission = get_object_or_404(
        Submission.objects.select_related("client"), pk=submission_id
    )
    request.session["active_client_id"] = submission.client_id
    request.session["active_submission_id"] = submission.pk
    samples = submission.samples.all().order_by("id")

    if submission.is_submitted:
        form = None
    elif request.method == "POST":
        form = SampleForm(request.POST, submission=submission)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.submission = submission
            sample.added_by = request.user
            sample.save()
            form.save_m2m()
            messages.success(request, f"Sample {sample.client_sample_id} added.")
            return redirect(
                "reception:sample_registration_detail", submission_id=submission.pk
            )
    else:
        form = SampleForm(submission=submission)

    return render(
        request,
        "reception/sample_registration_detail.html",
        {
            "submission": submission,
            "samples": samples,
            "form": form,
        },
    )


@reception_required
def sample_edit(request, pk):
    sample = get_object_or_404(Sample.objects.select_related("submission"), pk=pk)
    submission = sample.submission
    if submission.is_submitted:
        messages.warning(request, "Submitted samples cannot be edited.")
        return redirect(
            "reception:sample_registration_detail", submission_id=submission.pk
        )

    samples = submission.samples.all().order_by("id")
    if request.method == "POST":
        form = SampleForm(request.POST, instance=sample, submission=submission)
        if form.is_valid():
            form.save()
            messages.success(request, f"Sample {sample.client_sample_id} updated.")
            return redirect(
                "reception:sample_registration_detail", submission_id=submission.pk
            )
    else:
        form = SampleForm(instance=sample, submission=submission)

    return render(
        request,
        "reception/sample_edit.html",
        {
            "submission": submission,
            "form": form,
            "sample": sample,
        },
    )


@reception_required
def submission_submit_review(request, submission_id):
    submission = get_object_or_404(
        Submission.objects.select_related("client"), pk=submission_id
    )
    if request.method != "POST":
        return redirect(
            "reception:sample_registration_detail", submission_id=submission.pk
        )

    try:
        submission.validate_before_submit()
    except ValidationError as exc:
        for error in exc.messages:
            messages.error(request, error)
        return redirect(
            "reception:sample_registration_detail", submission_id=submission.pk
        )

    return render(
        request,
        "reception/submission_confirm.html",
        {
            "submission": submission,
            "samples": submission.samples.all().order_by("id"),
        },
    )


@reception_required
def submission_confirm_submit(request, submission_id):
    submission = get_object_or_404(
        Submission.objects.select_related("client"), pk=submission_id
    )
    if request.method != "POST":
        return redirect(
            "reception:sample_registration_detail", submission_id=submission.pk
        )

    try:
        submission.validate_before_submit()
        submission.submit(submitted_by=request.user)
    except ValidationError as exc:
        for error in exc.messages:
            messages.error(request, error)
        return redirect(
            "reception:sample_registration_detail", submission_id=submission.pk
        )

    messages.success(request, f"Submission {submission.reference} was submitted.")
    return redirect("reception:sample_registration")


@reception_required
def sample_remove(request, submission_id, pk):
    submission = get_object_or_404(Submission, pk=submission_id)
    if submission.is_submitted:
        messages.warning(request, "Submitted samples cannot be removed.")
        return redirect(
            "reception:sample_registration_detail", submission_id=submission.pk
        )

    sample = get_object_or_404(Sample, pk=pk, submission=submission)
    sample_label = sample.client_sample_id
    sample.delete()
    messages.success(request, f"Sample {sample_label} removed.")
    return redirect("reception:sample_registration_detail", submission_id=submission_id)


@reception_required
def coa_reporting_preference(request):
    return render(request, "reception/coa_reporting_preference.html")


@reception_required
def generate_worksheet(request):
    return render(request, "reception/generate_worksheet.html")


@reception_required
def client_submission_form(request):
    return render(request, "reception/client_submission_form.html")


@reception_required
def payment_details(request):
    return render(request, "reception/payment_details.html")


@reception_required
def add_expense(request):
    return render(request, "reception/add_expense.html")
