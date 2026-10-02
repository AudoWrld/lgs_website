from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from samples.models import Sample

ZERO = Decimal("0")


def _final_field(max_digits=12, decimal_places=4):
    return models.DecimalField(
        max_digits=max_digits,
        decimal_places=decimal_places,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO)],
    )


class QCReview(models.Model):
    sample = models.OneToOneField(
        Sample, on_delete=models.CASCADE, related_name="qc_review"
    )

    gold_test_1 = _final_field()
    gold_test_2 = _final_field()
    copper_final = _final_field()
    silver_final = _final_field()
    sulphur_final = _final_field()

    carbon_activity_final = _final_field(8, 4)

    show_recovery_12h = models.BooleanField(default=True)
    show_recovery_24h = models.BooleanField(default=True)
    show_recovery_48h = models.BooleanField(default=True)

    defaults_revision = models.PositiveSmallIntegerField(null=True, blank=True)

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "QC Review"
        verbose_name_plural = "QC Reviews"

    def __str__(self):
        return f"QC Review — {self.sample.slug}"


class QCEditLog(models.Model):
    sample = models.ForeignKey(
        Sample, on_delete=models.CASCADE, related_name="qc_edit_logs"
    )
    field_label = models.CharField(max_length=100)
    previous_value = models.CharField(max_length=100, blank=True)
    new_value = models.CharField(max_length=100, blank=True)
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    edited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-edited_at"]
        verbose_name = "QC Edit Log"
        verbose_name_plural = "QC Edit Logs"

    def __str__(self):
        return (
            f"{self.sample.slug} — {self.field_label} ({self.edited_at:%Y-%m-%d %H:%M})"
        )
