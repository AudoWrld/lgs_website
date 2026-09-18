from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class DailySubmissionSequence(models.Model):
    date = models.DateField(unique=True)
    last_sequence = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Daily Submission Sequence"
        verbose_name_plural = "Daily Submission Sequences"

    def __str__(self):
        return f"{self.date} — last {self.last_sequence:02d}"


class Submission(models.Model):
    reference = models.CharField(
        max_length=20, unique=True, db_index=True, editable=False
    )

    client = models.ForeignKey(
        "accounts.Client",
        on_delete=models.PROTECT,
        related_name="submissions",
    )

    receiving_date = models.DateField(default=timezone.now)
    receiving_time = models.TimeField(default=timezone.now)

    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions_registered",
        limit_choices_to={"role": "RECEPTION"},
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference

    @property
    def total_samples(self):
        return self.samples.count()

    @classmethod
    def generate_reference(cls, for_date=None):
        for_date = for_date or timezone.localdate()
        with transaction.atomic():
            seq, _ = DailySubmissionSequence.objects.select_for_update().get_or_create(
                date=for_date
            )
            seq.last_sequence += 1
            seq.save(update_fields=["last_sequence"])
            return f"LGS/{for_date:%y%m%d}/{seq.last_sequence:02d}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self.generate_reference(self.receiving_date)
        super().save(*args, **kwargs)
