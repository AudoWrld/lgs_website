from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#123e5b")
ORANGE = colors.HexColor("#f39a2b")
CHARCOAL = colors.HexColor("#20272b")
MUTED = colors.HexColor("#5b666c")

MARGIN = 10 * mm
CONTENT_WIDTH = A4[0] - 2 * MARGIN
HEADER_HEIGHT = 50 * mm
FOOTER_HEIGHT = 22 * mm
LOGO_BOX = (60 * mm, 18 * mm)
SUMMARY_FONT = ("Helvetica", 9)


def money(value):
    return f"{value:,.2f}"


def _clock(moment):
    return f"{moment.hour % 12 or 12}:{moment:%M} {moment:%p}"


def _logo_geometry(path):
    if not path:
        return None
    try:
        width, height = ImageReader(path).getSize()
    except Exception:
        return None
    scale = min(LOGO_BOX[0] / width, LOGO_BOX[1] / height)
    return path, width * scale, height * scale


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, meta, **kwargs):
        super().__init__(*args, **kwargs)
        self._meta = meta
        self._logo = _logo_geometry(meta["logo_path"])
        self._saved_pages = []

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self._draw_header()
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_header(self):
        top = A4[1]
        right = A4[0] - MARGIN
        meta = self._meta

        if self._logo:
            path, width, height = self._logo
            try:
                self.drawImage(
                    path,
                    MARGIN,
                    top - 10 * mm - height,
                    width=width,
                    height=height,
                    mask="auto",
                )
            except Exception:
                pass

        self.setFillColor(CHARCOAL)
        self.setFont("Helvetica-Bold", 15)
        self.drawRightString(right, top - 14 * mm, meta["company"])
        self.setFont("Helvetica", 9)
        y = top - 19.5 * mm
        for line in meta["contact_lines"]:
            self.drawRightString(right, y, line)
            y -= 4.5 * mm

        self.setStrokeColor(NAVY)
        self.setLineWidth(1.2)
        self.line(MARGIN, top - 34 * mm, right, top - 34 * mm)

        self.setFillColor(CHARCOAL)
        self.setFont("Helvetica-Bold", 17)
        self.drawCentredString(A4[0] / 2, top - 43 * mm, "EXPENSE REPORT")

    def _draw_footer(self, total):
        meta = self._meta
        self.setFont("Helvetica-Oblique", 8.5)
        self.setFillColor(MUTED)
        center = A4[0] / 2
        self.drawCentredString(center, 14 * mm, f"Confidential - {meta['company']}")
        self.drawCentredString(center, 9.5 * mm, f"Generated on {meta['generated']}")
        self.drawCentredString(center, 5 * mm, f"Page {self._pageNumber}/{total}")


def _styles():
    base = ParagraphStyle(
        "base", fontName="Helvetica", fontSize=9, leading=12, textColor=CHARCOAL
    )
    cell = ParagraphStyle("cell", parent=base, fontSize=8, leading=10)
    return {
        "base": base,
        "base_right": ParagraphStyle("base_right", parent=base, alignment=TA_RIGHT),
        "heading": ParagraphStyle(
            "heading",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            spaceBefore=12,
            spaceAfter=5,
        ),
        "cell": cell,
        "cell_right": ParagraphStyle("cell_right", parent=cell, alignment=TA_RIGHT),
        "head": ParagraphStyle(
            "head",
            parent=cell,
            fontName="Helvetica-Bold",
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
        "muted": ParagraphStyle("muted", parent=base, textColor=MUTED),
    }


def _summary_line(category, width):
    suffix = f" - {money(category['amount'])} ({category['percent']}%)"
    label = category["label"].upper()
    font, size = SUMMARY_FONT
    if stringWidth(label + suffix, font, size) <= width:
        return label + suffix
    while label and stringWidth(label + "..." + suffix, font, size) > width:
        label = label[:-1]
    return label.rstrip() + "..." + suffix


def _category_table(categories, styles):
    column = CONTENT_WIDTH / 2
    cells = [
        Paragraph(escape(_summary_line(c, column - 8)), styles["base"])
        for c in categories
    ]
    if len(cells) % 2:
        cells.append("")
    rows = [cells[i : i + 2] for i in range(0, len(cells), 2)]
    table = Table(rows, colWidths=[column] * 2, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _total_table(total, styles):
    column = CONTENT_WIDTH / 2
    table = Table(
        [
            [
                Paragraph("Total Expenditure:", styles["base"]),
                Paragraph(money(total), styles["base"]),
            ]
        ],
        colWidths=[column, column],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("LEFTPADDING", (1, 0), (1, -1), 14 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _payments_table(methods, total, styles):
    cells = [(f"{m['label']}:", m["amount"]) for m in methods]
    while len(cells) % 3 != 2:
        cells.append(("", None))
    cells.append(("Paid Total:", total))

    rows = []
    for i in range(0, len(cells), 3):
        row = []
        for label, amount in cells[i : i + 3]:
            row.append(Paragraph(escape(label), styles["base"]) if label else "")
            row.append(
                Paragraph(money(amount), styles["base_right"])
                if amount is not None
                else ""
            )
        rows.append(row)

    pair = CONTENT_WIDTH / 3
    label_width = 22 * mm
    table = Table(
        rows,
        colWidths=[label_width, pair - label_width] * 3,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (1, 0), (1, -1), 8),
                ("RIGHTPADDING", (3, 0), (3, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _records_table(rows, styles):
    widths = [16 * mm, 46 * mm, 54 * mm, 22 * mm, 24 * mm, 28 * mm]
    header = [
        Paragraph(text, styles["head"])
        for text in (
            "Date",
            "Description",
            "Category",
            "Payment",
            "Amount",
            "Reference",
        )
    ]
    data = [header]
    for row in rows:
        data.append(
            [
                Paragraph(row["date"].strftime("%d/%m/%y"), styles["cell"]),
                Paragraph(escape(row["description"]), styles["cell"]),
                Paragraph(escape(row["category"].upper()), styles["cell"]),
                Paragraph(escape(row["payment"]), styles["cell"]),
                Paragraph(money(row["amount"]), styles["cell_right"]),
                Paragraph(escape(row["reference"] or "-"), styles["cell"]),
            ]
        )

    table = Table(data, colWidths=widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("VALIGN", (0, 1), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, CHARCOAL),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, ORANGE),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def render_expense_pdf(
    data,
    start,
    end,
    printed,
    company,
    logo_path,
    contact_lines=(),
):
    styles = _styles()
    buffer = BytesIO()
    meta = {
        "company": company,
        "logo_path": logo_path,
        "contact_lines": tuple(contact_lines),
        "generated": f"{printed:%d %b %Y} {_clock(printed)}",
    }
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=HEADER_HEIGHT,
        bottomMargin=FOOTER_HEIGHT,
        title=f"Expense Report {start:%d %b %Y} to {end:%d %b %Y}",
        author=company,
    )
    frame = Frame(
        MARGIN,
        FOOTER_HEIGHT,
        CONTENT_WIDTH,
        A4[1] - HEADER_HEIGHT - FOOTER_HEIGHT,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="body",
    )
    doc.addPageTemplates([PageTemplate(id="report", frames=[frame])])

    story = [
        Spacer(1, 4),
        Paragraph(f"Report Period: {start:%d %b %Y} TO {end:%d %b %Y}", styles["base"]),
        Paragraph(f"Printed: {printed:%d/%m/%Y} {_clock(printed)}", styles["base"]),
        Paragraph("Summary", styles["heading"]),
    ]
    if data["categories"]:
        story.append(_category_table(data["categories"], styles))
    story.append(_total_table(data["total"], styles))

    story.append(Paragraph("Payments (TZS)", styles["heading"]))
    story.append(_payments_table(data["methods"], data["total"], styles))
    story.append(Spacer(1, 12))

    if data["rows"]:
        story.append(_records_table(data["rows"], styles))
    else:
        story.append(
            Paragraph("No expenses were recorded for this period.", styles["muted"])
        )

    doc.build(
        story,
        canvasmaker=lambda *args, **kwargs: NumberedCanvas(*args, meta=meta, **kwargs),
    )
    return buffer.getvalue()
