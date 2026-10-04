import io
import math
import os
from dataclasses import dataclass, field
from datetime import datetime

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
PURPLE = colors.HexColor("#7A2E8E")
RED = colors.HexColor("#D4261C")
STAMP_BLUE = colors.HexColor("#1B2FD0")
STAMP_RED = colors.HexColor("#D01A1A")

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


def _draw_arc_text(c, text, cx, cy, radius, top):
    total = sum(stringWidth(ch, "Helvetica-Bold", 7) for ch in text) / radius
    acc = 0.0
    c.setFont("Helvetica-Bold", 7)
    for ch in text:
        w = stringWidth(ch, "Helvetica-Bold", 7)
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


def draw_stamp(c, cx, cy, issued_at):
    c.saveState()
    c.setStrokeColor(STAMP_BLUE)
    c.setFillColor(STAMP_BLUE)
    c.setLineWidth(1.6)
    c.circle(cx, cy, 20 * mm, stroke=1, fill=0)
    c.setLineWidth(0.7)
    c.circle(cx, cy, 18.4 * mm, stroke=1, fill=0)
    c.circle(cx, cy, 11.6 * mm, stroke=1, fill=0)
    _draw_arc_text(c, STAMP_TOP_TEXT, cx, cy, 13.2 * mm, top=True)
    _draw_arc_text(c, STAMP_BOTTOM_TEXT, cx, cy, 17.4 * mm, top=False)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(cx - 15.6 * mm, cy - 1.2 * mm, "*")
    c.drawCentredString(cx + 15.6 * mm, cy - 1.2 * mm, "*")
    c.setFillColor(STAMP_RED)
    c.translate(cx, cy)
    c.rotate(8)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawCentredString(0, -1.4 * mm, issued_at.strftime("%d %b %Y").upper())
    c.restoreState()


def _draw_qr(c, url, x, y, size):
    widget = qr.QrCodeWidget(url)
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(
        size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0]
    )
    drawing.add(widget)
    renderPDF.draw(drawing, c, x, y)


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
    c.setFillColor(BLUE)
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(right, PAGE_H - 15 * mm, COMPANY_NAME)
    c.setFillColor(PURPLE)
    c.setFont("Helvetica", 8.5)
    y = PAGE_H - 21.5 * mm
    for line in ADDRESS_LINES:
        c.drawRightString(right, y, line)
        y -= 4.3 * mm
    c.setStrokeColor(BLUE)
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
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.setDash(1, 2)
    c.line(sig_x, base + 12 * mm, sig_x + 62 * mm, base + 12 * mm)
    c.setDash()

    draw_stamp(c, PAGE_W / 2, base + 19 * mm, d.issued_at)

    if d.verify_url:
        size = 27 * mm
        right = PAGE_W - MARGIN_X
        _draw_qr(c, d.verify_url, right - size, base + 4 * mm, size)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8.5)
        c.drawRightString(right, base - 1 * mm, "Scan to verify at LGS Portal")


def _table(block, width):
    ncols = len(block.header)
    first = [16 * mm, 52 * mm]
    rest = (width - sum(first[: min(2, ncols)])) / max(ncols - 2, 1)
    col_widths = (first + [rest] * (ncols - 2))[:ncols]

    head_style = _style(
        "th",
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        alignment=TA_CENTER,
        textColor=colors.white,
    )
    data = [[Paragraph(h, head_style) for h in block.header]] + block.rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#444444")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 10.5),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def _detail_table(rows, width):
    label = _style("dl", fontName="Helvetica-Bold", fontSize=10.5, leading=14)
    value = _style("dv", fontSize=10.5, leading=14, textColor=PURPLE)
    data = [[Paragraph(a, label), Paragraph(b, value)] for a, b in rows]
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
        f"TO: {d.client_name.upper()}", _style("to", fontSize=12, leading=15)
    )
    meta_lines = [
        ("REFERENCE NO.:", d.coa_number),
        ("SAMPLE SUBMISSION DATE:", d.submitted_at),
        ("REPORT ISSUED DATE:", d.issued_at.strftime("%Y-%m-%d %H:%M:%S")),
        ("PAGES:", str(pages_total)),
    ]
    right_html = "<br/>".join(
        (
            f"<b>{a}</b> <font color='{purple}'>{b}</font>"
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
    story.append(
        _detail_table(
            [
                ("Nature of Sample:", d.nature_of_sample),
                ("Number of Samples:", str(d.sample_count)),
            ],
            width,
        )
    )

    for block in d.blocks:
        story.append(Spacer(1, 2 * mm))
        story.append(_detail_table(block.detail_rows, width))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(block.results_title, heading))
        story.append(Spacer(1, 1.5 * mm))
        story.append(_table(block, width))

    only_met = all(b.metallurgical for b in d.blocks)
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
