from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify


def _default_receiving_date():
    return timezone.localdate()


def _default_receiving_time():
    return timezone.localtime().time()


class DailySubmissionSequence(models.Model):
    date = models.DateField(unique=True)
    last_sequence = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Daily Submission Sequence"
        verbose_name_plural = "Daily Submission Sequences"

    def __str__(self):
        return f"{self.date} — last {self.last_sequence:02d}"


class Submission(models.Model):
    REGISTRATION_DRAFT = "REGISTRATION_DRAFT"

    SUBMITTED_TO_LAB = "SUBMITTED_TO_LAB"
    DRAFT = "DRAFT"
    READY_FOR_SUBMISSION = "READY_FOR_SUBMISSION"
    SUBMITTED_TO_QC = "SUBMITTED_TO_QC"
    REASSAY_REQUIRED = "REASSAY_REQUIRED"
    REASSAY_SUBMITTED = "REASSAY_SUBMITTED"
    QC_APPROVED = "QC_APPROVED"

    STATUS_CHOICES = [
        (REGISTRATION_DRAFT, "Registration Draft"),
        (SUBMITTED_TO_LAB, "Submitted to Lab"),
        (DRAFT, "Draft"),
        (READY_FOR_SUBMISSION, "Ready for Submission"),
        (SUBMITTED_TO_QC, "Submitted to QC"),
        (REASSAY_REQUIRED, "Reassay Required"),
        (REASSAY_SUBMITTED, "Reassay Submitted"),
        (QC_APPROVED, "QC Approved"),
    ]

    SAMPLE_STATUS_PRIORITY = [
        REASSAY_REQUIRED,
        SUBMITTED_TO_LAB,
        DRAFT,
        READY_FOR_SUBMISSION,
        SUBMITTED_TO_QC,
        REASSAY_SUBMITTED,
        QC_APPROVED,
    ]

    reference = models.CharField(
        max_length=20, unique=True, db_index=True, editable=False
    )
    slug = models.SlugField(max_length=80, unique=True, db_index=True, editable=False)

    client = models.ForeignKey(
        "accounts.Client",
        on_delete=models.PROTECT,
        related_name="submissions",
    )

    receiving_date = models.DateField(default=_default_receiving_date)
    receiving_time = models.TimeField(default=_default_receiving_time)

    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions_registered",
        limit_choices_to={"role": "RECEPTION"},
    )

    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=25,
        choices=STATUS_CHOICES,
        default=REGISTRATION_DRAFT,
        db_index=True,
        help_text=(
            "Registration Draft while Reception is still adding samples. "
            "Moves to Submitted to Lab for Data Entry once the submission "
            "is finalized. From there it tracks the most advanced/urgent "
            "stage across all samples — kept in sync via "
            "sync_status_from_samples()."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference

    @property
    def total_samples(self):
        return self.samples.count()

    @classmethod
    def generate_reference(cls, for_date=None):
        for_date = for_date or timezone.localdate()
        with transaction.atomic():
            seq, _ = DailySubmissionSequence.objects.select_for_update().get_or_create(
                date=for_date
            )
            seq.last_sequence += 1
            seq.save(update_fields=["last_sequence"])
            return f"LGS/{for_date:%y%m%d}/{seq.last_sequence:02d}"

    @classmethod
    def generate_slug(cls, reference):
        base_slug = slugify(reference) or "submission"
        candidate = base_slug
        suffix = 2
        while cls.objects.filter(slug=candidate).exists():
            candidate = f"{base_slug}-{suffix}"
            suffix += 1
        return candidate

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self.generate_reference(self.receiving_date)
        if not self.slug:
            self.slug = self.generate_slug(self.reference)
        super().save(*args, **kwargs)

    def validate_before_submit(self):
        errors = []

        if self.is_submitted:
            errors.append("This submission has already been finalized.")

        if self.total_samples == 0:
            errors.append("Add at least one sample before submitting.")

        client_sample_ids = list(
            self.samples.values_list("client_sample_id", flat=True)
        )
        if len(client_sample_ids) != len(set(client_sample_ids)):
            errors.append("Duplicate Sample IDs found within this submission.")

        for sample in self.samples.all():
            try:
                sample.validate_registration_complete()
            except ValidationError as exc:
                errors.extend(
                    f"{sample.client_sample_id or 'Unnamed sample'}: {message}"
                    for message in exc.messages
                )

        if errors:
            raise ValidationError(errors)

    def submit(self, submitted_by=None):
        self.validate_before_submit()

        with transaction.atomic():
            self.is_submitted = True
            self.submitted_at = timezone.now()
            self.status = self.SUBMITTED_TO_LAB
            if submitted_by is not None:
                self.registered_by = submitted_by
            self.save(
                update_fields=[
                    "is_submitted",
                    "submitted_at",
                    "status",
                    "registered_by",
                    "updated_at",
                ]
            )

        return self

    def sync_status_from_samples(self, save=True):
        if not self.is_submitted:
            return self.status

        statuses = set(self.samples.values_list("analysis_status", flat=True))
        new_status = self.status

        for candidate in self.SAMPLE_STATUS_PRIORITY:
            if candidate in statuses:
                new_status = candidate
                break

        if new_status != self.status:
            self.status = new_status
            if save:
                self.save(update_fields=["status", "updated_at"])

        return self.status
