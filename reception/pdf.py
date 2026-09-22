import base64
import os
from functools import lru_cache
from io import BytesIO

import qrcode
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont
from xhtml2pdf import pisa

STATIC_IMG = os.path.join(settings.BASE_DIR, "core", "static", "core", "img")

WATERMARK_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _qr_code_data_uri(url):
    try:
        qr = qrcode.QRCode(border=1, box_size=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#123f78", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return None


@lru_cache(maxsize=1)
def _watermark_data_uri(text="LGS MINERAL ASSAY LABORATORY", page_size=(1240, 1754)):
    try:
        font = None
        for path in WATERMARK_FONT_CANDIDATES:
            try:
                font = ImageFont.truetype(path, 34)
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()

        big_w, big_h = int(page_size[0] * 1.6), int(page_size[1] * 1.6)
        big = Image.new("RGBA", (big_w, big_h), (255, 255, 255, 0))
        draw = ImageDraw.Draw(big)

        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        x_gap, y_gap = tw + 90, th + 90
        y, row = -y_gap, 0
        while y < big_h + y_gap:
            x_offset = (x_gap / 2) if row % 2 else 0
            x = -x_gap + x_offset
            while x < big_w + x_gap:
                draw.text((x, y), text, font=font, fill=(18, 63, 120, 24))
                x += x_gap
            y += y_gap
            row += 1

        rotated = big.rotate(35, expand=True, resample=Image.BICUBIC)
        left = (rotated.width - page_size[0]) // 2
        top = (rotated.height - page_size[1]) // 2
        cropped = rotated.crop((left, top, left + page_size[0], top + page_size[1]))

        buf = BytesIO()
        cropped.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return None


def render_client_submission_form_pdf(context):
    context = {
        **context,
        "logo_path": os.path.join(STATIC_IMG, "lgs-logo.png"),
        "qr_code": _qr_code_data_uri(
            context.get("site_url") or "https://audowrld.pythonanywhere.com/"
        ),
        "watermark": _watermark_data_uri(),
    }

    html_string = render_to_string(
        "reception/pdf/client_submission_form_pdf.html", context
    )

    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html_string.encode("UTF-8")), result)

    if pdf.err:
        raise ValueError(f"PDF generation failed with {pdf.err} error(s).")

    return result.getvalue()


def render_worksheet_pdf(context):
    # Prefer the actual worksheet creation time from the DB (Worksheet.generated_at)
    # so reprinting later still shows when it was first generated, not "now".
    worksheets = context.get("worksheets") or []
    first_generated_at = None
    for ws in worksheets:
        if ws.generated_at and (
            first_generated_at is None or ws.generated_at < first_generated_at
        ):
            first_generated_at = ws.generated_at

    if first_generated_at:
        generated_at_display = timezone.localtime(first_generated_at).strftime(
            "%d %b %Y, %H:%M"
        )
    else:
        # No worksheets yet (nothing generated) — fall back to "now" so the
        # header doesn't show a blank/misleading date on an empty worksheet.
        generated_at_display = timezone.localtime().strftime("%d %b %Y, %H:%M")

    context = {
        **context,
        "logo_path": os.path.join(STATIC_IMG, "lgs-logo.png"),
        "generated_at": generated_at_display,
    }

    html_string = render_to_string("reception/pdf/worksheet_form.html", context)

    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html_string.encode("UTF-8")), result)

    if pdf.err:
        raise ValueError(f"PDF generation failed with {pdf.err} error(s).")

    return result.getvalue()


from worksheet.models import LabSampleMapping, Worksheet, WorksheetRow

REPLICATES_BY_SAMPLE_TYPE = {
    "ROCK": 2,
    "ROCK_PULP": 2,
    "SOIL": 3,
    "TAILINGS": 3,
    "CARBON": 4,
    "PROCESS_SOLUTION": 2,
}

MINERAL_SERVICES = {
    "GOLD_COPPER_ANALYSIS": {
        "elements": ["Au", "Cu"],
        "method": "Aqua Regia + AAS",
    },
    "GOLD_COPPER_SILVER_ANALYSIS": {
        "elements": ["Au", "Cu", "Ag"],
        "method": "Aqua Regia + AAS",
    },
    "GOLD_COPPER_SULPHUR_ANALYSIS": {
        "elements": ["Au", "Cu", "S"],
        "method": "Aqua Regia + AAS / Furnace Induction",
    },
    "GOLD_COPPER_SILVER_SULPHUR_ANALYSIS": {
        "elements": ["Au", "Cu", "Ag", "S"],
        "method": "Aqua Regia + AAS / Furnace Induction",
    },
}

CARBON_ACTIVITY_SERVICE = "CARBON_ACTIVITY_TEST"
CONVENTIONAL_CYANIDE_SERVICE = "CONVENTIONAL_CYANIDE_LEACHING_TEST"
PARAMETER_OPTIMIZATION_SERVICE = "CYANIDE_LEACHING_PARAMETER_OPTIMIZATION"

CONVENTIONAL_PARAMETERS = ["Ore", "Pulp Density", "Cyanide Dose", "Lime Dose"]
OPTIMIZATION_PARAMETERS = CONVENTIONAL_PARAMETERS + [
    "Lead Nitrate",
    "Ammonium Solution",
    "Caustic Soda",
    "Sodium Sulphide",
    "Hydrogen Peroxide",
    "Ammonium Nitrate Salt",
]

WORKSHEET_TYPE_BY_SERVICE = {
    **{code: Worksheet.MINERAL_ANALYSIS for code in MINERAL_SERVICES},
    CARBON_ACTIVITY_SERVICE: Worksheet.CARBON_ACTIVITY,
    CONVENTIONAL_CYANIDE_SERVICE: Worksheet.CONVENTIONAL_CYANIDE_LEACHING,
    PARAMETER_OPTIMIZATION_SERVICE: Worksheet.PARAMETER_OPTIMIZATION,
}


def _assign_lab_sample_ids(submission):
    mapping_by_sample = {}
    for sequence, sample in enumerate(submission.samples.order_by("id"), start=1):
        mapping = getattr(sample, "lab_mapping", None)
        if mapping is None:
            mapping = LabSampleMapping.generate_for_sample(sample, sequence)
        mapping_by_sample[sample.id] = mapping
    return mapping_by_sample


def _requested_services(submission):
    services = {}
    # Order matches _assign_lab_sample_ids so sample 1's rows are always on top.
    for sample in submission.samples.order_by("id"):
        for service in sample.requested_services.all():
            services.setdefault(service.code, []).append(sample)
    return services


def _mineral_rows(samples, mapping_by_sample):
    rows = []
    total = len(samples)
    for index, sample in enumerate(samples, start=1):
        mapping = mapping_by_sample[sample.id]
        replicate_count = REPLICATES_BY_SAMPLE_TYPE.get(sample.sample_type, 2)
        for replicate_number in range(1, replicate_count + 1):
            rows.append(
                {
                    "row_type": WorksheetRow.REPLICATE_ROW,
                    "lab_sample_mapping_id": mapping.id,
                    "replicate_number": replicate_number,
                }
            )
        if index < total:
            if index % 2 == 0:
                # Blank spacer, then CRM, then another blank spacer — CRM is
                # visually separated from both the sample above and below it.
                rows.append({"row_type": WorksheetRow.BLANK_ROW})
                rows.append({"row_type": WorksheetRow.CRM_ROW})
                rows.append({"row_type": WorksheetRow.BLANK_ROW})
            else:
                rows.append({"row_type": WorksheetRow.BLANK_ROW})
    return rows


def _carbon_activity_rows(samples, mapping_by_sample):
    rows = []
    for sample in samples:
        mapping = mapping_by_sample[sample.id]
        for replicate_number in (1, 2):
            rows.append(
                {
                    "row_type": WorksheetRow.REPLICATE_ROW,
                    "lab_sample_mapping_id": mapping.id,
                    "replicate_number": replicate_number,
                }
            )
    return rows


def _parameter_rows(samples, mapping_by_sample, parameters):
    rows = []
    for sample in samples:
        mapping = mapping_by_sample[sample.id]
        for parameter in parameters:
            rows.append(
                {
                    "row_type": WorksheetRow.SAMPLE_ROW,
                    "lab_sample_mapping_id": mapping.id,
                    "parameter": parameter,
                    "weight": getattr(sample, "weight", None),
                }
            )
    return rows


def generate_worksheets_for_submission(submission, user):
    mapping_by_sample = _assign_lab_sample_ids(submission)
    services = _requested_services(submission)

    created_worksheets = []
    for service_code, samples in services.items():
        worksheet_type = WORKSHEET_TYPE_BY_SERVICE.get(service_code)
        if worksheet_type is None:
            continue

        if worksheet_type == Worksheet.MINERAL_ANALYSIS:
            spec = MINERAL_SERVICES[service_code]
            elements = ",".join(spec["elements"])
            method = spec["method"]
            row_specs = _mineral_rows(samples, mapping_by_sample)
        elif worksheet_type == Worksheet.CARBON_ACTIVITY:
            elements = ""
            method = "Carbon Activity Test Method"
            row_specs = _carbon_activity_rows(samples, mapping_by_sample)
        elif worksheet_type == Worksheet.CONVENTIONAL_CYANIDE_LEACHING:
            elements = ""
            method = "Bottle Test + AAS"
            row_specs = _parameter_rows(
                samples, mapping_by_sample, CONVENTIONAL_PARAMETERS
            )
        else:
            elements = ""
            method = "Bottle Test + AAS"
            row_specs = _parameter_rows(
                samples, mapping_by_sample, OPTIMIZATION_PARAMETERS
            )

        worksheet = Worksheet.objects.create(
            submission=submission,
            worksheet_type=worksheet_type,
            elements=elements,
            method_of_analysis=method,
            generated_by=user,
        )

        rows = []
        display_counter = 0
        for row_number, spec in enumerate(row_specs, start=1):
            if spec.get("row_type") != WorksheetRow.BLANK_ROW:
                display_counter += 1
                spec = {**spec, "display_number": display_counter}
            rows.append(
                WorksheetRow(worksheet=worksheet, row_number=row_number, **spec)
            )
        WorksheetRow.objects.bulk_create(rows)
        created_worksheets.append(worksheet)

    return created_worksheets


def get_worksheets_for_display(submission):
    return submission.worksheets.order_by("id")
