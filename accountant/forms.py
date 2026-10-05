from datetime import date, timedelta
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from payments.models import Payment
from submissions.models import Submission

PERIOD_CHOICES = [
    ("daily", "Daily"),
    ("monthly", "Monthly"),
    ("yearly", "Yearly"),
    ("custom", "Custom Range"),
]


class PaymentForm(forms.Form):
    reference = forms.CharField(
        max_length=50,
        label="Reference Number",
        widget=forms.TextInput(
            attrs={"placeholder": "e.g. LGS/260925/01", "autocomplete": "off"}
        ),
    )
    amount = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=14,
        decimal_places=2,
        label="Amount (TZS)",
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
    )
    payment_method = forms.ChoiceField(
        choices=[("", "Select method")] + list(Payment.METHOD_CHOICES),
        label="Payment Method",
    )
    transaction_reference = forms.CharField(
        max_length=100,
        required=False,
        label="Transaction Reference",
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )
    remarks = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Remarks"
    )

    submission = None

    @property
    def reference_required_methods(self):
        return sorted(Payment.METHODS_REQUIRING_REFERENCE)

    def clean_reference(self):
        reference = self.cleaned_data["reference"].strip()
        submission = Submission.objects.filter(
            is_submitted=True, reference__iexact=reference
        ).first()
        if submission is None:
            raise ValidationError("No registered Reference Number matches this entry.")
        self.submission = submission
        return submission.reference

    def clean(self):
        data = super().clean()
        method = data.get("payment_method")
        reference = (data.get("transaction_reference") or "").strip()
        requires_reference = method in Payment.METHODS_REQUIRING_REFERENCE

        if requires_reference and not reference:
            self.add_error(
                "transaction_reference",
                "Transaction Reference is required for this payment method.",
            )
        if method and not requires_reference:
            reference = ""

        data["transaction_reference"] = reference
        return data


class ReportFilterForm(forms.Form):
    period = forms.ChoiceField(choices=PERIOD_CHOICES, required=False)
    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    month = forms.DateField(
        required=False,
        input_formats=["%Y-%m"],
        widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
    )
    year = forms.IntegerField(
        required=False,
        min_value=2000,
        max_value=2100,
        widget=forms.NumberInput(attrs={"placeholder": "e.g. 2026"}),
    )
    date_from = forms.DateField(
        required=False,
        label="From",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    date_to = forms.DateField(
        required=False,
        label="To",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )

    def clean(self):
        data = super().clean()
        today = timezone.localdate()
        period = data.get("period") or "daily"

        if period == "daily":
            start = end = data.get("date") or today
            label = start.isoformat()
        elif period == "monthly":
            month = data.get("month") or today
            start = month.replace(day=1)
            end = (start.replace(day=28) + timedelta(days=4)).replace(
                day=1
            ) - timedelta(days=1)
            label = start.strftime("%B %Y")
        elif period == "yearly":
            year = data.get("year") or today.year
            start = date(year, 1, 1)
            end = date(year, 12, 31)
            label = str(year)
        else:
            start = data.get("date_from") or today
            end = data.get("date_to") or start
            if end < start:
                raise ValidationError("The end date cannot be before the start date.")
            label = f"{start.isoformat()} to {end.isoformat()}"

        data["period"] = period
        data["start"] = start
        data["end"] = end
        data["label"] = label
        return data


class ReleaseForm(forms.Form):
    reason = forms.CharField(
        label="Reason for release",
        min_length=5,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
