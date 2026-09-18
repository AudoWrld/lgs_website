from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Service(models.Model):
    FIXED = "FIXED"
    QUOTATION = "QUOTATION"

    PRICING_TYPE_CHOICES = [
        (FIXED, "Fixed"),
        (QUOTATION, "By Quotation"),
    ]

    name = models.CharField(max_length=100, unique=True)
    method_of_analysis = models.CharField(max_length=150)
    pricing_type = models.CharField(
        max_length=10, choices=PRICING_TYPE_CHOICES, default=FIXED
    )
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.pricing_type == self.FIXED and self.unit_price is None:
            raise ValidationError("Fixed-price services must have a unit price.")
        if self.pricing_type == self.QUOTATION:
            self.unit_price = None


class Sample(models.Model):
    ROCK = "ROCK"
    ROCK_PULP = "ROCK_PULP"
    SOIL = "SOIL"
    TAILINGS = "TAILINGS"
    CARBON = "CARBON"
    PROCESS_SOLUTION = "PROCESS_SOLUTION"
    WATER = "WATER"
    RC_CHIPS = "RC_CHIPS"
    DRILL_CORE = "DRILL_CORE"
    CONCENTRATE = "CONCENTRATE"
    SLAG = "SLAG"
    OTHER = "OTHER"

    SAMPLE_TYPE_CHOICES = [
        (ROCK, "Rock"),
        (ROCK_PULP, "Rock Pulp"),
        (SOIL, "Soil"),
        (TAILINGS, "Tailings"),
        (CARBON, "Carbon"),
        (PROCESS_SOLUTION, "Process Solution"),
        (WATER, "Water"),
        (RC_CHIPS, "RC Chips"),
        (DRILL_CORE, "Drill Core"),
        (CONCENTRATE, "Concentrate"),
        (SLAG, "Slag"),
        (OTHER, "Other"),
    ]

    REPLICATE_RULES = {
        ROCK: 2,
        ROCK_PULP: 2,
        SOIL: 3,
        TAILINGS: 3,
        CARBON: 4,
        PROCESS_SOLUTION: 2,
    }

    submission = models.ForeignKey(
        "submissions.Submission",
        on_delete=models.CASCADE,
        related_name="samples",
    )

    client_sample_id = models.CharField(max_length=50)
    sample_type = models.CharField(max_length=20, choices=SAMPLE_TYPE_CHOICES)
    other_sample_type = models.CharField(max_length=100, blank=True)

    services = models.ManyToManyField(
        Service, through="SampleService", related_name="samples"
    )

    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="samples_added",
        limit_choices_to={"role": "RECEPTION"},
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "client_sample_id"],
                name="unique_sample_id_per_submission",
            )
        ]

    def __str__(self):
        return f"{self.submission.reference} — {self.client_sample_id}"

    def clean(self):
        if self.sample_type == self.OTHER and not self.other_sample_type:
            raise ValidationError("Specify the sample type when 'Other' is selected.")

    @property
    def replicate_count(self):
        return self.REPLICATE_RULES.get(self.sample_type, 0)


class SampleService(models.Model):
    sample = models.ForeignKey(
        Sample, on_delete=models.CASCADE, related_name="sample_services"
    )
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, related_name="sample_services"
    )
    quoted_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sample", "service"], name="unique_service_per_sample"
            )
        ]

    def __str__(self):
        return f"{self.sample} — {self.service}"

    @property
    def line_price(self):
        if self.service.pricing_type == Service.QUOTATION:
            return self.quoted_price
        return self.service.unit_price

    def clean(self):
        if self.service.pricing_type == Service.QUOTATION and self.quoted_price is None:
            pass
        if self.service.pricing_type == Service.FIXED and self.quoted_price is not None:
            raise ValidationError("Fixed-price services cannot carry a quoted price.")
