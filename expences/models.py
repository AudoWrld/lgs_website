from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

MAX_EVIDENCE_MB = 5
ALLOWED_EVIDENCE_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "pdf"]
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_ADDER_ROLES = ["RECEPTION", "ACCOUNTANT"]


def validate_evidence_size(file):
    if file.size > MAX_EVIDENCE_MB * 1024 * 1024:
        raise ValidationError(f"File must be {MAX_EVIDENCE_MB} MB or smaller.")


def expense_evidence_path(instance, filename):
    return f"expenses/evidence/{timezone.now():%Y/%m}/{filename}"


class Expense(models.Model):
    LABORATORY_CONSUMABLES = "LABORATORY_CONSUMABLES"
    CHEMICALS = "CHEMICALS"
    GLASSWARE = "GLASSWARE"
    EQUIPMENT_MAINTENANCE = "EQUIPMENT_MAINTENANCE"
    FUEL = "FUEL"
    TRANSPORT = "TRANSPORT"
    ELECTRICITY_UTILITIES = "ELECTRICITY_UTILITIES"
    STAFF_MEALS = "STAFF_MEALS"
    OFFICE_SUPPLIES = "OFFICE_SUPPLIES"
    CLEANING = "CLEANING"
    COMMUNICATION = "COMMUNICATION"
    MARKETING = "MARKETING"
    REPAIRS = "REPAIRS"
    LOGISTICS = "LOGISTICS"
    BONUSES = "BONUSES"
    OVERTIME = "OVERTIME"
    OTHER = "OTHER"

    CATEGORY_CHOICES = [
        (LABORATORY_CONSUMABLES, "Laboratory Consumables"),
        (CHEMICALS, "Chemicals"),
        (GLASSWARE, "Glassware"),
        (EQUIPMENT_MAINTENANCE, "Equipment Maintenance"),
        (FUEL, "Fuel"),
        (TRANSPORT, "Transport"),
        (ELECTRICITY_UTILITIES, "Electricity / Utilities"),
        (STAFF_MEALS, "Staff Meals"),
        (OFFICE_SUPPLIES, "Office Supplies"),
        (CLEANING, "Cleaning"),
        (COMMUNICATION, "Communication"),
        (MARKETING, "Marketing"),
        (REPAIRS, "Repairs"),
        (LOGISTICS, "Logistics"),
        (BONUSES, "Bonuses"),
        (OVERTIME, "Overtime"),
        (OTHER, "Other"),
    ]

    CASH = "CASH"
    MPESA = "MPESA"
    BANK = "BANK"
    LIPA_NUMBER = "LIPA_NUMBER"

    PAYMENT_METHOD_CHOICES = [
        (CASH, "Cash"),
        (MPESA, "M-Pesa"),
        (BANK, "Bank"),
        (LIPA_NUMBER, "Lipa Number"),
    ]

    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    slug = models.SlugField(max_length=160, unique=True, editable=False, blank=True)
    other_category = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=255)
    expense_date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=15, choices=PAYMENT_METHOD_CHOICES)
    supplier_reference = models.CharField(max_length=150, blank=True)
    document_number = models.CharField(max_length=100, blank=True)
    evidence = models.FileField(
        upload_to=expense_evidence_path,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(ALLOWED_EVIDENCE_EXTENSIONS),
            validate_evidence_size,
        ],
    )

    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)

    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses_added",
        limit_choices_to={"role__in": ALLOWED_ADDER_ROLES},
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]

    def __str__(self):
        return f"{self.get_category_display()} — {self.amount}"

    class ReceptionVisibleManager(models.Manager):
        def get_queryset(self):
            return super().get_queryset().filter(is_submitted=False)

    objects = models.Manager()
    reception_visible = ReceptionVisibleManager()

    @property
    def evidence_is_image(self):
        if not self.evidence:
            return False
        return self.evidence.name.lower().rsplit(".", 1)[-1] in IMAGE_EXTENSIONS

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(f"{self.category}-{self.description}") or "expense"
            candidate = base
            suffix = 2
            while (
                type(self).objects.filter(slug=candidate).exclude(pk=self.pk).exists()
            ):
                candidate = f"{base}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)
