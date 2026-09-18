from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _
from .models import Client
from django import forms
from django.contrib.auth import get_user_model
from .models import Client
from .utils import normalize_tz_phone
import re

User = get_user_model()


class EmailAuthenticationForm(AuthenticationForm):
    username = AuthenticationForm.base_fields["username"]
    username.label = _("Email address")
    username.widget.attrs.update({"autofocus": True, "autocomplete": "email"})

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class ClientSearchForm(forms.Form):
    query = forms.CharField(
        label="Search Client",
        max_length=200,
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Name, Contact Person, Email, or WhatsApp Number",
                "autofocus": True,
            }
        ),
    )

    def clean_query(self):
        return self.cleaned_data["query"].strip()


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            "client_type",
            "client_name",
            "contact_person",
            "email",
            "whatsapp_number",
        ]
        widgets = {
            "client_type": forms.Select(),
            "client_name": forms.TextInput(
                attrs={"placeholder": "e.g. ABC Mining Ltd"}
            ),
            "contact_person": forms.TextInput(
                attrs={"placeholder": "e.g. Jane Mwakalinga"}
            ),
            "email": forms.EmailInput(attrs={"placeholder": "name@company.com"}),
            "whatsapp_number": forms.TextInput(
                attrs={"placeholder": "e.g. 0712 345 678 or +255 712 345 678"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._existing_client_pk = self.instance.pk
        self._existing_user_pk = (
            self.instance.portal_user_id if self.instance.pk else None
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        user_qs = User.objects.filter(email__iexact=email)
        if self._existing_user_pk:
            user_qs = user_qs.exclude(pk=self._existing_user_pk)

        if user_qs.exists():
            conflicting = user_qs.first()
            if conflicting.role == User.CUSTOMER:
                raise forms.ValidationError(
                    "This email is already registered to another client account."
                )
            raise forms.ValidationError(
                "This email is already in use by a staff account and cannot be used for a client."
            )

        return email

    def clean_whatsapp_number(self):
        raw = self.cleaned_data["whatsapp_number"].strip()

        if not re.match(r"^(\+?255|0)\d{9}$", re.sub(r"[\s\-]", "", raw)):
            raise forms.ValidationError(
                "Enter a valid Tanzanian phone number, e.g. 0712345678 or +255712345678."
            )

        number = normalize_tz_phone(raw)

        client_qs = Client.objects.filter(whatsapp_number=number)
        if self._existing_client_pk:
            client_qs = client_qs.exclude(pk=self._existing_client_pk)

        if client_qs.exists():
            raise forms.ValidationError(
                "This WhatsApp number is already registered to another client."
            )

        user_qs = User.objects.filter(whatsapp_number=number).exclude(
            whatsapp_number=""
        )
        if self._existing_user_pk:
            user_qs = user_qs.exclude(pk=self._existing_user_pk)

        if user_qs.exists():
            raise forms.ValidationError(
                "This WhatsApp number is already associated with another account."
            )

        return number

    def clean_client_name(self):
        return self.cleaned_data["client_name"].strip()

    def clean_contact_person(self):
        return self.cleaned_data["contact_person"].strip()
