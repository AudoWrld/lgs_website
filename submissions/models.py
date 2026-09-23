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
            if submitted_by is not None:
                self.registered_by = submitted_by
            self.save(
                update_fields=[
                    "is_submitted",
                    "submitted_at",
                    "registered_by",
                    "updated_at",
                ]
            )

        return self
