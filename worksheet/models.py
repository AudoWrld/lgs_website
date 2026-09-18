from django.conf import settings
from django.db import models


class LabSampleMapping(models.Model):
    sample = models.OneToOneField(
        "samples.Sample",
        on_delete=models.CASCADE,
        related_name="lab_mapping",
    )
    lab_sample_id = models.CharField(max_length=30, unique=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Laboratory Sample ID Mapping"

    def __str__(self):
        return self.lab_sample_id

    @classmethod
    def generate_for_sample(cls, sample, sequence):
        lab_id = f"{sample.submission.reference}-{sequence}"
        return cls.objects.create(sample=sample, lab_sample_id=lab_id)


class Worksheet(models.Model):
    MINERAL_ANALYSIS = "MINERAL_ANALYSIS"
    CARBON_ACTIVITY = "CARBON_ACTIVITY"
    CONVENTIONAL_CYANIDE_LEACHING = "CONVENTIONAL_CYANIDE_LEACHING"
    PARAMETER_OPTIMIZATION = "PARAMETER_OPTIMIZATION"

    WORKSHEET_TYPE_CHOICES = [
        (MINERAL_ANALYSIS, "Mineral Analysis"),
        (CARBON_ACTIVITY, "Carbon Activity Test"),
        (CONVENTIONAL_CYANIDE_LEACHING, "Conventional Cyanide Leaching"),
        (PARAMETER_OPTIMIZATION, "Cyanide Leaching Parameter Optimization"),
    ]

    submission = models.ForeignKey(
        "submissions.Submission",
        on_delete=models.CASCADE,
        related_name="worksheets",
    )
    worksheet_type = models.CharField(max_length=30, choices=WORKSHEET_TYPE_CHOICES)

    elements = models.CharField(max_length=100, blank=True)
    method_of_analysis = models.CharField(max_length=150, blank=True)

    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="worksheets_generated",
    )
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"{self.submission.reference} — {self.get_worksheet_type_display()}"


class WorksheetRow(models.Model):
    SAMPLE_ROW = "SAMPLE"
    REPLICATE_ROW = "REPLICATE"
    CRM_ROW = "CRM"
    BLANK_ROW = "BLANK"

    ROW_TYPE_CHOICES = [
        (SAMPLE_ROW, "Sample"),
        (REPLICATE_ROW, "Replicate"),
        (CRM_ROW, "CRM"),
        (BLANK_ROW, "Blank"),
    ]

    worksheet = models.ForeignKey(
        Worksheet, on_delete=models.CASCADE, related_name="rows"
    )
    row_number = models.PositiveIntegerField()
    row_type = models.CharField(max_length=10, choices=ROW_TYPE_CHOICES)

    lab_sample_mapping = models.ForeignKey(
        LabSampleMapping,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="worksheet_rows",
    )
    replicate_number = models.PositiveIntegerField(null=True, blank=True)

    beaker_id = models.CharField(max_length=30, blank=True)
    container_label = models.CharField(max_length=30, blank=True)
    parameter = models.CharField(max_length=50, blank=True)
    weight = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    values = models.JSONField(default=dict, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["worksheet", "row_number"], name="unique_row_per_worksheet"
            )
        ]

    def __str__(self):
        return f"{self.worksheet} — row {self.row_number}"
