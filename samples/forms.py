import json

from django import forms

from .models import Sample, SampleService, SampleServiceParameter, Service


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
                option["attrs"]["data-metallurgical-type"] = (
                    service.metallurgical_type or Service.NONE
                )
        return option


_PARAMETER_LABELS = dict(SampleServiceParameter.PARAMETER_CHOICES)

LEACHING_PARAMETER_CHOICES = [
    (code, _PARAMETER_LABELS[code])
    for code in SampleServiceParameter.CONVENTIONAL_LEACHING_OPTIONS
]
OPTIMIZATION_PARAMETER_CHOICES = [
    (code, _PARAMETER_LABELS[code])
    for code in SampleServiceParameter.OPTIMIZATION_OPTIONS
]


class SampleForm(forms.ModelForm):
    services = forms.ModelMultipleChoiceField(
        queryset=Service.objects.filter(is_active=True),
        widget=ServiceCheckboxSelectMultiple,
        required=True,
    )

    leaching_parameters = forms.MultipleChoiceField(
        choices=LEACHING_PARAMETER_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    leaching_custom_parameters = forms.CharField(
        widget=forms.HiddenInput, required=False
    )

    optimization_parameters = forms.MultipleChoiceField(
        choices=OPTIMIZATION_PARAMETER_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    optimization_custom_parameters = forms.CharField(
        widget=forms.HiddenInput, required=False
    )

    class Meta:
        model = Sample
        fields = ["client_sample_id", "sample_type", "other_sample_type", "services"]
        widgets = {
            "client_sample_id": forms.TextInput(
                attrs={"placeholder": "e.g. ABC-001", "autocomplete": "off"}
            ),
            "other_sample_type": forms.TextInput(
                attrs={"placeholder": "Specify sample type", "autocomplete": "off"}
            ),
        }

    def __init__(self, *args, submission=None, **kwargs):
        self.submission = submission
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            selected_service_ids = [
                ss.service_id for ss in self.instance.sample_services.all()
            ]
            self.fields["services"].initial = selected_service_ids

            for sample_service in self.instance.sample_services.select_related(
                "service"
            ):
                fixed, custom = self._split_existing_parameters(sample_service)
                if (
                    sample_service.service.metallurgical_type
                    == Service.CYANIDE_CONVENTIONAL
                ):
                    self.fields["leaching_parameters"].initial = fixed
                    self.initial["leaching_custom_parameters"] = json.dumps(custom)
                elif (
                    sample_service.service.metallurgical_type
                    == Service.CYANIDE_OPTIMIZATION
                ):
                    self.fields["optimization_parameters"].initial = fixed
                    self.initial["optimization_custom_parameters"] = json.dumps(custom)

    @staticmethod
    def _split_existing_parameters(sample_service):
        fixed, custom = [], []
        for param in sample_service.parameters.all():
            if param.parameter == SampleServiceParameter.OTHER:
                custom.append(param.custom_label)
            else:
                fixed.append(param.parameter)
        return fixed, custom

    @property
    def metallurgical_service_ids(self):
        grouped = {}
        for service in self.fields["services"].queryset:
            if (
                service.metallurgical_type
                and service.metallurgical_type != Service.NONE
            ):
                grouped.setdefault(service.metallurgical_type, []).append(service.pk)
        return grouped

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

    @staticmethod
    def _parse_custom_json(raw):
        if not raw:
            return []
        try:
            values = json.loads(raw)
        except (TypeError, ValueError):
            return []
        if not isinstance(values, list):
            return []
        return [str(v).strip() for v in values if str(v).strip()]

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

        selected_services = cleaned.get("services") or []
        selected_types = {s.metallurgical_type for s in selected_services}

        leaching_custom = self._parse_custom_json(
            cleaned.get("leaching_custom_parameters")
        )
        cleaned["leaching_custom_parameters_list"] = leaching_custom
        if Service.CYANIDE_CONVENTIONAL in selected_types:
            if not cleaned.get("leaching_parameters") and not leaching_custom:
                self.add_error(
                    "leaching_parameters",
                    "Select at least one Leaching Parameter "
                    "(Cyanide Conventional Leaching Test was selected).",
                )

        optimization_custom = self._parse_custom_json(
            cleaned.get("optimization_custom_parameters")
        )
        cleaned["optimization_custom_parameters_list"] = optimization_custom
        if Service.CYANIDE_OPTIMIZATION in selected_types:
            if not cleaned.get("optimization_parameters") and not optimization_custom:
                self.add_error(
                    "optimization_parameters",
                    "Select at least one Optimization Parameter "
                    "(Cyanide Leaching Parameter Optimization was selected).",
                )

        return cleaned

    def _save_parameters_for(self, sample_service, fixed_codes, custom_labels):
        sample_service.parameters.all().delete()
        objs = []
        order = 0
        for code in fixed_codes:
            objs.append(
                SampleServiceParameter(
                    sample_service=sample_service, parameter=code, order=order
                )
            )
            order += 1
        for label in custom_labels:
            objs.append(
                SampleServiceParameter(
                    sample_service=sample_service,
                    parameter=SampleServiceParameter.OTHER,
                    custom_label=label,
                    order=order,
                )
            )
            order += 1
        if objs:
            SampleServiceParameter.objects.bulk_create(objs)

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
                    sample_service.delete()  # cascades to its parameters

            for service in selected_services:
                if service not in existing:
                    sample_service = SampleService.objects.create(
                        sample=sample, service=service
                    )
                    existing[service] = sample_service

            for service in selected_services:
                sample_service = existing[service]
                if service.metallurgical_type == Service.CYANIDE_CONVENTIONAL:
                    self._save_parameters_for(
                        sample_service,
                        self.cleaned_data.get("leaching_parameters") or [],
                        self.cleaned_data.get("leaching_custom_parameters_list") or [],
                    )
                elif service.metallurgical_type == Service.CYANIDE_OPTIMIZATION:
                    self._save_parameters_for(
                        sample_service,
                        self.cleaned_data.get("optimization_parameters") or [],
                        self.cleaned_data.get("optimization_custom_parameters_list")
                        or [],
                    )
                # CARBON_ACTIVITY / NONE: nothing to store — the fixed
                # Carbon Activity worksheet config is attached automatically
                # at worksheet-generation time based on metallurgical_type.

        return sample
