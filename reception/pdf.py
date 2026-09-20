import os

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa


def render_client_submission_form_pdf(context):
    logo_path = os.path.join(
        settings.BASE_DIR, "core", "static", "core", "img", "lgs-logo.png"
    )
    context = {
        **context,
        "logo_path": logo_path,
        "generated_at": timezone.now(),
    }

    html_string = render_to_string(
        "reception/pdf/client_submission_form_pdf.html", context
    )

    from io import BytesIO

    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html_string.encode("UTF-8")), result)

    if pdf.err:
        raise ValueError(f"PDF generation failed with {pdf.err} error(s).")

    return result.getvalue()
