from django.conf import settings
from django.db import models


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
    other_category = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=15, choices=PAYMENT_METHOD_CHOICES)

    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)

    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses_added",
        limit_choices_to={"role": "RECEPTION"},
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_category_display()} — {self.amount}"

    class ReceptionVisibleManager(models.Manager):
        def get_queryset(self):
            return super().get_queryset().filter(is_submitted=False)

    objects = models.Manager()
    reception_visible = ReceptionVisibleManager()
