from django import forms

from .models import Sample, Service, SampleService


class ServiceCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        if value:
            service = Service.objects.filter(
                pk=value.value if hasattr(value, "value") else value
            ).first()
            if service:
                option["attrs"]["data-method"] = service.method_of_analysis
        return option


class SampleForm(forms.ModelForm):
    services = forms.ModelMultipleChoiceField(
        queryset=Service.objects.filter(is_active=True),
        widget=ServiceCheckboxSelectMultiple,
        required=True,
    )

    class Meta:
        model = Sample
        fields = ["client_sample_id", "sample_type", "other_sample_type", "services"]
        widgets = {
            "client_sample_id": forms.TextInput(attrs={"placeholder": "e.g. ABC-001"}),
            "other_sample_type": forms.TextInput(
                attrs={"placeholder": "Specify sample type"}
            ),
        }

    def __init__(self, *args, submission=None, **kwargs):
        self.submission = submission
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["services"].initial = [
                ss.service_id for ss in self.instance.sample_services.all()
            ]

    def clean_client_sample_id(self):
        sample_id = self.cleaned_data["client_sample_id"].strip()
        submission = self.submission or getattr(self.instance, "submission", None)
        if submission:
            qs = submission.samples.filter(client_sample_id=sample_id)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    "This Sample ID already exists under this Submission Reference."
                )
        return sample_id

    def clean(self):
        cleaned = super().clean()

        if self.submission is None and not self.instance.pk:
            raise forms.ValidationError(
                "No active Submission Reference — cannot register a sample."
            )

        sample_type = cleaned.get("sample_type")
        other = cleaned.get("other_sample_type")
        if sample_type == Sample.OTHER and not other:
            self.add_error(
                "other_sample_type", "Specify the sample type when 'Other' is selected."
            )
        elif sample_type != Sample.OTHER:
            cleaned["other_sample_type"] = ""

        return cleaned

    def save(self, commit=True):
        sample = super().save(commit=False)
        if self.submission is not None:
            sample.submission = self.submission

        if commit:
            sample.save()

            selected_services = set(self.cleaned_data["services"])
            existing = {
                ss.service: ss
                for ss in sample.sample_services.select_related("service")
            }

            for service, sample_service in existing.items():
                if service not in selected_services:
                    sample_service.delete()

            for service in selected_services:
                if service not in existing:
                    SampleService.objects.create(sample=sample, service=service)

        return sample
