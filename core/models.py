import datetime

from django.db import models, transaction


class ReferenceCounter(models.Model):
    prefix = models.CharField(max_length=10)
    year = models.PositiveIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("prefix", "year")

    def __str__(self):
        return f"{self.prefix}-{self.year} -> {self.last_number}"


def generate_reference_number(prefix):
    year = datetime.date.today().year
    with transaction.atomic():
        counter, _ = ReferenceCounter.objects.select_for_update().get_or_create(
            prefix=prefix, year=year, defaults={"last_number": 0}
        )
        counter.last_number += 1
        counter.save()
        sequence = counter.last_number
    return f"LGS-{prefix}-{year}-{sequence:04d}"


class QuoteRequest(models.Model):

    STATUS_NEW = "NEW"
    STATUS_REVIEWING = "REVIEWING"
    STATUS_QUOTE_SENT = "QUOTE_SENT"
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_COMPLETED = "COMPLETED"

    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_REVIEWING, "Reviewing"),
        (STATUS_QUOTE_SENT, "Quote Sent"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_COMPLETED, "Completed"),
    ]

    TURNAROUND_STANDARD = "standard"
    TURNAROUND_EXPEDITED = "expedited"
    TURNAROUND_FLEXIBLE = "flexible"

    TURNAROUND_CHOICES = [
        (TURNAROUND_STANDARD, "Standard"),
        (TURNAROUND_EXPEDITED, "Expedited / Urgent"),
        (TURNAROUND_FLEXIBLE, "Flexible / No Rush"),
    ]

    UNIT_CHOICES = [
        ("samples", "Number of Samples"),
        ("g", "Grams (g)"),
        ("kg", "Kilograms (kg)"),
        ("tonnes", "Tonnes"),
        ("bags", "Bags"),
        ("other", "Other"),
    ]

    reference_number = models.CharField(
        max_length=25, unique=True, editable=False, db_index=True
    )
    full_name = models.CharField(max_length=150)
    company = models.CharField(max_length=150, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    services = models.JSONField(
        default=list,
        help_text="List of selected service value keys, e.g. ['gold_copper', 'crm_rock_pulp'].",
    )
    methods = models.JSONField(
        default=list,
        help_text="List of selected analysis method value keys, e.g. ['aqua_regia_aas', 'xrf'].",
    )
    sample_type = models.CharField(max_length=150, blank=True)
    sample_quantity = models.CharField(max_length=50, blank=True)
    sample_unit = models.CharField(max_length=20, choices=UNIT_CHOICES, blank=True)
    technical_requirements = models.TextField(blank=True)
    message = models.TextField()
    preferred_turnaround = models.CharField(
        max_length=20,
        choices=TURNAROUND_CHOICES,
        default=TURNAROUND_STANDARD,
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Quote Request"
        verbose_name_plural = "Quote Requests"

    def __str__(self):
        return f"{self.reference_number} - {self.full_name}"

    def save(self, *args, **kwargs):
        if not self.reference_number:
            self.reference_number = generate_reference_number("Q")
        super().save(*args, **kwargs)

    SERVICE_LABELS = {
        "gold_copper": "Gold & Copper Analysis",
        "gold_copper_silver": "Gold, Copper & Silver Analysis",
        "gold_copper_sulphur": "Gold, Copper & Sulphur Analysis",
        "multi_element": "Multi-Element Analysis",
        "conventional_cyanide": "Conventional Cyanide Leaching Test",
        "cyanide_optimization": "Cyanide Leaching Parameter Optimization",
        "metallic_screening": "Metallic Screening & Gold Evaluation",
        "crm_rock_pulp": "Rock Pulp Certified Reference Materials",
        "crm_gold_carbon": "Gold-Loaded Carbon Certified Reference Materials",
        "lab_glassware": "Laboratory Glassware & Consumables",
        "lab_equipment": "Laboratory Equipment & Instruments",
        "lab_tools": "Laboratory Tools & Accessories",
        "spectrophotometers": "Spectrophotometers & Analytical Instruments",
        "technical_consultancy": "Technical Assistance & Consultancy",
    }

    METHOD_LABELS = {
        "aqua_regia_aas": "Aqua Regia + AAS",
        "cyanide_leaching_aas": "Cyanide Leaching + AAS",
        "metallic_screening_aas": "Metallic Screening + AAS",
        "induction_furnace": "Induction Furnace",
        "xrf": "X-Ray Fluorescence (XRF)",
    }

    def get_services_display(self):
        return [self.SERVICE_LABELS.get(s, s) for s in self.services]

    def get_methods_display(self):
        return [self.METHOD_LABELS.get(m, m) for m in self.methods]


class ContactMessage(models.Model):

    SERVICE_OF_INTEREST_CHOICES = [
        ("gold", "Gold (Au) Analysis"),
        ("silver", "Silver (Ag) Analysis"),
        ("copper", "Copper (Cu) Analysis"),
        ("sulphur", "Sulphur Analysis"),
        ("carbon", "Carbon Activity Testing"),
        ("cyanide", "Cyanide Leaching Tests"),
        ("optimization", "Cyanide Leaching Parameter Optimization"),
        ("screening", "Metallic Screening & Gold Evaluation"),
        ("consultancy", "Technical Assistance & Consultancy"),
        ("other", "Other / Not Sure"),
    ]

    reference_number = models.CharField(
        max_length=25, unique=True, editable=False, db_index=True
    )
    full_name = models.CharField(max_length=150)
    company = models.CharField(max_length=150, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Contact Message"
        verbose_name_plural = "Contact Messages"

    def __str__(self):
        return f"{self.reference_number} - {self.full_name}"

    def save(self, *args, **kwargs):
        if not self.reference_number:
            self.reference_number = generate_reference_number("CON")
        super().save(*args, **kwargs)
