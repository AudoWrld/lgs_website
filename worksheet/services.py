from samples.models import Sample, Service
from .models import LabSampleMapping, Worksheet, WorksheetRow

REPLICATE_RULES = {
    Sample.ROCK: 2,
    Sample.ROCK_PULP: 2,
    Sample.SOIL: 3,
    Sample.TAILINGS: 3,
    Sample.CARBON: 4,
    Sample.PROCESS_SOLUTION: 2,
}

CRM_ELIGIBLE_SERVICES = {
    "Gold & Copper Analysis",
    "Gold, Copper & Silver Analysis",
    "Gold, Copper & Sulphur Analysis",
    "Gold, Copper, Silver & Sulphur Analysis",
}

MINERAL_ELEMENT_MAP = {
    "Gold & Copper Analysis": ["Au", "Cu"],
    "Gold, Copper & Silver Analysis": ["Au", "Cu", "Ag"],
    "Gold, Copper & Sulphur Analysis": ["Au", "Cu", "S"],
    "Gold, Copper, Silver & Sulphur Analysis": ["Au", "Cu", "Ag", "S"],
    "Metallic Screening and Gold Evaluation": ["Au", "Cu"],
}


def ensure_lab_sample_ids(submission):
    existing_count = LabSampleMapping.objects.filter(
        sample__submission=submission
    ).count()
    sequence = existing_count + 1

    for sample in submission.samples.order_by("id"):
        if not hasattr(sample, "lab_mapping"):
            LabSampleMapping.objects.create(
                sample=sample,
                lab_sample_id=f"{submission.reference}-{sequence}",
            )
            sequence += 1


def _group_samples_by_worksheet_type(submission):
    groups = {
        Worksheet.MINERAL_ANALYSIS: [],
        Worksheet.CARBON_ACTIVITY: [],
        Worksheet.CONVENTIONAL_CYANIDE_LEACHING: [],
        Worksheet.PARAMETER_OPTIMIZATION: [],
    }

    for sample in submission.samples.order_by("client_sample_id"):
        for sample_service in sample.sample_services.select_related("service"):
            service = sample_service.service

            if service.metallurgical_type == Service.CARBON_ACTIVITY:
                if sample not in groups[Worksheet.CARBON_ACTIVITY]:
                    groups[Worksheet.CARBON_ACTIVITY].append(sample)
            elif service.metallurgical_type == Service.CYANIDE_CONVENTIONAL:
                if sample not in groups[Worksheet.CONVENTIONAL_CYANIDE_LEACHING]:
                    groups[Worksheet.CONVENTIONAL_CYANIDE_LEACHING].append(sample)
            elif service.metallurgical_type == Service.CYANIDE_OPTIMIZATION:
                if sample not in groups[Worksheet.PARAMETER_OPTIMIZATION]:
                    groups[Worksheet.PARAMETER_OPTIMIZATION].append(sample)
            elif service.name in MINERAL_ELEMENT_MAP:
                if sample not in groups[Worksheet.MINERAL_ANALYSIS]:
                    groups[Worksheet.MINERAL_ANALYSIS].append(sample)

    return {k: v for k, v in groups.items() if v}


def _build_mineral_analysis_worksheet(submission, samples, generated_by):
    elements_needed = []
    for sample in samples:
        for ss in sample.sample_services.select_related("service"):
            for element in MINERAL_ELEMENT_MAP.get(ss.service.name, []):
                if element not in elements_needed:
                    elements_needed.append(element)

    element_order = ["Au", "Cu", "Ag", "S"]
    elements_needed = [e for e in element_order if e in elements_needed]

    worksheet = Worksheet.objects.create(
        submission=submission,
        worksheet_type=Worksheet.MINERAL_ANALYSIS,
        elements=", ".join(elements_needed),
        method_of_analysis="Aqua Regia + AAS"
        + (" / Furnace Induction" if "S" in elements_needed else ""),
        generated_by=generated_by,
    )

    row_number = 0
    submitted_sample_count = 0
    display_counter = 0
    crm_eligible = any(
        ss.service.name in CRM_ELIGIBLE_SERVICES
        for sample in samples
        for ss in sample.sample_services.select_related("service")
    )

    for sample in samples:
        replicate_count = REPLICATE_RULES.get(sample.sample_type, 0)

        for rep in range(1, replicate_count + 1):
            row_number += 1
            display_counter += 1
            WorksheetRow.objects.create(
                worksheet=worksheet,
                row_number=row_number,
                row_type=WorksheetRow.REPLICATE_ROW,
                lab_sample_mapping=sample.lab_mapping,
                replicate_number=rep,
                beaker_id="",
                remarks="",
                display_number=display_counter,
            )

        submitted_sample_count += 1

        if sample != samples[-1]:
            row_number += 1
            WorksheetRow.objects.create(
                worksheet=worksheet,
                row_number=row_number,
                row_type=WorksheetRow.BLANK_ROW,
            )

        if crm_eligible and submitted_sample_count % 2 == 0:
            if sample == samples[-1]:
                row_number += 1
                WorksheetRow.objects.create(
                    worksheet=worksheet,
                    row_number=row_number,
                    row_type=WorksheetRow.BLANK_ROW,
                )
            row_number += 1
            display_counter += 1
            WorksheetRow.objects.create(
                worksheet=worksheet,
                row_number=row_number,
                row_type=WorksheetRow.CRM_ROW,
                display_number=display_counter,
            )

    return worksheet


def _build_carbon_activity_worksheet(submission, samples, generated_by):
    worksheet = Worksheet.objects.create(
        submission=submission,
        worksheet_type=Worksheet.CARBON_ACTIVITY,
        method_of_analysis="Carbon Activity Test Method",
        generated_by=generated_by,
    )

    row_number = 0
    display_counter = 0
    for sample in samples:
        for rep in range(1, 3):
            row_number += 1
            display_counter += 1
            WorksheetRow.objects.create(
                worksheet=worksheet,
                row_number=row_number,
                row_type=WorksheetRow.REPLICATE_ROW,
                lab_sample_mapping=sample.lab_mapping,
                replicate_number=rep,
                display_number=display_counter,
            )

    return worksheet


def _sample_service_for_type(sample, metallurgical_type):
    for sample_service in sample.sample_services.select_related("service"):
        if sample_service.service.metallurgical_type == metallurgical_type:
            return sample_service
    return None


def _build_cyanide_leaching_worksheet(
    submission, samples, generated_by, worksheet_type, metallurgical_type
):
    method = "Bottle Test + AAS"
    worksheet = Worksheet.objects.create(
        submission=submission,
        worksheet_type=worksheet_type,
        method_of_analysis=method,
        generated_by=generated_by,
    )

    row_number = 0
    display_counter = 0

    for sample in samples:
        sample_service = _sample_service_for_type(sample, metallurgical_type)
        parameters = list(sample_service.parameters.all()) if sample_service else []

        if not parameters:
            row_number += 1
            display_counter += 1
            WorksheetRow.objects.create(
                worksheet=worksheet,
                row_number=row_number,
                row_type=WorksheetRow.SAMPLE_ROW,
                lab_sample_mapping=sample.lab_mapping,
                container_label="",
                parameter="",
                display_number=display_counter,
            )
        else:
            for parameter in parameters:
                row_number += 1
                display_counter += 1
                WorksheetRow.objects.create(
                    worksheet=worksheet,
                    row_number=row_number,
                    row_type=WorksheetRow.SAMPLE_ROW,
                    lab_sample_mapping=sample.lab_mapping,
                    container_label="",
                    parameter=parameter.display_label,
                    display_number=display_counter,
                )

        if sample != samples[-1]:
            row_number += 1
            WorksheetRow.objects.create(
                worksheet=worksheet,
                row_number=row_number,
                row_type=WorksheetRow.BLANK_ROW,
            )

    return worksheet


def generate_worksheets_for_submission(submission, generated_by):
    ensure_lab_sample_ids(submission)

    groups = _group_samples_by_worksheet_type(submission)
    worksheets = []

    if Worksheet.MINERAL_ANALYSIS in groups:
        worksheets.append(
            _build_mineral_analysis_worksheet(
                submission, groups[Worksheet.MINERAL_ANALYSIS], generated_by
            )
        )

    if Worksheet.CARBON_ACTIVITY in groups:
        worksheets.append(
            _build_carbon_activity_worksheet(
                submission, groups[Worksheet.CARBON_ACTIVITY], generated_by
            )
        )

    if Worksheet.CONVENTIONAL_CYANIDE_LEACHING in groups:
        worksheets.append(
            _build_cyanide_leaching_worksheet(
                submission,
                groups[Worksheet.CONVENTIONAL_CYANIDE_LEACHING],
                generated_by,
                Worksheet.CONVENTIONAL_CYANIDE_LEACHING,
                Service.CYANIDE_CONVENTIONAL,
            )
        )

    if Worksheet.PARAMETER_OPTIMIZATION in groups:
        worksheets.append(
            _build_cyanide_leaching_worksheet(
                submission,
                groups[Worksheet.PARAMETER_OPTIMIZATION],
                generated_by,
                Worksheet.PARAMETER_OPTIMIZATION,
                Service.CYANIDE_OPTIMIZATION,
            )
        )

    return worksheets
