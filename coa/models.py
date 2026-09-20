from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class COAReportingPreference(models.Model):
    INDIVIDUAL = "INDIVIDUAL"
    COMBINED = "COMBINED"
    CUSTOM_GROUP = "CUSTOM_GROUP"

    PREFERENCE_CHOICES = [
        (INDIVIDUAL, "Individual COA"),
        (COMBINED, "Combined COA"),
        (CUSTOM_GROUP, "Custom Group COA"),
    ]

    submission = models.OneToOneField(
        "submissions.Submission",
        on_delete=models.CASCADE,
        related_name="coa_preference",
    )

    preference_type = models.CharField(max_length=15, choices=PREFERENCE_CHOICES)

    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coa_preferences_set",
    )
    saved_at = models.DateTimeField(auto_now=True)
    is_finalized = models.BooleanField(default=False)
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coa_preferences_finalized",
    )

    class Meta:
        verbose_name = "COA Reporting Preference"

    def __str__(self):
        return f"{self.submission.reference} — {self.get_preference_type_display()}"

    def clean(self):
        total = self.submission.total_samples
        if total == 1 and self.preference_type != self.INDIVIDUAL:
            raise ValidationError("A single sample must use Individual COA.")
        if total == 2 and self.preference_type == self.CUSTOM_GROUP:
            raise ValidationError("Custom Group COA is not available for 2 samples.")

    def all_samples_assigned(self):
        assigned_ids = set(
            COAGroupSample.objects.filter(group__preference=self).values_list(
                "sample_id", flat=True
            )
        )
        all_ids = set(self.submission.samples.values_list("id", flat=True))
        return assigned_ids == all_ids


class COAGroup(models.Model):
    preference = models.ForeignKey(
        COAReportingPreference,
        on_delete=models.CASCADE,
        related_name="groups",
    )
    group_number = models.PositiveIntegerField()
    samples = models.ManyToManyField(
        "samples.Sample",
        through="COAGroupSample",
        related_name="coa_groups",
    )

    class Meta:
        ordering = ["group_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["preference", "group_number"],
                name="unique_group_number_per_preference",
            )
        ]

    def __str__(self):
        return f"{self.preference.submission.reference} — Group {self.group_number}"

    def clean(self):
        if self.pk and not self.samples.exists():
            raise ValidationError(
                "A group cannot be saved without at least one sample."
            )


class COAGroupSample(models.Model):
    group = models.ForeignKey(COAGroup, on_delete=models.CASCADE)
    sample = models.ForeignKey("samples.Sample", on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sample"], name="sample_assigned_to_one_group_only"
            )
        ]


class COAReportingPreferenceChange(models.Model):
    preference = models.ForeignKey(
        COAReportingPreference,
        on_delete=models.CASCADE,
        related_name="changes",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coa_preference_changes",
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=30)
    previous_preference_type = models.CharField(max_length=15, blank=True)
    new_preference_type = models.CharField(max_length=15, blank=True)
    group_number = models.PositiveIntegerField(null=True, blank=True)


class COA(models.Model):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    QC_REVIEW = "QC_REVIEW"
    APPROVED = "APPROVED"
    RELEASED = "RELEASED"
    REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (PENDING, "Pending"),
        (QC_REVIEW, "QC Review"),
        (APPROVED, "Approved"),
        (RELEASED, "Released"),
        (REJECTED, "Rejected"),
    ]

    CLIENT_VISIBLE_STATUSES = {RELEASED}

    submission = models.ForeignKey(
        "submissions.Submission",
        on_delete=models.CASCADE,
        related_name="coas",
    )
    group = models.ForeignKey(
        COAGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coa",
    )

    coa_number = models.CharField(max_length=30, unique=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=DRAFT)

    pdf_file = models.FileField(upload_to="coas/pdf/", null=True, blank=True)
    png_file = models.FileField(upload_to="coas/png/", null=True, blank=True)

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coas_approved",
    )
    released_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.coa_number

    @property
    def is_client_visible(self):
        return self.status in self.CLIENT_VISIBLE_STATUSES
