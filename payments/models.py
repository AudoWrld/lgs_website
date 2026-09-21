from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


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

    def recalculate_gross_amount(self):
        total = Decimal("0.00")
        for sample in self.submission.samples.all():
            for ss in sample.sample_services.all():
                if ss.line_price:
                    total += ss.line_price
        self.gross_amount = total

    def expected_status(self):
        if self.total_amount_paid <= 0:
            return None
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
