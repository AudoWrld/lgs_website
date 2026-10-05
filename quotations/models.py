from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

ZERO = Decimal("0.00")
NUMBER_PREFIX = "LGS-QTN"
DEFAULT_VALIDITY_DAYS = 14


def default_valid_until():
    return timezone.localdate() + timedelta(days=DEFAULT_VALIDITY_DAYS)


class Quotation(models.Model):
    DRAFT = "DRAFT"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"

    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (SENT, "Sent"),
        (ACCEPTED, "Accepted"),
        (EXPIRED, "Expired"),
    ]

    quotation_number = models.CharField(
        max_length=30, unique=True, editable=False, db_index=True
    )
    quotation_date = models.DateField(default=timezone.localdate)
    valid_until = models.DateField(default=default_valid_until)
    client_label = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional internal label. Do not enter client contact details.",
    )
    discount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    terms = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=DRAFT, db_index=True
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="quotations_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="quotations_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-quotation_date", "-id"]
        indexes = [
            models.Index(fields=["status", "valid_until"]),
            models.Index(fields=["quotation_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(discount__gte=0),
                name="quotation_discount_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_until__gte=models.F("quotation_date")),
                name="quotation_valid_until_after_date",
            ),
        ]

    def __str__(self):
        return self.quotation_number

    @classmethod
    def _next_number(cls, on_date):
        prefix = f"{NUMBER_PREFIX}-{on_date:%y%m%d}-"
        last = (
            cls.objects.select_for_update()
            .filter(quotation_number__startswith=prefix)
            .order_by("-quotation_number")
            .values_list("quotation_number", flat=True)
            .first()
        )
        sequence = int(last.rsplit("-", 1)[1]) + 1 if last else 1
        return f"{prefix}{sequence:03d}"

    def clean(self):
        if self.valid_until and self.quotation_date:
            if self.valid_until < self.quotation_date:
                raise ValidationError(
                    {"valid_until": "Valid Until cannot be before the quotation date."}
                )

    def save(self, *args, **kwargs):
        if self.quotation_number:
            return super().save(*args, **kwargs)

        for _ in range(5):
            try:
                with transaction.atomic():
                    self.quotation_number = self._next_number(self.quotation_date)
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.quotation_number = ""
        raise IntegrityError("Could not generate a unique quotation number.")

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Quotations cannot be deleted. Mark them as expired instead."
        )

    @property
    def subtotal(self):
        line = ExpressionWrapper(
            F("quantity") * F("unit_price"),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
        return self.items.aggregate(total=Sum(line))["total"] or ZERO

    @property
    def total_amount(self):
        return max(self.subtotal - self.discount, ZERO)

    @property
    def is_past_validity(self):
        return self.valid_until < timezone.localdate()

    @property
    def effective_status(self):
        if self.status in (self.DRAFT, self.SENT) and self.is_past_validity:
            return self.EXPIRED
        return self.status

    @property
    def effective_status_display(self):
        return dict(self.STATUS_CHOICES)[self.effective_status]

    @property
    def is_editable(self):
        return self.status == self.DRAFT

    def mark_sent(self, user):
        if self.status != self.DRAFT:
            raise ValidationError("Only a draft quotation can be marked as sent.")
        if not self.items.exists():
            raise ValidationError("Add at least one service before sending.")
        self.status = self.SENT
        self.sent_at = timezone.now()
        self.updated_by = user
        self.save(update_fields=["status", "sent_at", "updated_by", "updated_at"])

    def mark_accepted(self, user):
        if self.effective_status != self.SENT:
            raise ValidationError("Only a sent, unexpired quotation can be accepted.")
        self.status = self.ACCEPTED
        self.accepted_at = timezone.now()
        self.updated_by = user
        self.save(update_fields=["status", "accepted_at", "updated_by", "updated_at"])

    def mark_expired(self, user=None):
        if self.status == self.ACCEPTED:
            raise ValidationError("An accepted quotation cannot be expired.")
        self.status = self.EXPIRED
        if user:
            self.updated_by = user
        self.save(update_fields=["status", "updated_by", "updated_at"])


class QuotationItem(models.Model):
    quotation = models.ForeignKey(
        Quotation, on_delete=models.CASCADE, related_name="items"
    )
    service = models.CharField(max_length=200, verbose_name="Requested service")
    description = models.CharField(max_length=255, blank=True)
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name="Quantity / No. of samples",
    )
    unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Unit price (TZS)",
    )
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="quotation_item_quantity_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gt=0),
                name="quotation_item_unit_price_positive",
            ),
        ]

    def __str__(self):
        return f"{self.quotation.quotation_number} - {self.service}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    def clean(self):
        if self.quotation_id and not self.quotation.is_editable:
            raise ValidationError(
                "Items can only be changed while the quotation is a draft."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not self.quotation.is_editable:
            raise ValidationError(
                "Items can only be removed while the quotation is a draft."
            )
        return super().delete(*args, **kwargs)
