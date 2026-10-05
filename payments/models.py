from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from samples.models import SampleService, Service


class Payment(models.Model):
    CASH = "CASH"
    MPESA = "MPESA"
    BANK = "BANK"
    LIPA_NUMBER = "LIPA_NUMBER"

    METHOD_CHOICES = [
        (CASH, "Cash"),
        (MPESA, "M-Pesa"),
        (BANK, "Bank"),
        (LIPA_NUMBER, "Lipa Number"),
    ]

    METHODS_REQUIRING_REFERENCE = {MPESA, BANK, LIPA_NUMBER}

    UNPAID = "UNPAID"
    CREDIT = "CREDIT"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"

    STATUS_CHOICES = [
        (UNPAID, "Unpaid"),
        (CREDIT, "Credit"),
        (PARTIALLY_PAID, "Partially Paid"),
        (PAID, "Paid"),
    ]

    submission = models.OneToOneField(
        "submissions.Submission",
        on_delete=models.CASCADE,
        related_name="payment",
    )

    gross_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    discount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    total_amount_paid = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    payment_method = models.CharField(max_length=15, choices=METHOD_CHOICES, blank=True)
    transaction_reference = models.CharField(max_length=100, blank=True)
    payment_status = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default=UNPAID
    )
    remarks = models.TextField(blank=True)

    credit_start_date = models.DateField(null=True, blank=True)
    credit_due_date = models.DateField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"

    def __str__(self):
        return f"{self.submission.reference} — {self.payment_status}"

    @property
    def net_amount_payable(self):
        return self.gross_amount - self.discount

    @property
    def outstanding_balance(self):
        return self.net_amount_payable - self.total_amount_paid

    @property
    def unpriced_quotation_count(self):
        return SampleService.objects.filter(
            sample__submission=self.submission,
            service__pricing_type=Service.QUOTATION,
            quoted_price__isnull=True,
        ).count()

    @property
    def is_credit(self):
        return self.credit_start_date is not None and self.outstanding_balance > 0

    @property
    def days_overdue(self):
        if not self.is_credit or self.credit_due_date is None:
            return 0
        grace = getattr(settings, "CREDIT_GRACE_DAYS", 0)
        late = (timezone.localdate() - self.credit_due_date).days - grace
        return max(late, 0)

    @property
    def is_overdue(self):
        return self.days_overdue > 0

    @property
    def credit_status(self):
        if self.credit_start_date is None:
            return ""
        if self.outstanding_balance <= 0:
            return "Settled"
        if self.is_overdue:
            return "Overdue"
        if self.total_amount_paid > 0:
            return "Partially Paid"
        return "Active Credit"

    def apply_credit_terms(self):
        if self.payment_status != self.CREDIT or self.credit_start_date is not None:
            return False
        start = timezone.localdate()
        days = getattr(settings, "CREDIT_DEFAULT_DAYS", 7)
        self.credit_start_date = start
        self.credit_due_date = start + timedelta(days=days)
        return True

    def save(self, *args, **kwargs):
        changed = self.apply_credit_terms()
        update_fields = kwargs.get("update_fields")
        if changed and update_fields is not None:
            kwargs["update_fields"] = {
                *update_fields,
                "credit_start_date",
                "credit_due_date",
            }
        super().save(*args, **kwargs)

    def recalculate_gross_amount(self):
        total = SampleService.objects.filter(
            sample__submission=self.submission
        ).aggregate(total=Sum("charged_price"))["total"]
        self.gross_amount = total or Decimal("0.00")

    def refresh_from_charges(self):
        self.recalculate_gross_amount()
        expected = self.expected_status()
        if expected is not None:
            self.payment_status = expected
        self.save()

    @classmethod
    def ensure_for(cls, submission):
        payment, created = cls.objects.get_or_create(submission=submission)
        if created:
            payment.refresh_from_charges()
        return payment

    def expected_status(self):
        if self.total_amount_paid <= 0:
            return self.UNPAID
        if self.total_amount_paid < self.net_amount_payable:
            return self.PARTIALLY_PAID
        return self.PAID

    def clean(self):
        super().clean()

        gross = self.gross_amount or Decimal("0")
        discount = self.discount or Decimal("0")
        paid = self.total_amount_paid or Decimal("0")
        net = gross - discount

        if (
            self.payment_method in self.METHODS_REQUIRING_REFERENCE
            and not self.transaction_reference
        ):
            raise ValidationError(
                f"Transaction Reference is required for {self.get_payment_method_display()}."
            )

        if discount < 0:
            raise ValidationError("Discount cannot be negative.")
        if discount > gross:
            raise ValidationError("Discount cannot be more than the Gross Amount.")
        if paid < 0:
            raise ValidationError("Amount paid cannot be negative.")
        if paid > net:
            raise ValidationError(
                f"Overpayment: total paid (TZS {paid:,.2f}) is more than the "
                f"Net Amount Payable (TZS {net:,.2f})."
            )

        if paid == 0:
            valid = {self.UNPAID, self.CREDIT}
        elif paid < net:
            valid = {self.PARTIALLY_PAID}
        else:
            valid = {self.PAID}

        if self.payment_status not in valid:
            raise ValidationError("PAYMENT STATUS DOES NOT MATCH THE PAYMENT AMOUNT")

        if self.payment_status == self.PAID and self.unpriced_quotation_count:
            raise ValidationError(
                "A quotation amount has not been entered for every quoted service. "
                "The payment cannot be marked Paid yet."
            )

        if (
            self.credit_start_date
            and self.credit_due_date
            and self.credit_due_date < self.credit_start_date
        ):
            raise ValidationError(
                "The credit due date cannot be before the credit start date."
            )


class PaymentTransaction(models.Model):
    payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, related_name="transactions"
    )

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(max_length=15, choices=Payment.METHOD_CHOICES)
    transaction_reference = models.CharField(max_length=100, blank=True)
    remarks = models.TextField(blank=True)

    resulting_status = models.CharField(max_length=15, choices=Payment.STATUS_CHOICES)
    resulting_total_paid = models.DecimalField(max_digits=14, decimal_places=2)
    resulting_outstanding = models.DecimalField(max_digits=14, decimal_places=2)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_transactions_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment Transaction"
        verbose_name_plural = "Payment Transactions — Finance/Management Only"

    def __str__(self):
        return f"{self.payment.submission.reference} — {self.amount} ({self.created_at:%Y-%m-%d})"


class PaymentAccount(models.Model):
    BANK = "BANK"
    MOBILE = "MOBILE"

    ACCOUNT_TYPE_CHOICES = [
        (BANK, "Bank"),
        (MOBILE, "Mobile / Lipa Number"),
    ]

    account_type = models.CharField(max_length=10, choices=ACCOUNT_TYPE_CHOICES)
    bank_name = models.CharField(max_length=100, blank=True)
    account_name = models.CharField(max_length=150)
    account_number = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "account_type"]
        verbose_name = "LGS Payment Account"
        verbose_name_plural = "LGS Payment Accounts"

    def __str__(self):
        if self.account_type == self.BANK:
            return f"{self.bank_name} — {self.account_number}"
        return f"Lipa Number — {self.account_number}"

    def clean(self):
        if self.account_type == self.BANK and not self.bank_name:
            raise ValidationError(
                {"bank_name": "Bank Name is required for a Bank account."}
            )
