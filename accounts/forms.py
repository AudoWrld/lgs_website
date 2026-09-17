from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _


class EmailAuthenticationForm(AuthenticationForm):
    username = AuthenticationForm.base_fields["username"]
    username.label = _("Email address")
    username.widget.attrs.update({"autofocus": True, "autocomplete": "email"})

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()
