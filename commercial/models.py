from decimal import Decimal

from django.conf import settings
from branches.models import BranchScopedModel
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from payments.models import Payment


class DailyInvoiceSequence(models.Model):
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        related_name="daily_invoice_sequences",
        db_index=True,
    )
    date = models.DateField()
    last_sequence = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "date"], name="unique_daily_invoice_sequence_branch_date")
        ]

    def __str__(self):
        return f"{self.date} - last {self.last_sequence:02d}"


class CommercialInvoice(BranchScopedModel):
    invoice_number = models.CharField(
        max_length=30, unique=True, db_index=True, editable=False
    )
    client = models.ForeignKey(
        "accounts.Client",
        on_delete=models.PROTECT,
        related_name="commercial_invoices",
    )
    invoice_date = models.DateField(default=timezone.localdate)
    total_charges = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commercial_invoices_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Commercial Invoice"
        verbose_name_plural = "Commercial Invoices"

    def __str__(self):
        return self.invoice_number

    @classmethod
    def generate_number(cls, branch, for_date=None):
        for_date = for_date or timezone.localdate()
        with transaction.atomic():
            seq, _ = DailyInvoiceSequence.objects.select_for_update().get_or_create(
                branch=branch, date=for_date
            )
            seq.last_sequence += 1
            seq.save(update_fields=["last_sequence"])
            return f"LGS/{for_date:%y%m%d}/{seq.last_sequence:02d}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self.generate_number(self.branch, self.invoice_date)
        super().save(*args, **kwargs)

    @property
    def reference_numbers(self):
        return [link.submission.reference for link in self.references.all()]

    @property
    def amount_paid(self):
        total = Payment.objects.filter(
            submission__commercial_link__invoice=self
        ).aggregate(total=Sum("total_amount_paid"))["total"]
        return total or Decimal("0.00")

    @property
    def outstanding_balance(self):
        return max(self.total_charges - self.amount_paid, Decimal("0.00"))

    @property
    def payment_status(self):
        paid = self.amount_paid
        if paid <= 0:
            return "UNPAID"
        if self.outstanding_balance > 0:
            return "PARTIALLY PAID"
        return "PAID"


class CommercialInvoiceReference(models.Model):
    invoice = models.ForeignKey(
        CommercialInvoice, on_delete=models.CASCADE, related_name="references"
    )
    submission = models.OneToOneField(
        "submissions.Submission",
        on_delete=models.PROTECT,
        related_name="commercial_link",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.submission.reference}"


class CommercialInvoiceLine(models.Model):
    invoice = models.ForeignKey(
        CommercialInvoice, on_delete=models.CASCADE, related_name="lines"
    )
    position = models.PositiveIntegerField(default=0)
    reference = models.CharField(max_length=20)
    description = models.CharField(max_length=255)
    sample_type = models.CharField(max_length=100, blank=True)
    quantity = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["position", "id"]
