import io
import os
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from xml.sax.saxutils import escape

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

PAGE_W, PAGE_H = landscape(A4)
MARGIN_X = 18 * mm
FRAME_TOP = 42 * mm
FRAME_BOTTOM = 35 * mm
LATER_FRAME_TOP = 48 * mm
FOOTER_BASE = 6 * mm

PX = 0.75
GAP = 10 * PX
CELL_PAD = 5

BLUE = colors.HexColor("#0B3C91")
COMPANY_BLUE = colors.HexColor("#1B3FD6")
PURPLE = colors.HexColor("#7A2E8E")
TITLE_ORANGE = colors.HexColor("#EB6A1A")
STAMP_INK = colors.HexColor("#5B3E9A")
STAMP_DATE_CX = 0.508
STAMP_DATE_CY = 0.539
STAMP_DATE_W = 0.455

COMPANY_NAME = "LGS AFRICAN GROUP COMPANY LIMITED"
ADDRESS_LINES = [
    "Karumwa \u2013 Sweya, Kahama Road, Njia Panda ya Mahagi, Nyang'hwale, Geita",
    "P.O. Box 1214, Mwanza, Tanzania",
    "Email: lgsafricansales2025@gmail.com",
    "Tel: +255 797 717 883   |   Website: www.lgsafrica.co.tz",
]

MINERAL_DISCLAIMER = (
    "This report applies only to the sample(s) received and tested by LGS African "
    "Group Company Limited. The results are valid for the submitted sample(s) only "
    "and may not be reproduced except in full without written permission from the "
    "laboratory."
)
METALLURGICAL_DISCLAIMER = (
    "This report presents the metallurgical test results obtained from the submitted "
    "sample under the stated test conditions. The results apply only to the sample "
    "tested and should not be reproduced except in full without written permission "
    "from the laboratory."
)


@dataclass
class Block:
    results_title: str
    detail_rows: list
    header: list
    rows: list
    metallurgical: bool = False
    bold_last_column: bool = False
    spans: list = field(default_factory=list)


@dataclass
class CoaDoc:
    coa_number: str
    client_name: str
    submitted_at: str
    issued_at: datetime
    nature_of_sample: str
    sample_count: int
    blocks: list = field(default_factory=list)
    verify_url: str = ""
    logo_path: str = ""
    signature_path: str = ""
    stamp_path: str = ""


def _style(name, **kw):
    base = dict(fontName="Helvetica", fontSize=10, leading=13)
    base.update(kw)
    return ParagraphStyle(name, **base)


@lru_cache(maxsize=8)
def _scaled_reader(path, max_width):
    from PIL import Image

    img = Image.open(path).convert("RGBA")
    if img.width > max_width:
        img = img.resize(
            (max_width, max(1, round(img.height * max_width / img.width))),
            Image.LANCZOS,
        )
    return ImageReader(img)


def _trim(img):
    box = img.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
    return img.crop(box) if box else img


@lru_cache(maxsize=4)
def _logo_rgba(path):
    from PIL import Image, ImageChops, ImageFilter

    img = Image.open(path).convert("RGBA")
    if img.width > 500:
        img = img.resize(
            (500, max(1, round(img.height * 500 / img.width))), Image.LANCZOS
        )
    if img.getchannel("A").getextrema()[0] < 250:
        return _trim(img)

    r, g, b = img.convert("RGB").split()
    top = ImageChops.lighter(ImageChops.lighter(r, g), b)
    low = ImageChops.darker(ImageChops.darker(r, g), b)
    chroma = ImageChops.subtract(top, low)
    bright = low.point(lambda v: 255 if v > 140 else 0)
    neutral = chroma.point(lambda v: 255 if v < 70 else 0)
    background = ImageChops.multiply(bright, neutral).filter(ImageFilter.MaxFilter(3))
    alpha = ImageChops.multiply(img.getchannel("A"), ImageChops.invert(background))
    img.putalpha(alpha)
    return _trim(img)


@lru_cache(maxsize=4)
def _logo_reader(path):
    try:
        return ImageReader(_logo_rgba(path))
    except Exception:
        return ImageReader(path)


@lru_cache(maxsize=4)
def _watermark_tile(path):
    from PIL import Image

    logo = _logo_rgba(path)
    width = 160
    small = logo.resize(
        (width, max(1, round(logo.height * width / logo.width))), Image.BILINEAR
    )
    scale = min(42 * mm / small.width, 23 * mm / small.height)
    tile = small.rotate(20, expand=True, resample=Image.BILINEAR)
    table = [int(v * 0.045) for v in range(256)]
    tile.putalpha(tile.getchannel("A").point(table))
    return ImageReader(tile), tile.width * scale, tile.height * scale


def _draw_qr(c, url, x, y, size):
    widget = qr.QrCodeWidget(url, barBorder=1)
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(
        size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0]
    )
    drawing.add(widget)
    renderPDF.draw(drawing, c, x, y)


def _draw_watermark(c, d):
    if not (d.logo_path and os.path.exists(d.logo_path)):
        return
    if not getattr(c, "_wm_ready", False):
        reader, w, h = _watermark_tile(d.logo_path)
        step_x, step_y = 62 * mm, 46 * mm
        c.beginForm("watermark")
        row = 0
        y = -10 * mm
        while y < PAGE_H + 20 * mm:
            x = -20 * mm + (step_x / 2 if row % 2 else 0)
            while x < PAGE_W + 20 * mm:
                c.drawImage(reader, x, y, width=w, height=h, mask="auto")
                x += step_x
            y += step_y
            row += 1
        c.endForm()
        c._wm_ready = True
    c.doForm("watermark")


def _draw_letterhead(c, d):
    right = PAGE_W - MARGIN_X
    if d.logo_path and os.path.exists(d.logo_path):
        c.drawImage(
            _logo_reader(d.logo_path),
            MARGIN_X,
            PAGE_H - 38.5 * mm,
            width=54 * mm,
            height=31 * mm,
            preserveAspectRatio=True,
            mask="auto",
            anchor="sw",
        )
    c.setFillColor(COMPANY_BLUE)
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(right, PAGE_H - 15 * mm, COMPANY_NAME)
    c.setFillColor(PURPLE)
    c.setFont("Helvetica", 8.5)
    y = PAGE_H - 21.5 * mm
    for line in ADDRESS_LINES:
        c.drawRightString(right, y, line)
        y -= 4.3 * mm
    c.setStrokeColor(COMPANY_BLUE)
    c.setLineWidth(0.9)
    c.line(MARGIN_X, PAGE_H - 40 * mm, right, PAGE_H - 40 * mm)


def _stamp_line(c, text, font, size, cx, y, max_w, color, char_space=0.0):
    natural = stringWidth(text, font, size) + char_space * len(text)
    scale = min(max(max_w / natural, 0.7), 1.1)
    width = natural * scale
    c.saveState()
    t = c.beginText()
    t.setFont(font, size)
    t.setFillColor(color)
    t.setCharSpace(char_space)
    t.setHorizScale(scale * 100)
    t.setTextOrigin(cx - width / 2, y)
    t.textOut(text)
    c.drawText(t)
    c.restoreState()


def draw_stamp(c, path, cx, y, width, issued_at):
    reader = _scaled_reader(path, 700)
    iw, ih = reader.getSize()
    height = width * ih / iw
    x = cx - width / 2
    c.drawImage(reader, x, y, width=width, height=height, mask="auto")
    text = issued_at.strftime("%d %b %Y").upper()
    _stamp_line(
        c,
        text,
        "Helvetica-Bold",
        13.5,
        x + width * STAMP_DATE_CX,
        y + height * (1 - STAMP_DATE_CY) - 13.5 * 0.34,
        width * STAMP_DATE_W,
        STAMP_INK,
        char_space=1.0,
    )


def _draw_continuation_page(c, page, total):
    if page > 1:
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(
            PAGE_W - MARGIN_X, PAGE_H - 45 * mm, f"PAGE: {page} of {total}"
        )


def _draw_footer(c, d):
    base = FOOTER_BASE
    sig_x = MARGIN_X + 4 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(sig_x + 8 * mm, base + 24 * mm, "Laboratory Manager")
    if d.signature_path and os.path.exists(d.signature_path):
        c.drawImage(
            _scaled_reader(d.signature_path, 500),
            sig_x + 8 * mm,
            base + 10.5 * mm,
            width=34 * mm,
            height=12.5 * mm,
            preserveAspectRatio=True,
            mask="auto",
            anchor="sw",
        )
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.setDash(1, 2)
    c.line(sig_x, base + 10 * mm, sig_x + 56 * mm, base + 10 * mm)
    c.setDash()

    if d.stamp_path and os.path.exists(d.stamp_path):
        draw_stamp(c, d.stamp_path, PAGE_W / 2, base + 2.5 * mm, 42 * mm, d.issued_at)

    if d.verify_url:
        size = 22 * mm
        right = PAGE_W - MARGIN_X
        label = "Scan to verify at LGS Portal"
        c.setFont("Helvetica", 8.5)
        label_w = stringWidth(label, "Helvetica", 8.5)
        center = right - label_w / 2
        _draw_qr(c, d.verify_url, center - size / 2, base + 4 * mm, size)
        c.setFillColor(colors.black)
        c.drawCentredString(center, base, label)


def _col_widths(ncols, width):
    if ncols == 1:
        return [width]
    if ncols == 2:
        return [width * 0.3, width * 0.7]
    if ncols == 3:
        return [width * 0.29, width * 0.35, width * 0.36]
    first = [width * 0.1, width * 0.18]
    rest = (width - sum(first)) / (ncols - 2)
    return first + [rest] * (ncols - 2)


def _table(block, width):
    ncols = len(block.header)
    size = 11 if ncols <= 5 else 9.5
    head_style = _style(
        "th",
        fontName="Helvetica-Bold",
        fontSize=size,
        leading=size + 2.5,
        alignment=TA_CENTER,
        textColor=colors.white,
    )
    body = _style("td", fontSize=11, leading=13, alignment=TA_CENTER)
    body_bold = _style(
        "tdb", fontName="Helvetica-Bold", fontSize=12, leading=14, alignment=TA_CENTER
    )

    data = [[Paragraph(escape(str(h)), head_style) for h in block.header]]
    for row in block.rows:
        cells = []
        for i, value in enumerate(row):
            bold = block.bold_last_column and i == ncols - 1
            cells.append(Paragraph(escape(str(value)), body_bold if bold else body))
        data.append(cells)

    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#333333")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), CELL_PAD),
        ("BOTTOMPADDING", (0, 0), (-1, -1), CELL_PAD),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for col, start, end in block.spans:
        commands.append(("SPAN", (col, start + 1), (col, end + 1)))

    t = Table(data, colWidths=_col_widths(ncols, width), repeatRows=1)
    t.setStyle(TableStyle(commands))
    return t


def _detail_table(rows, width):
    label = _style("dl", fontName="Helvetica-Bold", fontSize=10.5, leading=13)
    value = _style("dv", fontSize=10.5, leading=13, textColor=PURPLE)
    data = [[Paragraph(escape(a), label), Paragraph(escape(b), value)] for a, b in rows]
    t = Table(data, colWidths=[55 * mm, width - 55 * mm])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return t


def _story(d, pages_total):
    width = PAGE_W - 2 * MARGIN_X
    purple = "#7A2E8E"
    story = [NextPageTemplate("later")]

    title = _style(
        "title",
        fontName="Times-Bold",
        fontSize=21,
        leading=24,
        alignment=TA_CENTER,
        textColor=TITLE_ORANGE,
    )
    story.append(Paragraph("CERTIFICATE OF ANALYSIS", title))
    story.append(Spacer(1, GAP))

    left = Paragraph(
        f"TO: {escape(d.client_name.upper())}", _style("to", fontSize=12, leading=15)
    )
    meta_lines = [
        ("REFERENCE NO.:", d.coa_number),
        ("SAMPLE SUBMISSION DATE:", d.submitted_at),
        ("COA ISSUED DATE:", d.issued_at.strftime("%Y-%m-%d %H:%M:%S")),
        ("PAGE:", f"1 of {pages_total}"),
    ]
    right_html = "<br/>".join(
        (
            f"<b>{a}</b> <font color='{purple}'>{escape(b)}</font>"
            if a != "PAGE:"
            else f"<b>{a}</b> {escape(b)}"
        )
        for a, b in meta_lines
    )
    right = Paragraph(right_html, _style("meta", fontSize=10, leading=14, alignment=2))
    meta = Table([[left, right]], colWidths=[width * 0.5, width * 0.5])
    meta.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(meta)
    story.append(Spacer(1, GAP))

    heading = _style("h", fontName="Helvetica-Bold", fontSize=13, leading=15)
    story.append(Paragraph("SAMPLE DETAILS:", heading))
    story.append(Spacer(1, 3))

    details = [
        ("Nature of Sample:", d.nature_of_sample),
        ("Number of Samples:", str(d.sample_count)),
    ]
    if d.blocks:
        details += list(d.blocks[0].detail_rows)
    story.append(_detail_table(details, width))

    groups = []
    for index, block in enumerate(d.blocks):
        group = []
        if index > 0:
            group.append(Spacer(1, GAP * 2))
            group.append(_detail_table(block.detail_rows, width))
        group += [
            Spacer(1, GAP),
            Paragraph(block.results_title, heading),
            Spacer(1, 5),
            _table(block, width),
        ]
        groups.append(group)

    only_met = bool(d.blocks) and all(b.metallurgical for b in d.blocks)
    text = METALLURGICAL_DISCLAIMER if only_met else MINERAL_DISCLAIMER
    disclaimer = [
        Spacer(1, GAP),
        Paragraph(
            f"<b>Disclaimer:</b> <font color='{purple}'>{text}</font>",
            _style("disc", fontSize=8.5, leading=10.5),
        ),
    ]
    if groups:
        groups[-1] += disclaimer
    else:
        story += disclaimer
    for group in groups:
        story.append(KeepTogether(group))
    return story


def _build(d, pages_total):
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=FRAME_TOP,
        bottomMargin=FRAME_BOTTOM,
        title=f"Certificate of Analysis {d.coa_number}",
        author="LGS African Group Company Limited",
    )

    def make_frame(top):
        return Frame(
            MARGIN_X,
            FRAME_BOTTOM,
            PAGE_W - 2 * MARGIN_X,
            PAGE_H - top - FRAME_BOTTOM,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )

    def on_page(c, _doc):
        _draw_watermark(c, d)
        _draw_letterhead(c, d)
        _draw_footer(c, d)
        _draw_continuation_page(c, _doc.page, pages_total)

    doc.addPageTemplates(
        [
            PageTemplate(id="first", frames=[make_frame(FRAME_TOP)], onPage=on_page),
            PageTemplate(
                id="later", frames=[make_frame(LATER_FRAME_TOP)], onPage=on_page
            ),
        ]
    )
    doc.build(_story(d, pages_total))
    return buf.getvalue(), doc.page


def render_coa_pdf(d):
    data, pages = _build(d, 1)
    if pages != 1:
        data, _ = _build(d, pages)
    return data


def render_coa_png(pdf_bytes, scale=1.6):
    import pypdfium2 as pdfium
    from PIL import Image

    pdf = pdfium.PdfDocument(pdf_bytes)
    pages = [
        pdf[i].render(scale=scale).to_pil().convert("RGB") for i in range(len(pdf))
    ]
    if len(pages) == 1:
        sheet = pages[0]
    else:
        sheet = Image.new(
            "RGB", (pages[0].width, sum(p.height for p in pages)), "white"
        )
        y = 0
        for page in pages:
            sheet.paste(page, (0, y))
            y += page.height
    out = io.BytesIO()
    sheet.save(out, format="PNG", compress_level=1)
    return out.getvalue()
