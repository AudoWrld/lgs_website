from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


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

    slug = models.SlugField(max_length=120, unique=True, db_index=True, editable=False)
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

    @classmethod
    def generate_slug(cls, submission_slug, submission_pk):
        base = slugify(submission_slug) or "submission"
        candidate_count = cls.objects.filter(submission_id=submission_pk).count() + 1
        candidate = f"{base}-{candidate_count:02d}"
        suffix = 2
        while cls.objects.filter(slug=candidate).exists():
            candidate = f"{base}-{candidate_count:02d}-{suffix}"
            suffix += 1
        return candidate

    def save(self, *args, **kwargs):
        if not self.slug:
            submission_slug = self.submission.slug if self.submission_id else "submission"
            self.slug = self.generate_slug(submission_slug, self.submission_id)
        super().save(*args, **kwargs)

    def clean(self):
        if self.sample_type == self.OTHER and not self.other_sample_type:
            raise ValidationError("Specify the sample type when 'Other' is selected.")

    @property
    def replicate_count(self):
        return self.REPLICATE_RULES.get(self.sample_type, 0)

    def has_required_service(self):
        return self.sample_services.exists()

    def validate_registration_complete(self):
        errors = []
        if not self.client_sample_id:
            errors.append("Sample ID is required.")
        if not self.sample_type:
            errors.append("Sample Type is required.")
        if self.sample_type == self.OTHER and not self.other_sample_type:
            errors.append("Specify the sample type when 'Other' is selected.")
        if not self.has_required_service():
            errors.append("At least one requested Service is required.")
        for sample_service in self.sample_services.select_related("service"):
            if not sample_service.service.method_of_analysis:
                errors.append(
                    f"No Method of Analysis assigned for service "
                    f"'{sample_service.service.name}'."
                )
        if errors:
            raise ValidationError(errors)


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
        if self.service.pricing_type == Service.FIXED and self.quoted_price is not None:
            raise ValidationError("Fixed-price services cannot carry a quoted price.")
