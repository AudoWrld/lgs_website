import base64
import os
from functools import lru_cache
from io import BytesIO

import qrcode
from django.conf import settings
from django.template.loader import render_to_string
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
