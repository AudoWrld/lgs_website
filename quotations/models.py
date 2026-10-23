from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from branches.models import BranchScopedModel
from django.db import IntegrityError, models, transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

ZERO = Decimal("0.00")
NUMBER_PREFIX = "LGS-QTN"
DEFAULT_VALIDITY_DAYS = 14


def to_title(value):
    """Convert string to Title Case without affecting the casing of the rest of the word."""
    words = (value or "").split()
    return " ".join(w[:1].upper() + w[1:] for w in words)


def capitalize_first(value):
    """Capitalize the first character of the string, leaving the rest as typed."""
    value = " ".join((value or "").split())
    return value[:1].upper() + value[1:] if value else ""


def default_valid_until():
    return timezone.localdate() + timedelta(days=DEFAULT_VALIDITY_DAYS)


class Quotation(BranchScopedModel):
    quotation_number = models.CharField(
        max_length=30, unique=True, editable=False, db_index=True
    )
    quotation_date = models.DateField(default=timezone.localdate)
    valid_until = models.DateField(default=default_valid_until)
    discount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    terms = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    expired_at = models.DateTimeField(null=True, blank=True, editable=False, db_index=True)
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
        raise ValidationError("Quotations cannot be deleted.")

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
    def is_expired(self):
        return self.expired_at is not None


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
        pass

    def save(self, *args, **kwargs):
        self.service = to_title(self.service)
        self.description = capitalize_first(self.description)
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return super().delete(*args, **kwargs)
