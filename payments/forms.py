from decimal import Decimal

from django import forms

from .models import Payment


class PaymentSearchForm(forms.Form):
    reference = forms.CharField(
        label="Submission Reference",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. LGS/260914/01",
                "autofocus": True,
            }
        ),
    )

    def clean_reference(self):
        return self.cleaned_data["reference"].strip().upper()


class PaymentUpdateForm(forms.Form):
    additional_amount_paid = forms.DecimalField(
        label="Additional Amount Paid",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        initial=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"placeholder": "0.00", "step": "0.01"}),
    )

    discount = forms.DecimalField(
        label="Discount",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        widget=forms.NumberInput(attrs={"placeholder": "0.00", "step": "0.01"}),
    )

    payment_method = forms.ChoiceField(
        label="Payment Method",
        choices=Payment.METHOD_CHOICES,
    )

    transaction_reference = forms.CharField(
        label="Transaction Reference",
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "Required for M-Pesa, Bank, Lipa Number"}
        ),
    )

    payment_status = forms.ChoiceField(
        label="Payment Status",
        choices=Payment.STATUS_CHOICES,
    )

    remarks = forms.CharField(
        label="Remarks",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional"}),
    )

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("payment_method")
        reference = cleaned.get("transaction_reference")

        if method in Payment.METHODS_REQUIRING_REFERENCE and not reference:
            self.add_error(
                "transaction_reference",
                "Transaction Reference is required for this payment method.",
            )

        return cleaned
