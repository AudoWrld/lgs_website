from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from accounts.decorators import reception_required
from accounts.forms import ClientForm, ClientSearchForm
from accounts.models import Client, ClientEditLog
from accounts.utils import generate_temp_password, normalize_tz_phone
from coa.models import (
    COA,
    COAGroup,
    COAGroupSample,
    COAReportingPreference,
    COAReportingPreferenceChange,
)
from expences.forms import ExpenseForm
from expences.models import Expense
from payments.models import Payment, PaymentAccount
from payments.views import payment_detail, payment_list
from reception.pdf import render_client_submission_form_pdf
from samples.forms import SampleForm
from samples.models import Sample
from submissions.models import Submission
from worksheet.models import Worksheet
from worksheet.services import generate_worksheets_for_submission

FORM_LIST_LIMIT = 60

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
    today = timezone.localdate()

    today_submissions_count = Submission.objects.filter(created_at__date=today).count()

    pending_payments_count = Payment.objects.filter(
        payment_status__in=[Payment.UNPAID, Payment.PARTIALLY_PAID]
    ).count()

    submissions_with_samples = Submission.objects.filter(
        samples__isnull=False
    ).distinct()
    submissions_with_worksheets = Worksheet.objects.values_list(
        "submission_id", flat=True
    ).distinct()
    awaiting_worksheet_count = submissions_with_samples.exclude(
        pk__in=submissions_with_worksheets
    ).count()

    todays_expenses_count = Expense.objects.filter(created_at__date=today).count()

    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    per_day = dict(
        Submission.objects.filter(created_at__date__gte=days[0])
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .values_list("day", "total")
    )
    week_counts = [per_day.get(day, 0) for day in days]
    week_labels = [day.strftime("%a") for day in days]

    recent_submissions = (
        Submission.objects.select_related("client")
        .annotate(sample_count=Count("samples", distinct=True))
        .order_by("-created_at")[:6]
    )

    max_week_count = max(week_counts) if max(week_counts) > 0 else 1
    weekly_chart = [
        {"label": label, "count": count, "height": int(count / max_week_count * 120)}
        for label, count in zip(week_labels, week_counts)
    ]

    return render(
        request,
        "reception/reception_dashboard.html",
        {
            "today_submissions_count": today_submissions_count,
            "pending_payments_count": pending_payments_count,
            "awaiting_worksheet_count": awaiting_worksheet_count,
            "todays_expenses_count": todays_expenses_count,
            "week_labels": week_labels,
            "week_counts": week_counts,
            "recent_submissions": recent_submissions,
            "weekly_chart": weekly_chart,
        },
    )


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
    queryset = client.submissions.prefetch_related("samples").order_by("-created_at")
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    page_range = paginator.get_elided_page_range(
        page_obj.number, on_each_side=1, on_ends=1
    )
    return render(
        request,
        "reception/client_submissions.html",
        {
            "client": client,
            "submissions": page_obj,
            "page_obj": page_obj,
            "paginator": paginator,
            "page_range": page_range,
        },
    )


@reception_required
def client_new_submission(request, slug):
    client = get_object_or_404(Client, slug=slug)
    submission = _start_submission_for_client(request, client)
    messages.success(request, f"New submission {submission.reference} started.")
    return redirect("reception:sample_registration_detail", slug=submission.slug)


@reception_required
def submission_use(request, slug, submission_id):
    client = get_object_or_404(Client, slug=slug)
    submission = get_object_or_404(Submission, pk=submission_id, client=client)
    request.session["active_client_id"] = client.pk
    request.session["active_submission_id"] = submission.pk
    messages.success(request, f"Using submission {submission.reference}.")
    return redirect("reception:sample_registration_detail", slug=submission.slug)


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
                    "reception:sample_registration_detail", slug=submission.slug
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
def sample_registration_detail(request, slug):
    submission = get_object_or_404(
        Submission.objects.select_related("client"), slug=slug
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
                "reception:sample_registration_detail", slug=submission.slug
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
def sample_edit(request, submission_slug, sample_slug):
    submission = get_object_or_404(
        Submission.objects.select_related("client"), slug=submission_slug
    )
    sample = get_object_or_404(
        Sample.objects.select_related("submission"),
        submission=submission,
        slug=sample_slug,
    )
    if submission.is_submitted:
        messages.warning(request, "Submitted samples cannot be edited.")
        return redirect("reception:sample_registration_detail", slug=submission.slug)

    if request.method == "POST":
        form = SampleForm(request.POST, instance=sample, submission=submission)
        if form.is_valid():
            form.save()
            messages.success(request, f"Sample {sample.client_sample_id} updated.")
            return redirect(
                "reception:sample_registration_detail", slug=submission.slug
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
    if submission.is_submitted:
        return redirect("reception:sample_registration_detail", slug=submission.slug)

    if request.method == "POST":
        try:
            submission.validate_before_submit()
        except ValidationError as exc:
            for error in exc.messages:
                messages.error(request, error)
            return redirect(
                "reception:sample_registration_detail", slug=submission.slug
            )
        return redirect(
            "reception:submission_submit_review", submission_id=submission.pk
        )

    try:
        submission.validate_before_submit()
    except ValidationError as exc:
        for error in exc.messages:
            messages.error(request, error)
        return redirect("reception:sample_registration_detail", slug=submission.slug)

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
        return redirect("reception:sample_registration_detail", slug=submission.slug)

    try:
        submission.validate_before_submit()
        submission.submit(submitted_by=request.user)
    except ValidationError as exc:
        for error in exc.messages:
            messages.error(request, error)
        return redirect("reception:sample_registration_detail", slug=submission.slug)

    messages.success(request, f"Submission {submission.reference} was submitted.")
    return redirect("reception:sample_registration_detail", slug=submission.slug)


@reception_required
def sample_remove(request, submission_slug, sample_slug):
    submission = get_object_or_404(Submission, slug=submission_slug)
    if submission.is_submitted:
        messages.warning(request, "Submitted samples cannot be removed.")
        return redirect("reception:sample_registration_detail", slug=submission.slug)

    sample = get_object_or_404(Sample, slug=sample_slug, submission=submission)
    sample_label = sample.client_sample_id
    sample.delete()
    messages.success(request, f"Sample {sample_label} removed.")
    return redirect("reception:sample_registration_detail", slug=submission.slug)


def _coa_submission(reference):
    return get_object_or_404(
        Submission.objects.prefetch_related("samples"), reference=reference
    )


def _save_coa_preference(preference, preference_type, user):
    preference.preference_type = preference_type
    preference.set_by = user
    preference.full_clean()
    preference.save()


def _coa_generation_started(submission):
    return (
        COAReportingPreference.objects.filter(
            submission=submission, is_finalized=True
        ).exists()
        or COA.objects.filter(submission=submission).exists()
    )


def _log_coa_change(
    preference, user, action, previous_type="", new_type="", group_number=None
):
    COAReportingPreferenceChange.objects.create(
        preference=preference,
        changed_by=user,
        action=action,
        previous_preference_type=previous_type,
        new_preference_type=new_type,
        group_number=group_number,
    )


@reception_required
def coa_reporting_preference(request, reference):
    submission = _coa_submission(reference)
    total_samples = submission.total_samples
    preference = COAReportingPreference.objects.filter(submission=submission).first()
    changing = request.GET.get("change") == "1"

    if (
        changing
        and preference is not None
        and preference.is_finalized
        and _coa_generation_started(submission)
    ):
        messages.error(
            request,
            "This reporting preference is locked because COA generation has started.",
        )
        return redirect("reception:coa_confirmation", reference=reference)

    if total_samples == 1:
        if preference is None:
            preference = COAReportingPreference(
                submission=submission,
                preference_type=COAReportingPreference.INDIVIDUAL,
            )
        try:
            _save_coa_preference(
                preference, COAReportingPreference.INDIVIDUAL, request.user
            )
            if not preference.is_finalized:
                preference.is_finalized = True
                preference.finalized_at = timezone.now()
                preference.finalized_by = request.user
                preference.save(
                    update_fields=[
                        "is_finalized",
                        "finalized_at",
                        "finalized_by",
                        "saved_at",
                    ]
                )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect(
                "reception:sample_registration_detail", slug=submission.slug
            )
        return redirect("reception:coa_confirmation", reference=reference)

    if request.method == "GET" and not changing and preference is not None:
        if preference.preference_type == COAReportingPreference.CUSTOM_GROUP:
            if preference.all_samples_assigned():
                return redirect("reception:coa_confirmation", reference=reference)
            return redirect("reception:coa_custom_group_wizard", reference=reference)
        if preference.preference_type in (
            COAReportingPreference.INDIVIDUAL,
            COAReportingPreference.COMBINED,
        ):
            return redirect("reception:coa_confirmation", reference=reference)

    if request.method == "POST":
        preference_type = request.POST.get("preference_type")
        allowed = {COAReportingPreference.INDIVIDUAL, COAReportingPreference.COMBINED}
        if total_samples >= 3:
            allowed.add(COAReportingPreference.CUSTOM_GROUP)
        if preference_type not in allowed:
            return render(
                request,
                "reception/coa_reporting_preference.html",
                {
                    "submission": submission,
                    "total_samples": total_samples,
                    "error": "Choose a valid reporting preference.",
                },
            )

        try:
            with transaction.atomic():
                if preference is None:
                    preference = COAReportingPreference(submission=submission)
                previous_type = preference.preference_type
                if preference.is_finalized and _coa_generation_started(submission):
                    raise ValidationError(
                        "This reporting preference is locked because COA generation has started."
                    )
                _save_coa_preference(preference, preference_type, request.user)
                if preference.is_finalized and previous_type != preference_type:
                    _log_coa_change(
                        preference,
                        request.user,
                        "SELECTION_CHANGED",
                        previous_type=previous_type,
                        new_type=preference_type,
                    )
                if preference_type == COAReportingPreference.CUSTOM_GROUP:
                    preference.is_finalized = False
                    preference.finalized_at = None
                    preference.finalized_by = None
                    preference.save(
                        update_fields=[
                            "is_finalized",
                            "finalized_at",
                            "finalized_by",
                            "saved_at",
                        ]
                    )
                else:
                    preference.groups.all().delete()
                    preference.is_finalized = False
                    preference.finalized_at = None
                    preference.finalized_by = None
                    preference.save(
                        update_fields=[
                            "is_finalized",
                            "finalized_at",
                            "finalized_by",
                            "saved_at",
                        ]
                    )
        except ValidationError as exc:
            return render(
                request,
                "reception/coa_reporting_preference.html",
                {
                    "submission": submission,
                    "total_samples": total_samples,
                    "error": exc.messages[0],
                },
            )

        if preference_type == COAReportingPreference.CUSTOM_GROUP:
            return redirect("reception:coa_custom_group_wizard", reference=reference)
        return redirect("reception:coa_confirmation", reference=reference)

    return render(
        request,
        "reception/coa_reporting_preference.html",
        {
            "submission": submission,
            "total_samples": total_samples,
            "preference": preference,
        },
    )


@reception_required
def coa_custom_group_wizard(request, reference):
    submission = _coa_submission(reference)
    total_samples = submission.total_samples
    preference = get_object_or_404(
        COAReportingPreference,
        submission=submission,
        preference_type=COAReportingPreference.CUSTOM_GROUP,
    )
    if preference.is_finalized and _coa_generation_started(submission):
        messages.error(
            request,
            "This reporting preference is locked because COA generation has started.",
        )
        return redirect("reception:coa_confirmation", reference=reference)
    assigned_ids = COAGroupSample.objects.filter(
        group__preference=preference
    ).values_list("sample_id", flat=True)
    available_samples = list(submission.samples.exclude(pk__in=assigned_ids))
    next_group_number = preference.groups.count() + 1

    if request.method == "POST":
        selected_ids = request.POST.getlist("sample_ids")
        if not selected_ids:
            return render(
                request,
                "reception/coa_custom_group_wizard.html",
                {
                    "submission": submission,
                    "preference": preference,
                    "available_samples": available_samples,
                    "next_group_number": next_group_number,
                    "error": "Select at least one sample for this group.",
                },
            )
        selected_samples = list(
            submission.samples.filter(pk__in=selected_ids).exclude(pk__in=assigned_ids)
        )
        if not selected_samples:
            messages.error(request, "UNASSIGNED SAMPLES REMAIN")
            return redirect("reception:coa_custom_group_wizard", reference=reference)
        try:
            with transaction.atomic():
                group = COAGroup.objects.create(
                    preference=preference, group_number=next_group_number
                )
                COAGroupSample.objects.bulk_create(
                    [
                        COAGroupSample(group=group, sample=sample)
                        for sample in selected_samples
                    ]
                )
                if preference.is_finalized:
                    _log_coa_change(
                        preference,
                        request.user,
                        "GROUP_ADDED",
                        group_number=next_group_number,
                    )
        except IntegrityError:
            messages.error(
                request,
                "One or more selected samples were already assigned. Please try again.",
            )
            return redirect("reception:coa_custom_group_wizard", reference=reference)

        if preference.all_samples_assigned():
            return redirect("reception:coa_final_review", reference=reference)
        return redirect("reception:coa_custom_group_wizard", reference=reference)

    if not available_samples:
        if preference.all_samples_assigned():
            return redirect("reception:coa_final_review", reference=reference)
        messages.error(request, "UNASSIGNED SAMPLES REMAIN")

    return render(
        request,
        "reception/coa_custom_group_wizard.html",
        {
            "submission": submission,
            "preference": preference,
            "available_samples": available_samples,
            "next_group_number": next_group_number,
            "remaining_count": len(available_samples),
            "total_samples": total_samples,
        },
    )


@reception_required
def coa_final_review(request, reference):
    submission = _coa_submission(reference)
    preference = get_object_or_404(
        COAReportingPreference,
        submission=submission,
        preference_type=COAReportingPreference.CUSTOM_GROUP,
    )
    if preference.is_finalized and _coa_generation_started(submission):
        messages.error(
            request,
            "This reporting preference is locked because COA generation has started.",
        )
        return redirect("reception:coa_confirmation", reference=reference)
    if not preference.all_samples_assigned():
        return redirect("reception:coa_custom_group_wizard", reference=reference)
    groups = preference.groups.prefetch_related("samples").all()
    return render(
        request,
        "reception/coa_final_review.html",
        {"submission": submission, "preference": preference, "groups": groups},
    )


@reception_required
def coa_group_delete(request, reference, group_number):
    submission = _coa_submission(reference)
    preference = get_object_or_404(
        COAReportingPreference,
        submission=submission,
        preference_type=COAReportingPreference.CUSTOM_GROUP,
    )
    if preference.is_finalized and _coa_generation_started(submission):
        messages.error(
            request,
            "This reporting preference is locked because COA generation has started.",
        )
        return redirect("reception:coa_confirmation", reference=reference)
    group = get_object_or_404(preference.groups, group_number=group_number)
    if request.method == "POST":
        group.delete()
        if preference.is_finalized:
            _log_coa_change(
                preference,
                request.user,
                "GROUP_DELETED",
                group_number=group_number,
            )
        messages.success(
            request, f"Group {group_number} removed. Assign its samples again."
        )
        return redirect("reception:coa_custom_group_wizard", reference=reference)
    return redirect("reception:coa_final_review", reference=reference)


@reception_required
def coa_confirmation(request, reference):
    submission = _coa_submission(reference)
    preference = get_object_or_404(COAReportingPreference, submission=submission)
    if request.method == "POST":
        if preference.is_finalized and _coa_generation_started(submission):
            messages.error(
                request,
                "This reporting preference is locked because COA generation has started.",
            )
            return redirect("reception:coa_confirmation", reference=reference)
        if (
            preference.preference_type == COAReportingPreference.CUSTOM_GROUP
            and not preference.all_samples_assigned()
        ):
            messages.error(request, "UNASSIGNED SAMPLES REMAIN")
            return redirect("reception:coa_custom_group_wizard", reference=reference)
        preference.is_finalized = True
        preference.finalized_at = timezone.now()
        preference.finalized_by = request.user
        preference.save(
            update_fields=["is_finalized", "finalized_at", "finalized_by", "saved_at"]
        )
        messages.success(request, "Reporting preference saved")
        return redirect("reception:coa_confirmation", reference=reference)
    groups = preference.groups.prefetch_related("samples").all()
    return render(
        request,
        "reception/coa_confirmation.html",
        {
            "submission": submission,
            "preference": preference,
            "groups": groups,
            "can_edit": not _coa_generation_started(submission),
        },
    )


def _services_and_methods(submission):
    services = set()
    methods = set()
    for sample in submission.samples.all():
        for sample_service in sample.sample_services.select_related("service").all():
            services.add(sample_service.service.name)
            if sample_service.service.method_of_analysis:
                methods.add(sample_service.service.method_of_analysis)
    return sorted(services), sorted(methods)


def _service_rows(submission):
    found = {}
    for sample in submission.samples.all():
        for sample_service in sample.sample_services.select_related("service").all():
            service = sample_service.service
            found.setdefault(service.name, service.method_of_analysis or "")
    return [{"name": name, "method": method} for name, method in sorted(found.items())]


def _portal_login(request, client, consume):
    username = client.portal_user.email if client.portal_user else None
    temp_password = None
    if not consume:
        return username, temp_password

    session = request.session
    if session.get("last_registered_client_id") == client.pk and session.get(
        "last_registered_temp_password"
    ):
        temp_password = session.pop("last_registered_temp_password")
        session.pop("last_registered_client_id", None)
        session.modified = True
    elif session.get("reissued_client_id") == client.pk and session.get(
        "reissued_temp_password"
    ):
        temp_password = session.pop("reissued_temp_password")
        session.pop("reissued_client_id", None)
        session.modified = True
    return username, temp_password


def _form_context(request, submission, consume_password=True):
    client = submission.client
    samples = submission.samples.all()

    payment, _ = Payment.objects.get_or_create(submission=submission)
    payment.recalculate_gross_amount()
    payment.save(update_fields=["gross_amount"])

    net = payment.net_amount_payable
    paid_percent = 0
    if net > 0:
        paid_percent = int(min(Decimal("100"), payment.total_amount_paid / net * 100))
    elif payment.total_amount_paid > 0:
        paid_percent = 100

    services, methods = _services_and_methods(submission)
    portal_username, temp_password = _portal_login(request, client, consume_password)
    has_outstanding = payment.payment_status in (Payment.UNPAID, Payment.PARTIALLY_PAID)

    return {
        "submission": submission,
        "client": client,
        "payment": payment,
        "total_samples": samples.count(),
        "sample_types": sorted(set(s.get_sample_type_display() for s in samples)),
        "services": services,
        "methods": methods,
        "service_rows": _service_rows(submission),
        "paid_percent": paid_percent,
        "has_outstanding": has_outstanding,
        "payment_accounts": (
            PaymentAccount.objects.filter(is_active=True) if has_outstanding else []
        ),
        "portal_username": portal_username,
        "temp_password": temp_password,
        "can_reissue_password": bool(
            client.portal_user and client.portal_user.must_change_password
        ),
        "site_url": request.build_absolute_uri("/"),
    }


@reception_required
def client_submission_form(request):
    query = request.GET.get("q", "").strip()
    reference = request.GET.get("ref", "").strip()
    list_only = request.GET.get("list") == "1"

    submission = None
    extra = {}
    if reference:
        submission = (
            Submission.objects.filter(is_submitted=True, reference__iexact=reference)
            .select_related("client")
            .first()
        )
    if submission and not list_only:
        extra = _form_context(request, submission)

    scoped = Submission.objects.filter(is_submitted=True)
    if query:
        scoped = scoped.filter(
            Q(reference__icontains=query) | Q(client__client_name__icontains=query)
        )
    match_count = scoped.count()
    submissions = list(
        scoped.select_related("client", "payment")
        .annotate(sample_count=Count("samples", distinct=True))
        .order_by("-created_at")[:FORM_LIST_LIMIT]
    )

    context = {
        "query": query,
        "reference": reference,
        "submissions": submissions,
        "match_count": match_count,
        "list_limit": FORM_LIST_LIMIT,
        "submission": submission,
        "not_found": bool(reference) and submission is None,
    }
    context.update(extra)
    return render(request, "reception/client_submission_form.html", context)


@reception_required
def client_submission_form_detail(request, reference):
    url = reverse("reception:client_submission_form")
    return redirect(f"{url}?{urlencode({'ref': reference})}")


@reception_required
def client_reissue_temp_password(request, reference):
    submission = get_object_or_404(Submission, reference=reference)
    client = submission.client

    if not client.portal_user:
        messages.error(request, "This client has no portal account yet.")
        return redirect("reception:client_submission_form_detail", reference=reference)

    if not client.portal_user.must_change_password:
        messages.warning(
            request,
            "This client has already logged in and set their own password — "
            "reissuing is not available. Ask them to use 'Forgot Password' instead.",
        )
        return redirect("reception:client_submission_form_detail", reference=reference)

    new_temp_password = generate_temp_password()
    client.portal_user.set_password(new_temp_password)
    client.portal_user.must_change_password = True
    client.portal_user.save(update_fields=["password", "must_change_password"])

    request.session["reissued_temp_password"] = new_temp_password
    request.session["reissued_client_id"] = client.pk

    messages.success(request, "New temporary password generated.")
    return redirect("reception:client_submission_form_detail", reference=reference)


@reception_required
def client_submission_form_pdf(request, reference):
    submission = get_object_or_404(
        Submission.objects.select_related("client"),
        reference=reference,
        is_submitted=True,
    )
    context = _form_context(request, submission)

    pdf_bytes = render_client_submission_form_pdf(context)

    filename = (
        f"LGS_Client_Submission_Form_{submission.reference.replace('/', '-')}.pdf"
    )
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    disposition = "inline" if request.GET.get("view") == "1" else "attachment"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return response


@reception_required
def generate_worksheet(request):
    submissions = (
        Submission.objects.filter(is_submitted=True)
        .select_related("client")
        .annotate(sample_count=Count("samples", distinct=True))
        .order_by("-created_at")
    )
    query = request.GET.get("q", "").strip()
    if query:
        submissions = submissions.filter(
            Q(reference__icontains=query) | Q(client__client_name__icontains=query)
        )

    return render(
        request,
        "reception/worksheet_list.html",
        {"submissions": submissions, "query": query},
    )


@reception_required
def generate_worksheet_detail(request, reference):
    submission = get_object_or_404(
        Submission.objects.select_related("client"),
        reference=reference,
        is_submitted=True,
    )

    if request.method == "POST":
        submission.worksheets.all().delete()
        generate_worksheets_for_submission(submission, request.user)
        messages.success(request, f"Worksheets generated for {submission.reference}.")
        return redirect("reception:generate_worksheet_detail", reference=reference)

    worksheets = submission.worksheets.prefetch_related(
        "rows", "rows__lab_sample_mapping"
    ).all()
    return render(
        request,
        "reception/generate_worksheet.html",
        {"submission": submission, "worksheets": worksheets},
    )


@reception_required
def add_expense(request):
    if request.method == "POST":
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.is_submitted = False
            expense.added_by = request.user
            expense.save()
            return redirect("reception:expense_edit", slug=expense.slug)
    else:
        form = ExpenseForm()

    return render(request, "reception/expense_add.html", {"form": form})


@reception_required
def expense_edit(request, slug):
    expense = get_object_or_404(Expense.reception_visible, slug=slug)

    if request.method == "POST":
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            action = request.POST.get("action")
            if action == "submit":
                expense = form.save(commit=False)
                expense.is_submitted = True
                expense.submitted_at = timezone.now()
                expense.save()
                messages.success(request, "Expense submitted successfully.")
                return redirect("reception:add_expense")

            form.save()
            messages.success(request, "Expense changes saved.")
            return redirect("reception:expense_edit", slug=expense.slug)
    else:
        form = ExpenseForm(instance=expense)

    return render(
        request,
        "reception/expense_edit.html",
        {"form": form, "expense": expense},
    )
