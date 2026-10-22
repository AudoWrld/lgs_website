import re

from django import forms

from .models import Branch

TZ_NATIONAL_PATTERN = re.compile(r"^(?:(?:6[1-9]|7[1-8])\d{7}|2\d{8})$")


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ["name", "location", "phone", "email"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "br-input",
                    "placeholder": "e.g. Dar es Salaam Main",
                    "required": True,
                    "maxlength": 150,
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "br-input",
                    "placeholder": "e.g. Mikocheni, Dar es Salaam",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "br-input",
                    "placeholder": "+255 7XX XXX XXX",
                    "inputmode": "tel",
                    "autocomplete": "tel",
                    "maxlength": 20,
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "br-input",
                    "placeholder": "branch@example.com",
                }
            ),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        existing = Branch.objects.filter(name__iexact=name)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise forms.ValidationError("A branch with this name already exists.")

        return name

    def clean_phone(self):
        raw = (self.cleaned_data.get("phone") or "").strip()

        if not raw:
            return ""

        message = (
            "Enter a valid Tanzanian number, e.g. +255 712 345 678 or 0712 345 678."
        )

        if re.search(r"[^\d+\s\-().]", raw):
            raise forms.ValidationError(message)

        digits = re.sub(r"[\s\-().]", "", raw)

        if digits.startswith("+255"):
            national = digits[4:]
        elif digits.startswith("00255"):
            national = digits[5:]
        elif digits.startswith("255"):
            national = digits[3:]
        elif digits.startswith("0"):
            national = digits[1:]
        else:
            raise forms.ValidationError(message)

        if not national.isdigit() or not TZ_NATIONAL_PATTERN.match(national):
            raise forms.ValidationError(message)

        return "+255 {} {} {}".format(national[:3], national[3:6], national[6:])

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        return email
