from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.functional import cached_property

from samples.models import Sample, SampleServiceParameter, Service
from worksheet.models import Worksheet, WorksheetRow

CYANIDE_TYPES = (Service.CYANIDE_CONVENTIONAL, Service.CYANIDE_OPTIMIZATION)
METALLURGICAL_TYPES = CYANIDE_TYPES + (Service.CARBON_ACTIVITY,)
ZERO = Decimal("0")


def _quantize(value, places="0.0001"):
    if value is None:
        return None
    return Decimal(value).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _input_field(max_digits=10, decimal_places=4, maximum=None):
    validators = [MinValueValidator(ZERO)]
    if maximum is not None:
        validators.append(MaxValueValidator(maximum))
    return models.DecimalField(
        max_digits=max_digits,
        decimal_places=decimal_places,
        null=True,
        blank=True,
        validators=validators,
    )


def _result_field(max_digits=14, decimal_places=4):
    return models.DecimalField(
        max_digits=max_digits,
        decimal_places=decimal_places,
        null=True,
        blank=True,
        editable=False,
    )


def get_metallurgical_type(sample):
    sample_service = (
        sample.sample_services.filter(
            service__metallurgical_type__in=METALLURGICAL_TYPES
        )
        .select_related("service")
        .first()
    )
    return sample_service.service.metallurgical_type if sample_service else None


def latest_mineral_worksheet(submission):
    return (
        Worksheet.objects.filter(
            submission=submission, worksheet_type=Worksheet.MINERAL_ANALYSIS
        )
        .order_by("-generated_at", "-id")
        .first()
    )


def worksheet_rows_for_sample(sample):
    worksheet = latest_mineral_worksheet(sample.submission)
    if worksheet is None:
        return []
    return list(
        worksheet.rows.filter(
            lab_sample_mapping__sample=sample,
            row_type__in=[WorksheetRow.SAMPLE_ROW, WorksheetRow.REPLICATE_ROW],
        )
        .select_related("worksheet", "lab_sample_mapping")
        .order_by("row_number")
    )


def latest_carbon_worksheet(submission):
    return (
        Worksheet.objects.filter(
            submission=submission, worksheet_type=Worksheet.CARBON_ACTIVITY
        )
        .order_by("-generated_at", "-id")
        .first()
    )


def carbon_worksheet_rows_for_sample(sample):
    worksheet = latest_carbon_worksheet(sample.submission)
    if worksheet is None:
        return []
    return list(
        worksheet.rows.filter(
            lab_sample_mapping__sample=sample,
            row_type__in=[WorksheetRow.SAMPLE_ROW, WorksheetRow.REPLICATE_ROW],
        )
        .select_related("worksheet", "lab_sample_mapping")
        .order_by("row_number")
    )


def worksheet_label(row, position=None):
    mapping = row.lab_sample_mapping
    if mapping is None:
        return ""
    prefix, _, suffix = mapping.lab_sample_id.rpartition("-")
    number = row.replicate_number or position
    letter = chr(64 + number) if number else ""
    return f"{prefix}-{suffix.lstrip('0') or '0'}{letter}"


def format_lab_sample_id(raw):
    prefix, _, suffix = (raw or "").rpartition("-")
    if not prefix:
        return raw or ""
    return f"{prefix}-{suffix.lstrip('0') or '0'}"


def lab_sample_id_for(sample):
    mapping = getattr(sample, "lab_mapping", None)
    if mapping is None:
        return sample.slug.upper()
    return format_lab_sample_id(mapping.lab_sample_id)


def worksheet_elements(worksheet):
    tokens = {
        token.strip().upper()
        for token in (worksheet.elements or "").replace("/", ",").split(",")
        if token.strip()
    }
    return {
        "gold": "AU" in tokens,
        "copper": "CU" in tokens,
        "silver": "AG" in tokens,
        "sulphur": "S" in tokens,
    }


class BaseEntry(models.Model):
    DRAFT = "DRAFT"
    READY_FOR_SUBMISSION = "READY_FOR_SUBMISSION"
    SUBMITTED_TO_QC = "SUBMITTED_TO_QC"

    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (READY_FOR_SUBMISSION, "Ready for Submission"),
        (SUBMITTED_TO_QC, "Submitted to QC"),
    ]

    EDITABLE_SAMPLE_STATUSES = (
        Sample.SUBMITTED_TO_LAB,
        Sample.DRAFT,
        Sample.READY_FOR_SUBMISSION,
        Sample.REASSAY_REQUIRED,
    )

    INCOMPLETE_MESSAGE = (
        "All required fields must be completed before submitting to QC."
    )

    status = models.CharField(
        max_length=25, choices=STATUS_CHOICES, default=DRAFT, db_index=True
    )
    revision = models.PositiveSmallIntegerField(default=1)
    is_reassay = models.BooleanField(default=False)
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reassays",
    )
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_entries",
        limit_choices_to={"role": "CHEMIST"},
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @classmethod
    def creation_kwargs(cls, sample):
        return {}

    @classmethod
    def current_for(cls, sample, user=None):
        with transaction.atomic():
            locked = Sample.objects.select_for_update().get(pk=sample.pk)
            latest = cls.objects.filter(sample=locked).order_by("-revision").first()
            owner = user if user is not None and user.is_authenticated else None

            if latest is None:
                if locked.analysis_status not in cls.EDITABLE_SAMPLE_STATUSES:
                    return None
                return cls.objects.create(
                    sample=locked, entered_by=owner, **cls.creation_kwargs(locked)
                )

            if (
                locked.analysis_status == Sample.REASSAY_REQUIRED
                and latest.status == cls.SUBMITTED_TO_QC
            ):
                return cls.objects.create(
                    sample=locked,
                    revision=latest.revision + 1,
                    is_reassay=True,
                    supersedes=latest,
                    entered_by=owner,
                    **cls.creation_kwargs(locked),
                )

            return latest

    @property
    def is_locked(self):
        return self.status == self.SUBMITTED_TO_QC

    def is_complete(self):
        raise NotImplementedError

    def before_submit(self):
        return None

    def after_submit(self):
        return None

    def refresh_status(self, user=None):
        if self.status == self.SUBMITTED_TO_QC:
            return self.status
        self.status = self.READY_FOR_SUBMISSION if self.is_complete() else self.DRAFT
        fields = ["status", "updated_at"]
        if user is not None and user.is_authenticated:
            self.entered_by = user
            fields.append("entered_by")
        self.save(update_fields=fields)
        return self.status

    def submit_to_qc(self, user=None):
        with transaction.atomic():
            current = type(self).objects.select_for_update().get(pk=self.pk)
            if current.status == self.SUBMITTED_TO_QC:
                raise ValidationError("This entry has already been submitted to QC.")

            sample = Sample.objects.select_for_update().get(pk=self.sample_id)
            if sample.analysis_status not in self.EDITABLE_SAMPLE_STATUSES:
                raise ValidationError("This sample is no longer open for data entry.")

            if not self.is_complete():
                raise ValidationError(self.INCOMPLETE_MESSAGE)

            self.before_submit()

            self.status = self.SUBMITTED_TO_QC
            self.submitted_at = timezone.now()
            fields = ["status", "submitted_at", "updated_at"]
            if user is not None and user.is_authenticated:
                self.entered_by = user
                fields.append("entered_by")
            self.save(update_fields=fields)

            sample.set_analysis_status(
                Sample.REASSAY_SUBMITTED if self.is_reassay else Sample.SUBMITTED_TO_QC
            )
            self.after_submit()


class MineralAnalysisEntry(BaseEntry):
    INCOMPLETE_MESSAGE = (
        "All required replicate fields must be completed before submitting to QC."
    )

    sample = models.ForeignKey(
        Sample, on_delete=models.CASCADE, related_name="mineral_analysis_entries"
    )

    class Meta:
        verbose_name_plural = "Mineral Analysis Entries"
        ordering = ["-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["sample", "revision"], name="unique_mineral_entry_revision"
            )
        ]

    def __str__(self):
        return f"Mineral Analysis — {self.sample.slug} (rev {self.revision})"

    @cached_property
    def registered_elements(self):
        rows = list(
            Service.objects.filter(sample_services__sample=self.sample).values_list(
                "tests_gold", "tests_copper", "tests_silver", "tests_sulphur"
            )
        )
        gold = any(row[0] for row in rows)
        copper = any(row[1] for row in rows)
        silver = any(row[2] for row in rows)
        sulphur = any(row[3] for row in rows)

        if self.sample.sample_type == Sample.CARBON:
            sulphur = False

        return {"gold": gold, "copper": copper, "silver": silver, "sulphur": sulphur}

    @property
    def show_weight_column(self):
        return self.sample.sample_type != Sample.PROCESS_SOLUTION

    @cached_property
    def worksheet_rows(self):
        return worksheet_rows_for_sample(self.sample)

    @property
    def required_replicate_count(self):
        return len(self.worksheet_rows) or self.sample.replicate_count

    def ensure_replicates(self):
        rows = self.worksheet_rows
        with transaction.atomic():
            if rows:
                for number, row in enumerate(rows, start=1):
                    replicate, created = MineralAnalysisReplicate.objects.get_or_create(
                        entry=self,
                        replicate_number=number,
                        defaults={"worksheet_row": row},
                    )
                    if not created and replicate.worksheet_row_id != row.pk:
                        replicate.worksheet_row = row
                        replicate.save(update_fields=["worksheet_row", "updated_at"])
                return

            existing = set(self.replicates.values_list("replicate_number", flat=True))
            for number in range(1, self.sample.replicate_count + 1):
                if number not in existing:
                    MineralAnalysisReplicate.objects.create(
                        entry=self, replicate_number=number
                    )

    def is_complete(self):
        needed = self.required_replicate_count
        elements = self.registered_elements
        if needed == 0 or not any(elements.values()):
            return False

        replicates = list(self.replicates.all())
        if len(replicates) != needed:
            return False

        for replicate in replicates:
            if self.show_weight_column and (
                replicate.weight is None or replicate.weight <= 0
            ):
                return False
            if elements["gold"] and (
                replicate.au_aas is None or replicate.au_df is None
            ):
                return False
            if elements["copper"] and (
                replicate.cu_aas is None or replicate.cu_df is None
            ):
                return False
            if elements["silver"] and (
                replicate.ag_aas is None or replicate.ag_df is None
            ):
                return False
            if elements["sulphur"] and replicate.sulphur is None:
                return False

        return True


class MineralAnalysisReplicate(models.Model):
    RESULT_FIELDS = ("gold_ppm", "copper_ppm", "silver_ppm")

    entry = models.ForeignKey(
        MineralAnalysisEntry, on_delete=models.CASCADE, related_name="replicates"
    )
    replicate_number = models.PositiveSmallIntegerField()
    worksheet_row = models.ForeignKey(
        "worksheet.WorksheetRow",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    weight = _input_field(10, 4)
    au_aas = _input_field(12, 6)
    au_df = _input_field(10, 4)
    cu_aas = _input_field(12, 6)
    cu_df = _input_field(10, 4)
    ag_aas = _input_field(12, 6)
    ag_df = _input_field(10, 4)
    sulphur = _input_field(10, 4)

    gold_ppm = _result_field()
    copper_ppm = _result_field()
    silver_ppm = _result_field()

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["replicate_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "replicate_number"], name="unique_replicate_per_entry"
            )
        ]

    def __str__(self):
        return f"{self.entry.sample.slug} — Rep {self.replicate_number}"

    @property
    def serial_number(self):
        row = self.worksheet_row
        if row is None:
            return self.replicate_number
        return row.display_number or row.row_number

    @property
    def label(self):
        if self.worksheet_row is None:
            return str(self.replicate_number)
        return worksheet_label(self.worksheet_row, self.replicate_number)

    def calculate(self):
        self.gold_ppm = None
        self.copper_ppm = None
        self.silver_ppm = None

        sample_type = self.entry.sample.sample_type
        if sample_type == Sample.CARBON:
            self._calculate_carbon()
        elif sample_type == Sample.PROCESS_SOLUTION:
            self._calculate_process_solution()
        else:
            self._calculate_standard_solid()

    def _calculate_standard_solid(self):
        weight = self.weight
        if weight is None or weight <= 0:
            return
        if self.au_aas is not None and self.au_df is not None:
            self.gold_ppm = _quantize(
                ((Decimal("250") - (Decimal("0.35") * weight)) / weight)
                * self.au_aas
                * self.au_df
                * Decimal("0.08")
            )
        if self.cu_aas is not None and self.cu_df is not None:
            self.copper_ppm = _quantize(
                (Decimal("250") / weight) * self.cu_aas * self.cu_df
            )
        if self.ag_aas is not None and self.ag_df is not None:
            self.silver_ppm = _quantize(
                (Decimal("250") / weight) * self.ag_aas * self.ag_df
            )

    def _calculate_carbon(self):
        if self.au_aas is not None and self.au_df is not None:
            self.gold_ppm = _quantize(Decimal("50") * self.au_aas * self.au_df)
        if self.cu_aas is not None and self.cu_df is not None:
            self.copper_ppm = _quantize(Decimal("50") * self.cu_aas * self.cu_df)
        if self.ag_aas is not None and self.ag_df is not None:
            self.silver_ppm = _quantize(Decimal("50") * self.ag_aas * self.ag_df)

    def _calculate_process_solution(self):
        if self.au_aas is not None and self.au_df is not None:
            self.gold_ppm = _quantize(self.au_aas * self.au_df)
        if self.cu_aas is not None and self.cu_df is not None:
            self.copper_ppm = _quantize(self.cu_aas * self.cu_df)
        if self.ag_aas is not None and self.ag_df is not None:
            self.silver_ppm = _quantize(self.ag_aas * self.ag_df)

    def save(self, *args, **kwargs):
        self.calculate()
        super().save(*args, **kwargs)


class CRMEntry(models.Model):
    RESULT_FIELDS = ()

    DRAFT = "DRAFT"
    READY_FOR_SUBMISSION = "READY_FOR_SUBMISSION"
    SUBMITTED_TO_QC = "SUBMITTED_TO_QC"

    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (READY_FOR_SUBMISSION, "Ready for Submission"),
        (SUBMITTED_TO_QC, "Submitted to QC"),
    ]

    DATA_FIELDS = (
        "weight",
        "au_aas",
        "au_df",
        "cu_aas",
        "cu_df",
        "ag_aas",
        "ag_df",
        "sulphur",
    )

    worksheet_row = models.OneToOneField(
        "worksheet.WorksheetRow",
        on_delete=models.CASCADE,
        related_name="crm_entry",
    )

    weight = _input_field(10, 4)
    au_aas = _input_field(12, 6)
    au_df = _input_field(10, 4)
    cu_aas = _input_field(12, 6)
    cu_df = _input_field(10, 4)
    ag_aas = _input_field(12, 6)
    ag_df = _input_field(10, 4)
    sulphur = _input_field(10, 4)

    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_entries",
        limit_choices_to={"role": "CHEMIST"},
    )
    status = models.CharField(
        max_length=25, choices=STATUS_CHOICES, default=DRAFT, db_index=True
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["worksheet_row__row_number"]
        verbose_name = "CRM Entry"
        verbose_name_plural = "CRM Entries"

    def __str__(self):
        return f"CRM {self.serial_number}"

    @property
    def serial_number(self):
        row = self.worksheet_row
        return row.display_number or row.row_number

    @property
    def has_data(self):
        return any(getattr(self, field) is not None for field in self.DATA_FIELDS)

    def is_complete(self, elements, needs_weight=True):
        if needs_weight and (self.weight is None or self.weight <= 0):
            return False
        if elements["gold"] and (self.au_aas is None or self.au_df is None):
            return False
        if elements["copper"] and (self.cu_aas is None or self.cu_df is None):
            return False
        if elements["silver"] and (self.ag_aas is None or self.ag_df is None):
            return False
        if elements["sulphur"] and self.sulphur is None:
            return False
        return True

    @property
    def is_locked(self):
        return self.status == self.SUBMITTED_TO_QC

    def refresh_status(self, elements, user=None):
        if self.is_locked:
            return self.status
        self.status = (
            self.READY_FOR_SUBMISSION if self.is_complete(elements) else self.DRAFT
        )
        fields = ["status", "updated_at"]
        if user is not None and user.is_authenticated:
            self.entered_by = user
            fields.append("entered_by")
        self.save(update_fields=fields)
        return self.status

    def submit_to_qc(self, elements, user=None):
        with transaction.atomic():
            current = type(self).objects.select_for_update().get(pk=self.pk)
            if current.status == self.SUBMITTED_TO_QC:
                raise ValidationError("This CRM has already been submitted to QC.")
            if not self.is_complete(elements):
                raise ValidationError(
                    "All CRM fields must be completed before submitting to QC."
                )
            self.status = self.SUBMITTED_TO_QC
            self.submitted_at = timezone.now()
            fields = ["status", "submitted_at", "updated_at"]
            if user is not None and user.is_authenticated:
                self.entered_by = user
                fields.append("entered_by")
            self.save(update_fields=fields)


class MetallurgicalTestEntry(BaseEntry):
    INCOMPLETE_MESSAGE = "All parameter rows must be completed before submitting to QC."

    SI_UNIT_CHOICES = [
        ("kg", "kg"),
        ("g", "g"),
        ("mL", "mL"),
        ("L", "L"),
    ]

    sample = models.ForeignKey(
        Sample, on_delete=models.CASCADE, related_name="metallurgical_test_entries"
    )
    test_type = models.CharField(
        max_length=25,
        choices=[
            (Service.CYANIDE_CONVENTIONAL, "Cyanide Conventional Leaching Test"),
            (Service.CYANIDE_OPTIMIZATION, "Cyanide Leaching Parameter Optimization"),
        ],
    )

    class Meta:
        verbose_name_plural = "Metallurgical Test Entries"
        ordering = ["-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["sample", "revision"],
                name="unique_metallurgical_entry_revision",
            )
        ]

    def __str__(self):
        return (
            f"{self.get_test_type_display()} — {self.sample.slug} (rev {self.revision})"
        )

    @classmethod
    def creation_kwargs(cls, sample):
        test_type = get_metallurgical_type(sample)
        if test_type not in CYANIDE_TYPES:
            raise ValidationError(
                "This sample is not registered for a cyanide leaching test."
            )
        return {"test_type": test_type}

    def ensure_parameter_rows(self):
        assigned = SampleServiceParameter.objects.filter(
            sample_service__sample=self.sample
        ).order_by("order", "id")

        with transaction.atomic():
            existing = set(self.rows.values_list("source_parameter_id", flat=True))
            for parameter in assigned:
                if parameter.id not in existing:
                    MetallurgicalTestRow.objects.create(
                        entry=self, source_parameter=parameter
                    )

    def is_complete(self):
        rows = list(self.rows.all())
        if not rows:
            return False
        for row in rows:
            if row.weight_volume is None or row.weight_volume <= 0 or not row.si_unit:
                return False
            if (
                row.gold_recovery_12h is None
                or row.gold_recovery_24h is None
                or row.gold_recovery_48h is None
            ):
                return False
        return True


class MetallurgicalTestRow(models.Model):
    RESULT_FIELDS = ()

    entry = models.ForeignKey(
        MetallurgicalTestEntry, on_delete=models.CASCADE, related_name="rows"
    )
    source_parameter = models.ForeignKey(
        SampleServiceParameter, on_delete=models.PROTECT, related_name="+"
    )

    weight_volume = _input_field(10, 4)
    si_unit = models.CharField(
        max_length=4, choices=MetallurgicalTestEntry.SI_UNIT_CHOICES, blank=True
    )
    gold_recovery_12h = _input_field(8, 4, maximum=Decimal("100"))
    gold_recovery_24h = _input_field(8, 4, maximum=Decimal("100"))
    gold_recovery_48h = _input_field(8, 4, maximum=Decimal("100"))
    remarks = models.TextField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_parameter__order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "source_parameter"], name="unique_row_per_parameter"
            )
        ]

    def __str__(self):
        return f"{self.entry} — {self.source_parameter.display_label}"


class CarbonActivityEntry(BaseEntry):
    INCOMPLETE_MESSAGE = "All replicates must be completed before submitting to QC."

    REPLICATE_COUNT = 2

    sample = models.ForeignKey(
        Sample, on_delete=models.CASCADE, related_name="carbon_activity_entries"
    )
    final_carbon_activity_percent = _result_field(12, 4)

    class Meta:
        verbose_name_plural = "Carbon Activity Entries"
        ordering = ["-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["sample", "revision"], name="unique_carbon_entry_revision"
            )
        ]

    def __str__(self):
        return f"Carbon Activity — {self.sample.slug} (rev {self.revision})"

    @cached_property
    def worksheet_rows(self):
        return carbon_worksheet_rows_for_sample(self.sample)

    @property
    def required_replicate_count(self):
        return len(self.worksheet_rows) or self.REPLICATE_COUNT

    def ensure_replicates(self):
        rows = self.worksheet_rows
        with transaction.atomic():
            if rows:
                for number, row in enumerate(rows, start=1):
                    replicate, created = CarbonActivityReplicate.objects.get_or_create(
                        entry=self,
                        replicate_number=number,
                        defaults={"worksheet_row": row},
                    )
                    if not created and replicate.worksheet_row_id != row.pk:
                        replicate.worksheet_row = row
                        replicate.save(update_fields=["worksheet_row", "updated_at"])
                return

            existing = set(self.replicates.values_list("replicate_number", flat=True))
            for number in range(1, self.REPLICATE_COUNT + 1):
                if number not in existing:
                    CarbonActivityReplicate.objects.create(
                        entry=self, replicate_number=number
                    )

    def is_complete(self):
        rows = list(self.replicates.all())
        if len(rows) != self.required_replicate_count:
            return False
        return all(
            row.standard_concentration is not None
            and row.final_concentration_sample is not None
            and row.final_concentration_standard is not None
            and row.activity_percent is not None
            for row in rows
        )

    def recalculate_final_activity(self):
        activities = [
            row.activity_percent
            for row in self.replicates.all()
            if row.activity_percent is not None
        ]
        if activities and len(activities) == self.required_replicate_count:
            average = sum(activities) / Decimal(len(activities))
            self.final_carbon_activity_percent = _quantize(average * Decimal("0.80"))
        else:
            self.final_carbon_activity_percent = None
        self.save(update_fields=["final_carbon_activity_percent", "updated_at"])

    def before_submit(self):
        self.recalculate_final_activity()


class CarbonActivityReplicate(models.Model):
    RESULT_FIELDS = ("activity_percent",)

    entry = models.ForeignKey(
        CarbonActivityEntry, on_delete=models.CASCADE, related_name="replicates"
    )
    replicate_number = models.PositiveSmallIntegerField()
    worksheet_row = models.ForeignKey(
        "worksheet.WorksheetRow",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    standard_concentration = _input_field(10, 4)
    final_concentration_sample = _input_field(10, 4)
    final_concentration_standard = _input_field(10, 4)
    remarks = models.TextField(blank=True)

    activity_percent = _result_field(12, 4)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["replicate_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "replicate_number"], name="unique_carbon_replicate"
            )
        ]

    def __str__(self):
        return f"{self.entry.sample.slug} — Carbon Rep {self.replicate_number}"

    @property
    def label(self):
        if self.worksheet_row is None:
            return f"Replicate {self.replicate_number}"
        return worksheet_label(self.worksheet_row, self.replicate_number)

    def calculate(self):
        std = self.standard_concentration
        sample_conc = self.final_concentration_sample
        standard_conc = self.final_concentration_standard

        self.activity_percent = None
        if std is None or sample_conc is None or standard_conc is None:
            return

        denominator = std - standard_conc
        if denominator != 0:
            self.activity_percent = _quantize(
                ((std - sample_conc) / denominator) * Decimal("100")
            )

    def save(self, *args, **kwargs):
        self.calculate()
        super().save(*args, **kwargs)
