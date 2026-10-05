from django import forms

from .models import (
    ALLOWED_EVIDENCE_EXTENSIONS,
    MAX_EVIDENCE_MB,
    Expense,
)


class ExpenseForm(forms.ModelForm):
    remove_evidence = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Expense
        fields = [
            "category",
            "other_category",
            "description",
            "amount",
            "payment_method",
            "supplier_reference",
            "document_number",
            "evidence",
        ]
        labels = {
            "supplier_reference": "Supplier / Payee Reference",
            "document_number": "Receipt Number",
            "evidence": "Supporting Evidence",
        }
        help_texts = {
            "evidence": f"Optional. One image or PDF, up to {MAX_EVIDENCE_MB} MB.",
        }
        widgets = {
            "other_category": forms.TextInput(
                attrs={"placeholder": "Specify expense category"}
            ),
            "description": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Describe the expense"}
            ),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "supplier_reference": forms.TextInput(
                attrs={"placeholder": "Supplier or payee name / reference"}
            ),
            "document_number": forms.TextInput(
                attrs={"placeholder": "e.g. M-Pesa or bank transaction code"}
            ),
            "evidence": forms.FileInput(
                attrs={
                    "class": "ef-file-input",
                    "accept": ",".join(
                        f".{ext}" for ext in ALLOWED_EVIDENCE_EXTENSIONS
                    ),
                }
            ),
        }

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        other_category = (cleaned.get("other_category") or "").strip()
        method = cleaned.get("payment_method")
        removing = (cleaned.get("remove_evidence") or "").strip() == "1"
        uploading = bool(self.files.get("evidence"))

        if category == Expense.OTHER:
            if not other_category:
                self.add_error(
                    "other_category",
                    "Specify the expense category when 'Other' is selected.",
                )
            else:
                cleaned["other_category"] = other_category
        else:
            cleaned["other_category"] = ""

        if method == Expense.CASH:
            cleaned["document_number"] = ""
            cleaned["evidence"] = False
        elif method:
            number = (cleaned.get("document_number") or "").strip()
            if not number:
                self.add_error(
                    "document_number",
                    "Receipt number is required unless the payment is cash.",
                )
            else:
                cleaned["document_number"] = number
            if removing and not uploading:
                cleaned["evidence"] = False

        return cleaned
