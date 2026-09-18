from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import reception_required
from accounts.forms import ClientForm, ClientSearchForm
from accounts.models import Client, ClientEditLog
from accounts.utils import generate_temp_password, normalize_tz_phone
from submissions.models import Submission
from samples.forms import SampleForm
from samples.models import Sample

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
    return redirect(
        "reception:sample_registration_detail", submission_id=submission.pk
    )


@reception_required
def submission_use(request, slug, submission_id):
    client = get_object_or_404(Client, slug=slug)
    submission = get_object_or_404(
        Submission, pk=submission_id, client=client
    )
    request.session["active_client_id"] = client.pk
    request.session["active_submission_id"] = submission.pk
    messages.success(request, f"Using submission {submission.reference}.")
    return redirect(
        "reception:sample_registration_detail", submission_id=submission.pk
    )


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


@reception_required
def sample_registration(request):
    submissions = Submission.objects.select_related("client").prefetch_related("samples")
    return render(
        request,
        "reception/sample_registration.html",
        {"submissions": submissions},
    )


@reception_required
def sample_registration_detail(request, submission_id):
    submission = get_object_or_404(Submission.objects.select_related("client"), pk=submission_id)
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
    submission = get_object_or_404(Submission.objects.select_related("client"), pk=submission_id)
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
    submission = get_object_or_404(Submission.objects.select_related("client"), pk=submission_id)
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
    return redirect(
        "reception:sample_registration_detail", submission_id=submission_id
    )


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
