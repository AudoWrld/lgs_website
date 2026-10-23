import re
from django import forms
from accounts.models import User

PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9\s\-]{6,18}$")


class AdminProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Last name")
    whatsapp_number = forms.CharField(max_length=30, label="Phone")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "whatsapp_number"]

    def clean_first_name(self):
        return self.cleaned_data["first_name"].strip()

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip()

    def clean_whatsapp_number(self):
        value = self.cleaned_data["whatsapp_number"].strip()
        if not PHONE_PATTERN.match(value):
            raise forms.ValidationError("Enter a valid phone number.")
        return value
