from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from samples.models import Sample, SampleServiceParameter, Service


def _quantize(value, places="0.0001"):
    if value is None:
        return None
    return Decimal(value).quantize(Decimal(places), rounding=ROUND_HALF_UP)


class MineralAnalysisEntry(models.Model):
    DRAFT = "DRAFT"
    READY_FOR_SUBMISSION = "READY_FOR_SUBMISSION"
    SUBMITTED_TO_QC = "SUBMITTED_TO_QC"

    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (READY_FOR_SUBMISSION, "Ready for Submission"),
        (SUBMITTED_TO_QC, "Submitted to QC"),
    ]

    sample = models.OneToOneField(
        Sample, on_delete=models.CASCADE, related_name="mineral_analysis_entry"
    )
    status = models.CharField(
        max_length=25, choices=STATUS_CHOICES, default=DRAFT, db_index=True
    )
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mineral_analysis_entries",
        limit_choices_to={"role": "CHEMIST"},
    )
    is_reassay = models.BooleanField(default=False)
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reassayed_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Mineral Analysis Entries"

    def __str__(self):
        return f"Mineral Analysis — {self.sample.slug}"

    @property
    def registered_elements(self):
        services = Service.objects.filter(sample_services__sample=self.sample)
        gold = services.filter(tests_gold=True).exists()
        copper = services.filter(tests_copper=True).exists()
        silver = services.filter(tests_silver=True).exists()
        sulphur = services.filter(tests_sulphur=True).exists()

        if self.sample.sample_type == Sample.CARBON:
            sulphur = False

        return {"gold": gold, "copper": copper, "silver": silver, "sulphur": sulphur}

    @property
    def show_weight_column(self):
        return self.sample.sample_type != Sample.PROCESS_SOLUTION

    @property
    def required_replicate_count(self):
        return self.sample.replicate_count

    def ensure_replicates(self):
        existing = self.replicates.count()
        needed = self.required_replicate_count
        with transaction.atomic():
            for n in range(existing + 1, needed + 1):
                MineralAnalysisReplicate.objects.create(entry=self, replicate_number=n)

    def is_complete(self):
        elements = self.registered_elements
        for replicate in self.replicates.all():
            if self.show_weight_column and replicate.weight is None:
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
        return self.replicates.count() == self.required_replicate_count

    def refresh_status(self):
        self.status = self.READY_FOR_SUBMISSION if self.is_complete() else self.DRAFT
        self.save(update_fields=["status", "updated_at"])
        return self.status

    def submit_to_qc(self):
        if not self.is_complete():
            raise ValidationError(
                "All required replicate fields must be completed before submitting to QC."
            )
        self.status = self.SUBMITTED_TO_QC
        self.save(update_fields=["status", "updated_at"])
        new_sample_status = (
            Sample.REASSAY_SUBMITTED if self.is_reassay else Sample.SUBMITTED_TO_QC
        )
        self.sample.set_analysis_status(new_sample_status)


class MineralAnalysisReplicate(models.Model):
    entry = models.ForeignKey(
        MineralAnalysisEntry, on_delete=models.CASCADE, related_name="replicates"
    )
    replicate_number = models.PositiveSmallIntegerField()

    weight = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    au_aas = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    au_df = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    cu_aas = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    cu_df = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    ag_aas = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    ag_df = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    sulphur = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )

    gold_ppm = models.DecimalField(
        max_digits=14, decimal_places=6, null=True, blank=True, editable=False
    )
    copper_ppm = models.DecimalField(
        max_digits=14, decimal_places=6, null=True, blank=True, editable=False
    )
    silver_ppm = models.DecimalField(
        max_digits=14, decimal_places=6, null=True, blank=True, editable=False
    )

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

    def calculate(self):
        sample_type = self.entry.sample.sample_type
        if sample_type == Sample.CARBON:
            self._calculate_carbon()
        elif sample_type == Sample.PROCESS_SOLUTION:
            self._calculate_process_solution()
        else:
            self._calculate_standard_solid()

    def _calculate_standard_solid(self):
        w = self.weight
        if w and w != 0:
            if self.au_aas is not None and self.au_df is not None:
                self.gold_ppm = _quantize(
                    ((Decimal("250") - (Decimal("0.35") * w)) / w)
                    * self.au_aas
                    * self.au_df
                    * Decimal("0.08")
                )
            if self.cu_aas is not None and self.cu_df is not None:
                self.copper_ppm = _quantize(
                    (Decimal("250") / w) * self.cu_aas * self.cu_df
                )
            if self.ag_aas is not None and self.ag_df is not None:
                self.silver_ppm = _quantize(
                    (Decimal("250") / w) * self.ag_aas * self.ag_df
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


class CRMSequenceCounter(models.Model):
    samples_since_last_crm = models.PositiveIntegerField(default=0)
    total_crm_inserted = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "CRM Sequence Counter"

    @classmethod
    def get_singleton(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def register_sample_and_maybe_insert_crm(cls, mineral_entry):
        elements = mineral_entry.registered_elements
        if mineral_entry.sample.sample_type == Sample.PROCESS_SOLUTION:
            return None
        if not any(elements.values()):
            return None

        with transaction.atomic():
            counter, _ = cls.objects.select_for_update().get_or_create(pk=1)
            counter.samples_since_last_crm += 1

            crm_entry = None
            if counter.samples_since_last_crm >= 2:
                counter.samples_since_last_crm = 0
                counter.total_crm_inserted += 1
                crm_entry = CRMEntry.objects.create(
                    sequence_number=counter.total_crm_inserted,
                    inserted_after_entry=mineral_entry,
                )

            counter.save(
                update_fields=[
                    "samples_since_last_crm",
                    "total_crm_inserted",
                    "updated_at",
                ]
            )

        return crm_entry


class CRMEntry(models.Model):
    sequence_number = models.PositiveIntegerField(unique=True)
    inserted_after_entry = models.ForeignKey(
        MineralAnalysisEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_entries_after",
    )

    weight = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    au_aas = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    au_df = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    cu_aas = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    cu_df = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    ag_aas = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    ag_df = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    sulphur = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence_number"]
        verbose_name = "CRM Entry"
        verbose_name_plural = "CRM Entries"

    def __str__(self):
        return f"CRM #{self.sequence_number}"


class MetallurgicalTestEntry(models.Model):
    DRAFT = "DRAFT"
    READY_FOR_SUBMISSION = "READY_FOR_SUBMISSION"
    SUBMITTED_TO_QC = "SUBMITTED_TO_QC"

    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (READY_FOR_SUBMISSION, "Ready for Submission"),
        (SUBMITTED_TO_QC, "Submitted to QC"),
    ]

    SI_UNIT_CHOICES = [
        ("kg", "kg"),
        ("g", "g"),
        ("mL", "mL"),
        ("L", "L"),
    ]

    sample = models.OneToOneField(
        Sample, on_delete=models.CASCADE, related_name="metallurgical_test_entry"
    )
    test_type = models.CharField(
        max_length=25,
        choices=[
            (Service.CYANIDE_CONVENTIONAL, "Cyanide Conventional Leaching Test"),
            (Service.CYANIDE_OPTIMIZATION, "Cyanide Leaching Parameter Optimization"),
        ],
    )
    status = models.CharField(
        max_length=25, choices=STATUS_CHOICES, default=DRAFT, db_index=True
    )
    is_reassay = models.BooleanField(default=False)
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reassayed_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Metallurgical Test Entries"

    def __str__(self):
        return f"{self.get_test_type_display()} — {self.sample.slug}"

    def ensure_parameter_rows(self):
        assigned = SampleServiceParameter.objects.filter(
            sample_service__sample=self.sample
        ).order_by("order", "id")

        existing_param_ids = set(
            self.rows.values_list("source_parameter_id", flat=True)
        )
        for param in assigned:
            if param.id not in existing_param_ids:
                MetallurgicalTestRow.objects.create(entry=self, source_parameter=param)

    def is_complete(self):
        rows = list(self.rows.all())
        if not rows:
            return False
        for row in rows:
            if row.weight_volume is None or not row.si_unit:
                return False
            if (
                row.gold_recovery_12h is None
                or row.gold_recovery_24h is None
                or row.gold_recovery_48h is None
            ):
                return False
        return True

    def refresh_status(self):
        self.status = self.READY_FOR_SUBMISSION if self.is_complete() else self.DRAFT
        self.save(update_fields=["status", "updated_at"])
        return self.status

    def submit_to_qc(self):
        if not self.is_complete():
            raise ValidationError(
                "All parameter rows must be completed before submitting to QC."
            )
        self.status = self.SUBMITTED_TO_QC
        self.save(update_fields=["status", "updated_at"])
        new_sample_status = (
            Sample.REASSAY_SUBMITTED if self.is_reassay else Sample.SUBMITTED_TO_QC
        )
        self.sample.set_analysis_status(new_sample_status)


class MetallurgicalTestRow(models.Model):
    entry = models.ForeignKey(
        MetallurgicalTestEntry, on_delete=models.CASCADE, related_name="rows"
    )
    source_parameter = models.ForeignKey(
        SampleServiceParameter, on_delete=models.PROTECT, related_name="+"
    )

    weight_volume = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    si_unit = models.CharField(
        max_length=4, choices=MetallurgicalTestEntry.SI_UNIT_CHOICES, blank=True
    )
    gold_recovery_12h = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True
    )
    gold_recovery_24h = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True
    )
    gold_recovery_48h = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True
    )
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


class CarbonActivityEntry(models.Model):
    DRAFT = "DRAFT"
    READY_FOR_SUBMISSION = "READY_FOR_SUBMISSION"
    SUBMITTED_TO_QC = "SUBMITTED_TO_QC"

    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (READY_FOR_SUBMISSION, "Ready for Submission"),
        (SUBMITTED_TO_QC, "Submitted to QC"),
    ]

    REPLICATE_COUNT = 2

    sample = models.OneToOneField(
        Sample, on_delete=models.CASCADE, related_name="carbon_activity_entry"
    )
    status = models.CharField(
        max_length=25, choices=STATUS_CHOICES, default=DRAFT, db_index=True
    )
    is_reassay = models.BooleanField(default=False)
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reassayed_by",
    )
    final_carbon_activity_percent = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True, editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Carbon Activity Entries"

    def __str__(self):
        return f"Carbon Activity — {self.sample.slug}"

    def ensure_replicates(self):
        existing = self.replicates.count()
        with transaction.atomic():
            for n in range(existing + 1, self.REPLICATE_COUNT + 1):
                CarbonActivityReplicate.objects.create(entry=self, replicate_number=n)

    def is_complete(self):
        rows = list(self.replicates.all())
        if len(rows) != self.REPLICATE_COUNT:
            return False
        return all(
            r.standard_concentration is not None
            and r.final_concentration_sample is not None
            and r.final_concentration_standard is not None
            for r in rows
        )

    def recalculate_final_activity(self):
        activities = [
            r.activity_percent
            for r in self.replicates.all()
            if r.activity_percent is not None
        ]
        if len(activities) == self.REPLICATE_COUNT:
            average = sum(activities) / Decimal(self.REPLICATE_COUNT)
            self.final_carbon_activity_percent = _quantize(average * Decimal("0.80"))
        else:
            self.final_carbon_activity_percent = None
        self.save(update_fields=["final_carbon_activity_percent", "updated_at"])

    def refresh_status(self):
        self.status = self.READY_FOR_SUBMISSION if self.is_complete() else self.DRAFT
        self.save(update_fields=["status", "updated_at"])
        return self.status

    def submit_to_qc(self):
        if not self.is_complete():
            raise ValidationError(
                "Both replicates must be completed before submitting to QC."
            )
        self.recalculate_final_activity()
        self.status = self.SUBMITTED_TO_QC
        self.save(update_fields=["status", "updated_at"])
        new_sample_status = (
            Sample.REASSAY_SUBMITTED if self.is_reassay else Sample.SUBMITTED_TO_QC
        )
        self.sample.set_analysis_status(new_sample_status)


class CarbonActivityReplicate(models.Model):
    entry = models.ForeignKey(
        CarbonActivityEntry, on_delete=models.CASCADE, related_name="replicates"
    )
    replicate_number = models.PositiveSmallIntegerField()

    standard_concentration = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    final_concentration_sample = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    final_concentration_standard = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    remarks = models.TextField(blank=True)

    activity_percent = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True, editable=False
    )

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

    def calculate(self):
        std = self.standard_concentration
        sample_conc = self.final_concentration_sample
        standard_conc = self.final_concentration_standard

        if std is not None and sample_conc is not None and standard_conc is not None:
            denominator = std - standard_conc
            if denominator != 0:
                self.activity_percent = _quantize(
                    ((std - sample_conc) / denominator) * Decimal("100")
                )
            else:
                self.activity_percent = None
        else:
            self.activity_percent = None

    def save(self, *args, **kwargs):
        self.calculate()
        super().save(*args, **kwargs)
