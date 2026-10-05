from django import forms
from django.utils import timezone

from .models import (
    ALLOWED_EVIDENCE_EXTENSIONS,
    MAX_EVIDENCE_MB,
    Expense,
)


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "category",
            "other_category",
            "description",
            "expense_date",
            "amount",
            "payment_method",
            "supplier_reference",
            "document_number",
            "evidence",
        ]
        labels = {
            "expense_date": "Expense Date",
            "supplier_reference": "Supplier / Payee Reference",
            "document_number": "Receipt / Document Number",
            "evidence": "Supporting Evidence",
        }
        help_texts = {
            "evidence": (f"Optional. One image or PDF, up to {MAX_EVIDENCE_MB} MB."),
        }
        widgets = {
            "other_category": forms.TextInput(
                attrs={"placeholder": "Specify expense category"}
            ),
            "description": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Describe the expense"}
            ),
            "expense_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "supplier_reference": forms.TextInput(
                attrs={"placeholder": "Supplier or payee name / reference"}
            ),
            "document_number": forms.TextInput(
                attrs={"placeholder": "Receipt or document number"}
            ),
            "evidence": forms.ClearableFileInput(
                attrs={
                    "accept": ",".join(f".{ext}" for ext in ALLOWED_EVIDENCE_EXTENSIONS)
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expense_date"].input_formats = ["%Y-%m-%d"]
        self.fields["expense_date"].initial = timezone.localdate

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount

    def clean_expense_date(self):
        expense_date = self.cleaned_data["expense_date"]
        if expense_date > timezone.localdate():
            raise forms.ValidationError("Expense date cannot be in the future.")
        return expense_date

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        other_category = (cleaned.get("other_category") or "").strip()

        if category == Expense.OTHER and not other_category:
            self.add_error(
                "other_category",
                "Specify the expense category when 'Other' is selected.",
            )
        elif category != Expense.OTHER:
            cleaned["other_category"] = ""
        else:
            cleaned["other_category"] = other_category

        return cleaned
