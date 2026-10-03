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
    gold_replicate_1_id = models.PositiveIntegerField(null=True, blank=True)
    gold_replicate_2_id = models.PositiveIntegerField(null=True, blank=True)

    copper_final = _final_field()
    silver_final = _final_field()
    sulphur_final = _final_field()

    carbon_activity_final = _final_field(8, 4)

    show_recovery_12h = models.BooleanField(default=True)
    show_recovery_24h = models.BooleanField(default=True)
    show_recovery_48h = models.BooleanField(default=True)

    metallurgical_original = models.JSONField(null=True, blank=True)

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
    entry_revision = models.PositiveSmallIntegerField(null=True, blank=True)
    field_label = models.CharField(max_length=150)
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
        ordering = ["-edited_at", "-id"]
        verbose_name = "QC Edit Log"
        verbose_name_plural = "QC Edit Logs"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("QC edit logs cannot be modified.")
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.sample.slug} — {self.field_label} ({self.edited_at:%Y-%m-%d %H:%M})"
        )


class QCDecision(models.Model):
    APPROVED = "approved"
    RETURNED = "returned"
    ACTION_CHOICES = (
        (APPROVED, "Approved"),
        (RETURNED, "Returned for reassay"),
    )

    sample = models.ForeignKey(
        Sample, on_delete=models.CASCADE, related_name="qc_decisions"
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    reason = models.TextField(blank=True)
    entry_revision = models.PositiveSmallIntegerField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-decided_at", "-id"]
        verbose_name = "QC Decision"
        verbose_name_plural = "QC Decisions"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("QC decisions cannot be modified.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sample.slug} — {self.get_action_display()} ({self.decided_at:%Y-%m-%d %H:%M})"
