from django import forms

from .models import Expense


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "category",
            "other_category",
            "description",
            "amount",
            "payment_method",
        ]
        widgets = {
            "other_category": forms.TextInput(
                attrs={"placeholder": "Specify expense category"}
            ),
            "description": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Describe the expense"}
            ),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        other_category = cleaned.get("other_category", "").strip()

        if category == Expense.OTHER and not other_category:
            self.add_error(
                "other_category",
                "Specify the expense category when 'Other' is selected.",
            )
        elif category != Expense.OTHER:
            cleaned["other_category"] = ""

        return cleaned
