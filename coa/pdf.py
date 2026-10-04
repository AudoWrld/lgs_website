import io
import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

PAGE_W, PAGE_H = landscape(A4)
MARGIN_X = 18 * mm
FRAME_TOP = 43 * mm
FRAME_BOTTOM = 54 * mm

BLUE = colors.HexColor("#0B3C91")
COMPANY_BLUE = colors.HexColor("#1B3FD6")
PURPLE = colors.HexColor("#7A2E8E")
RED = colors.HexColor("#D4261C")
STAMP_BLUE = colors.HexColor("#1B2FD0")
STAMP_RED = colors.HexColor("#D01A1A")
SIGN_BLUE = colors.HexColor("#2A1FBF")

COMPANY_NAME = "LGS AFRICAN GROUP COMPANY LIMITED"
ADDRESS_LINES = [
    "Karumwa \u2013 Sweya, Kahama Road, Njia Panda ya Mahagi, Nyang'hwale, Geita",
    "P.O. Box 1214, Mwanza, Tanzania",
    "Email: lgsafricansales2025@gmail.com",
    "Tel: +255 797 717 883   |   Website: www.lgsafrica.co.tz",
]
STAMP_TOP_TEXT = "LGS AFRICAN GROUP CO. LTD"
STAMP_BOTTOM_TEXT = "NYANG'HWALE BRANCH"

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


def _style(name, **kw):
    base = dict(fontName="Helvetica", fontSize=10, leading=13)
    base.update(kw)
    return ParagraphStyle(name, **base)


def _draw_arc_text(c, text, cx, cy, radius, top, size):
    font = "Helvetica-Bold"
    total = sum(stringWidth(ch, font, size) for ch in text) / radius
    acc = 0.0
    c.setFont(font, size)
    for ch in text:
        w = stringWidth(ch, font, size)
        mid = (acc + w / 2) / radius
        if top:
            theta = math.pi / 2 + total / 2 - mid
            rot = math.degrees(theta) - 90
        else:
            theta = 3 * math.pi / 2 - total / 2 + mid
            rot = math.degrees(theta) + 90
        c.saveState()
        c.translate(cx + radius * math.cos(theta), cy + radius * math.sin(theta))
        c.rotate(rot)
        c.drawCentredString(0, 0, ch)
        c.restoreState()
        acc += w


def _draw_star(c, x, y, r):
    p = c.beginPath()
    for i in range(10):
        ang = math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        px, py = x + rad * math.cos(ang), y + rad * math.sin(ang)
        if i == 0:
            p.moveTo(px, py)
        else:
            p.lineTo(px, py)
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def draw_stamp(c, cx, cy, issued_at):
    c.saveState()
    c.setStrokeColor(STAMP_BLUE)
    c.setFillColor(STAMP_BLUE)
    c.setLineWidth(1.8)
    c.circle(cx, cy, 20 * mm, stroke=1, fill=0)
    c.setLineWidth(0.8)
    c.circle(cx, cy, 18.6 * mm, stroke=1, fill=0)
    _draw_arc_text(c, STAMP_TOP_TEXT, cx, cy, 14.2 * mm, True, 9)
    _draw_arc_text(c, STAMP_BOTTOM_TEXT, cx, cy, 16.6 * mm, False, 8.5)
    for sign in (-1, 1):
        ang = math.radians(-22 if sign == 1 else 202)
        _draw_star(
            c, cx + 15.6 * mm * math.cos(ang), cy + 15.6 * mm * math.sin(ang), 1.5 * mm
        )
    c.setFillColor(STAMP_RED)
    c.translate(cx, cy)
    c.rotate(10)
    c.setFont("Helvetica-Bold", 11.5)
    c.drawCentredString(0, -1.6 * mm, issued_at.strftime("%d %b %Y").upper())
    c.restoreState()


def _draw_signature_fallback(c, x, y):
    c.saveState()
    c.setStrokeColor(SIGN_BLUE)
    c.setLineWidth(1.1)
    p = c.beginPath()
    p.moveTo(x, y + 5 * mm)
    p.curveTo(x + 3 * mm, y + 9 * mm, x + 14 * mm, y + 8 * mm, x + 18 * mm, y + 5 * mm)
    p.curveTo(x + 22 * mm, y + 2 * mm, x + 9 * mm, y + 1 * mm, x + 9 * mm, y + 4 * mm)
    c.drawPath(p, stroke=1, fill=0)
    p = c.beginPath()
    p.moveTo(x + 17 * mm, y + 3.5 * mm)
    p.lineTo(x + 21.5 * mm, y + 16 * mm)
    p.lineTo(x + 24 * mm, y + 2.5 * mm)
    p.lineTo(x + 26 * mm, y + 9 * mm)
    p.lineTo(x + 28 * mm, y + 3.5 * mm)
    c.drawPath(p, stroke=1, fill=0)
    p = c.beginPath()
    p.moveTo(x + 19 * mm, y + 5 * mm)
    p.curveTo(x + 27 * mm, y + 8 * mm, x + 35 * mm, y + 3 * mm, x + 44 * mm, y + 6 * mm)
    c.drawPath(p, stroke=1, fill=0)
    c.restoreState()


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
    c.saveState()
    c.setFillAlpha(0.06)
    w, h = 42 * mm, 23 * mm
    step_x, step_y = 62 * mm, 46 * mm
    row = 0
    y = -10 * mm
    while y < PAGE_H + 20 * mm:
        x = -20 * mm + (step_x / 2 if row % 2 else 0)
        while x < PAGE_W + 20 * mm:
            c.saveState()
            c.translate(x + w / 2, y + h / 2)
            c.rotate(20)
            c.drawImage(
                d.logo_path,
                -w / 2,
                -h / 2,
                width=w,
                height=h,
                preserveAspectRatio=True,
                mask="auto",
            )
            c.restoreState()
            x += step_x
        y += step_y
        row += 1
    c.restoreState()


def _draw_letterhead(c, d):
    right = PAGE_W - MARGIN_X
    if d.logo_path and os.path.exists(d.logo_path):
        c.drawImage(
            d.logo_path,
            MARGIN_X,
            PAGE_H - 38 * mm,
            width=50 * mm,
            height=28 * mm,
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


def _draw_footer(c, d):
    base = 14 * mm
    sig_x = MARGIN_X + 4 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(sig_x + 8 * mm, base + 33 * mm, "Laboratory Manager")
    if d.signature_path and os.path.exists(d.signature_path):
        c.drawImage(
            d.signature_path,
            sig_x + 4 * mm,
            base + 14 * mm,
            width=44 * mm,
            height=17 * mm,
            preserveAspectRatio=True,
            mask="auto",
            anchor="sw",
        )
    else:
        _draw_signature_fallback(c, sig_x + 4 * mm, base + 14.5 * mm)
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.setDash(1, 2)
    c.line(sig_x, base + 12 * mm, sig_x + 62 * mm, base + 12 * mm)
    c.setDash()

    draw_stamp(c, PAGE_W / 2, base + 19 * mm, d.issued_at)

    if d.verify_url:
        size = 25 * mm
        right = PAGE_W - MARGIN_X
        label = "Scan to verify at LGS Portal"
        c.setFont("Helvetica", 8.5)
        label_w = stringWidth(label, "Helvetica", 8.5)
        center = right - label_w / 2
        _draw_qr(c, d.verify_url, center - size / 2, base + 5 * mm, size)
        c.setFillColor(colors.black)
        c.drawCentredString(center, base, label)


def _col_widths(ncols, width):
    if ncols == 1:
        return [width]
    if ncols == 2:
        return [width * 0.3, width * 0.7]
    if ncols == 3:
        return [width * 0.29, width * 0.35, width * 0.36]
    first = [width * 0.12, width * 0.2]
    rest = (width - sum(first)) / (ncols - 2)
    return first + [rest] * (ncols - 2)


def _table(block, width):
    ncols = len(block.header)
    head_style = _style(
        "th",
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=13.5,
        alignment=TA_CENTER,
        textColor=colors.white,
    )
    body = _style("td", fontSize=11, leading=13.5, alignment=TA_CENTER)
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

    t = Table(data, colWidths=_col_widths(ncols, width), repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#333333")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def _detail_table(rows, width):
    label = _style("dl", fontName="Helvetica-Bold", fontSize=10.5, leading=14)
    value = _style("dv", fontSize=10.5, leading=14, textColor=PURPLE)
    data = [[Paragraph(escape(a), label), Paragraph(escape(b), value)] for a, b in rows]
    t = Table(data, colWidths=[55 * mm, width - 55 * mm])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return t


def _story(d, pages_total):
    width = PAGE_W - 2 * MARGIN_X
    purple = "#7A2E8E"
    story = []

    title = _style(
        "title",
        fontName="Times-Bold",
        fontSize=22,
        leading=26,
        alignment=TA_CENTER,
        textColor=RED,
    )
    story.append(Paragraph("CERTIFICATE OF ANALYSIS", title))
    story.append(Spacer(1, 4 * mm))

    left = Paragraph(
        f"TO: {escape(d.client_name.upper())}", _style("to", fontSize=12, leading=15)
    )
    meta_lines = [
        ("REFERENCE NO.:", d.coa_number),
        ("SAMPLE SUBMISSION DATE:", d.submitted_at),
        ("REPORT ISSUED DATE:", d.issued_at.strftime("%Y-%m-%d %H:%M:%S")),
        ("PAGES:", str(pages_total)),
    ]
    right_html = "<br/>".join(
        (
            f"<b>{a}</b> <font color='{purple}'>{escape(b)}</font>"
            if a != "PAGES:"
            else f"<b>{a}</b> {b}"
        )
        for a, b in meta_lines
    )
    right = Paragraph(
        right_html, _style("meta", fontSize=10, leading=13.5, alignment=2)
    )
    meta = Table([[left, right]], colWidths=[width * 0.5, width * 0.5])
    meta.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(meta)
    story.append(Spacer(1, 3 * mm))

    heading = _style("h", fontName="Helvetica-Bold", fontSize=13, leading=16)
    story.append(Paragraph("SAMPLE DETAILS:", heading))
    story.append(Spacer(1, 1 * mm))

    details = [
        ("Nature of Sample:", d.nature_of_sample),
        ("Number of Samples:", str(d.sample_count)),
    ]
    if d.blocks:
        details += list(d.blocks[0].detail_rows)
    story.append(_detail_table(details, width))

    for index, block in enumerate(d.blocks):
        if index > 0:
            story.append(Spacer(1, 3 * mm))
            story.append(_detail_table(block.detail_rows, width))
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(block.results_title, heading))
        story.append(Spacer(1, 1.5 * mm))
        story.append(_table(block, width))

    only_met = bool(d.blocks) and all(b.metallurgical for b in d.blocks)
    text = METALLURGICAL_DISCLAIMER if only_met else MINERAL_DISCLAIMER
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            f"<b>Disclaimer:</b> <font color='{purple}'>{text}</font>",
            _style("disc", fontSize=9.5, leading=12.5),
        )
    )
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
    frame = Frame(
        MARGIN_X,
        FRAME_BOTTOM,
        PAGE_W - 2 * MARGIN_X,
        PAGE_H - FRAME_TOP - FRAME_BOTTOM,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )

    def on_page(c, _doc):
        _draw_watermark(c, d)
        _draw_letterhead(c, d)
        _draw_footer(c, d)

    doc.addPageTemplates([PageTemplate(id="coa", frames=[frame], onPage=on_page)])
    doc.build(_story(d, pages_total))
    return buf.getvalue(), doc.page


def render_coa_pdf(d):
    _, pages = _build(d, 0)
    data, _ = _build(d, pages)
    return data


def render_coa_png(pdf_bytes, scale=2.5):
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
    sheet.save(out, format="PNG", optimize=True)
    return out.getvalue()
