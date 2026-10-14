import io
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from xml.sax.saxutils import escape

from django.conf import settings
from django.contrib.staticfiles import finders
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from coa.pdf import (
    ADDRESS_FONT,
    ADDRESS_SIZE,
    BLUE,
    COMPANY_BLUE,
    PURPLE,
    _address_lines,
    _draw_company_name,
    _logo_reader,
)

PAGE_W, PAGE_H = A4
MARGIN_X = 15 * mm
FRAME_TOP = 44 * mm
FRAME_BOTTOM = 20 * mm
TOTAL_FILL = colors.HexColor("#EDEFF5")
SUMMARY_HEAD = colors.HexColor("#1F6F5C")
SUMMARY_FILL = colors.HexColor("#E3F1EC")
GRID = colors.HexColor("#333333")
CELL_PAD_X = 4
TABLE_FONT = "Helvetica"
TABLE_SIZE = 7.5


@dataclass
class Section:
    title: str
    header: list
    rows: list
    widths: list
    right: list = field(default_factory=list)
    truncate: list = field(default_factory=list)
    totals: Optional[list] = None
    empty: str = "No records for this period."


@dataclass
class ReportDoc:
    title: str
    short_title: str
    start: date
    end: date
    generated: datetime
    summary_heading: str = "Summary (TZS)"
    summary: list = field(default_factory=list)
    sections: list = field(default_factory=list)
    website: str = ""


def _style(name, **kw):
    base = dict(fontName="Helvetica", fontSize=8, leading=10)
    base.update(kw)
    return ParagraphStyle(name, **base)


def _static_path(relative):
    found = finders.find(relative)
    if found:
        return found
    root = getattr(settings, "STATIC_ROOT", None)
    return f"{root}/{relative}" if root else ""


def _fit(text, font, size, max_width):
    text = str(text)
    if stringWidth(text, font, size) <= max_width:
        return text
    ellipsis = "..."
    while text and stringWidth(text + ellipsis, font, size) > max_width:
        text = text[:-1]
    return text.rstrip() + ellipsis


def _draw_letterhead(c, logo_path, website=""):
    right = PAGE_W - MARGIN_X
    if logo_path and os.path.exists(logo_path):
        c.drawImage(
            _logo_reader(logo_path),
            MARGIN_X,
            PAGE_H - 36 * mm,
            width=44 * mm,
            height=26 * mm,
            preserveAspectRatio=True,
            mask="auto",
            anchor="sw",
        )
    _draw_company_name(c, right, PAGE_H - 16 * mm)
    c.setFillColor(PURPLE)
    c.setFont(ADDRESS_FONT, ADDRESS_SIZE)
    y = PAGE_H - 20.5 * mm
    for line in _address_lines(website):
        c.drawRightString(right, y, line)
        y -= 4.3 * mm
    c.setStrokeColor(COMPANY_BLUE)
    c.setLineWidth(0.9)
    c.line(MARGIN_X, PAGE_H - 38 * mm, right, PAGE_H - 38 * mm)


def _draw_footer(c, short_title, generated, page, total):
    c.setFillColor(GRID)
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawCentredString(
        PAGE_W / 2,
        14 * mm,
        f"LGS Mineral Assay Laboratory - Confidential {short_title}",
    )
    c.drawCentredString(
        PAGE_W / 2, 10.5 * mm, f"Generated on {generated:%d %b %Y %H:%M}"
    )
    c.drawCentredString(PAGE_W / 2, 7 * mm, f"Page {page}/{total}")


def _head_style():
    return _style(
        "th",
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        alignment=TA_CENTER,
        textColor=colors.white,
    )


def _base_commands(pad_y=3, head_color=BLUE):
    return [
        ("BACKGROUND", (0, 0), (-1, 0), head_color),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), pad_y),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad_y),
        ("LEFTPADDING", (0, 0), (-1, -1), CELL_PAD_X),
        ("RIGHTPADDING", (0, 0), (-1, -1), CELL_PAD_X),
    ]


def _table(section, width):
    left = _style("tl", fontSize=TABLE_SIZE, leading=9)
    right = _style("tr", fontSize=TABLE_SIZE, leading=9, alignment=TA_RIGHT)
    left_bold = _style("tlb", fontName="Helvetica-Bold", fontSize=TABLE_SIZE, leading=9)
    right_bold = _style(
        "trb",
        fontName="Helvetica-Bold",
        fontSize=TABLE_SIZE,
        leading=9,
        alignment=TA_RIGHT,
    )

    col_widths = [width * w for w in section.widths]
    head = _head_style()

    def cell(index, value):
        text = str(value)
        if index in section.truncate:
            text = _fit(
                text, TABLE_FONT, TABLE_SIZE, col_widths[index] - 2 * CELL_PAD_X - 1
            )
        return Paragraph(escape(text), right if index in section.right else left)

    data = [[Paragraph(escape(str(h)), head) for h in section.header]]
    for row in section.rows:
        data.append([cell(i, v) for i, v in enumerate(row)])
    if section.totals:
        data.append(
            [
                Paragraph(
                    escape(str(v)), right_bold if i in section.right else left_bold
                )
                for i, v in enumerate(section.totals)
            ]
        )

    commands = _base_commands()
    if section.totals:
        commands.append(
            ("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), TOTAL_FILL)
        )

    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle(commands))
    return t


def _summary_table(d, width):
    head = _head_style()
    label = _style("sl", fontSize=8.5, leading=11)
    label_bold = _style("slb", fontName="Helvetica-Bold", fontSize=8.5, leading=11)
    value = _style("sv", fontSize=8.5, leading=11, alignment=TA_RIGHT)
    value_bold = _style(
        "svb", fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=TA_RIGHT
    )

    data = [[Paragraph("Item", head), Paragraph("Value", head)]]
    bold_rows = []
    for index, (text, amount, bold) in enumerate(d.summary, start=1):
        data.append(
            [
                Paragraph(escape(text.rstrip(":")), label_bold if bold else label),
                Paragraph(escape(amount), value_bold if bold else value),
            ]
        )
        if bold:
            bold_rows.append(index)

    commands = _base_commands(pad_y=3, head_color=SUMMARY_HEAD)
    for index in bold_rows:
        commands.append(("BACKGROUND", (0, index), (-1, index), SUMMARY_FILL))

    t = Table(data, colWidths=[width * 0.7, width * 0.3])
    t.setStyle(TableStyle(commands))
    return t


def _story(d, pages_total):
    width = PAGE_W - 2 * MARGIN_X
    heading = _style("h", fontName="Helvetica-Bold", fontSize=10, leading=13)
    note = _style(
        "note", fontSize=8.5, leading=11, textColor=colors.HexColor("#5b666c")
    )

    story = [
        Paragraph(
            escape(d.title.upper()),
            _style(
                "title",
                fontName="Helvetica-Bold",
                fontSize=14,
                leading=17,
                alignment=TA_CENTER,
            ),
        ),
        Spacer(1, 12),
    ]

    meta = Table(
        [
            [
                Paragraph(
                    f"REPORT DATE: {d.generated:%d/%m/%Y}",
                    _style("m1", fontSize=9, leading=11),
                ),
                Paragraph(
                    f"PAGES: {pages_total}",
                    _style("m2", fontSize=9, leading=11, alignment=TA_RIGHT),
                ),
            ]
        ],
        colWidths=[width * 0.5, width * 0.5],
    )
    meta.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(meta)
    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            f"Reporting Period: {d.start:%d %b %Y} TO {d.end:%d %b %Y}",
            _style("period", fontName="Helvetica-Bold", fontSize=10, leading=13),
        )
    )

    if d.summary:
        story.append(Spacer(1, 12))
        story.append(Paragraph(escape(d.summary_heading), heading))
        story.append(Spacer(1, 4))
        story.append(_summary_table(d, width))

    for section in d.sections:
        story.append(CondPageBreak(35 * mm))
        story.append(Spacer(1, 14))
        story.append(Paragraph(escape(section.title), heading))
        story.append(Spacer(1, 4))
        if section.rows:
            story.append(_table(section, width))
        else:
            story.append(Paragraph(escape(section.empty), note))
    return story


def _build(d, pages_total):
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=FRAME_TOP,
        bottomMargin=FRAME_BOTTOM,
        title=f"{d.title} {d.start:%Y-%m-%d} to {d.end:%Y-%m-%d}",
        author="LGS MINERAL ASSAY LABORATORY",
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
    logo = _static_path("core/img/lgs-logo.png")

    def on_page(c, _doc):
        _draw_letterhead(c, logo, d.website)
        _draw_footer(c, d.short_title, d.generated, _doc.page, pages_total)

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])
    doc.build(_story(d, pages_total))
    return buf.getvalue(), doc.page


def render_report_pdf(d):
    data, pages = _build(d, 1)
    if pages != 1:
        data, _ = _build(d, pages)
    return data
