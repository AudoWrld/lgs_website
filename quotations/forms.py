from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import Quotation, QuotationItem

ZERO = Decimal("0.00")

STATUS_FILTER_CHOICES = [("", "All statuses")] + list(Quotation.STATUS_CHOICES)


def _date_widget():
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = [
            "quotation_date",
            "valid_until",
            "client_label",
            "discount",
            "terms",
            "notes",
        ]
        labels = {
            "quotation_date": "Date",
            "valid_until": "Valid Until",
            "client_label": "Internal Label (optional)",
            "discount": "Discount (TZS)",
        }
        widgets = {
            "quotation_date": _date_widget(),
            "valid_until": _date_widget(),
            "client_label": forms.TextInput(
                attrs={"placeholder": "No contact details", "autocomplete": "off"}
            ),
            "discount": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "inputmode": "decimal"}
            ),
            "terms": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["discount"].required = False
        self.fields["discount"].initial = ZERO
        self.fields["quotation_date"].input_formats = ["%Y-%m-%d"]
        self.fields["valid_until"].input_formats = ["%Y-%m-%d"]

    def clean_discount(self):
        value = self.cleaned_data.get("discount")
        if value is None:
            return ZERO
        if value < 0:
            raise ValidationError("Discount cannot be negative.")
        return value

    def clean(self):
        data = super().clean()
        start = data.get("quotation_date")
        end = data.get("valid_until")
        if start and end and end < start:
            self.add_error(
                "valid_until", "Valid Until cannot be before the quotation date."
            )
        return data

    def check_discount(self, subtotal):
        discount = self.cleaned_data.get("discount") or ZERO
        if discount > subtotal:
            self.add_error("discount", "Discount cannot be greater than the subtotal.")
            return False
        return True


class QuotationItemForm(forms.ModelForm):
    class Meta:
        model = QuotationItem
        fields = ["service", "description", "quantity", "unit_price"]
        labels = {
            "service": "Requested Service",
            "description": "Description",
            "quantity": "Qty / Samples",
            "unit_price": "Unit Price (TZS)",
        }
        widgets = {
            "service": forms.TextInput(
                attrs={
                    "placeholder": "e.g. Analysis of Gold & Copper",
                    "autocomplete": "off",
                }
            ),
            "description": forms.TextInput(attrs={"autocomplete": "off"}),
            "quantity": forms.NumberInput(attrs={"min": "1", "step": "1"}),
            "unit_price": forms.NumberInput(
                attrs={"min": "0.01", "step": "0.01", "inputmode": "decimal"}
            ),
        }

    def clean_service(self):
        return self.cleaned_data["service"].strip()


class BaseQuotationItemFormSet(forms.BaseInlineFormSet):
    def _live_forms(self):
        for form in self.forms:
            data = getattr(form, "cleaned_data", None)
            if not data or data.get("DELETE"):
                continue
            yield form

    def subtotal(self):
        total = ZERO
        for form in self._live_forms():
            quantity = form.cleaned_data.get("quantity")
            price = form.cleaned_data.get("unit_price")
            if quantity and price:
                total += quantity * price
        return total

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if not any(True for _ in self._live_forms()):
            raise ValidationError("Add at least one requested service.")


QuotationItemFormSet = forms.inlineformset_factory(
    Quotation,
    QuotationItem,
    form=QuotationItemForm,
    formset=BaseQuotationItemFormSet,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class QuotationFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        label="Quotation No.",
        widget=forms.TextInput(
            attrs={"placeholder": "e.g. LGS-QTN-260930-001", "autocomplete": "off"}
        ),
    )
    status = forms.ChoiceField(
        required=False, choices=STATUS_FILTER_CHOICES, label="Status"
    )
    date_from = forms.DateField(
        required=False,
        label="From",
        widget=_date_widget(),
    )
    date_to = forms.DateField(
        required=False,
        label="To",
        widget=_date_widget(),
    )

    def clean(self):
        data = super().clean()
        start = data.get("date_from")
        end = data.get("date_to")
        if start and end and end < start:
            raise ValidationError("The end date cannot be before the start date.")
        return data
