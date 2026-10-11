from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#123e5b")
MUTED = colors.HexColor("#6b7680")
GRID = colors.HexColor("#4a5560")
SOFT = colors.HexColor("#faf8f3")
MARGIN = 15 * mm
CONTENT_WIDTH = A4[0] - 2 * MARGIN
FOOTER_TEXT = "LGS AFRICAN GROUP COMPANY LIMITED"


def money(value):
    return f"{value:,.2f}"


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_pages = []

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total):
        self.setFont("Helvetica", 8)
        self.setFillColor(MUTED)
        self.drawString(MARGIN, 10 * mm, FOOTER_TEXT)
        self.drawRightString(
            A4[0] - MARGIN, 10 * mm, f"Page {self._pageNumber} of {total}"
        )


def _styles():
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=12)
    cell = ParagraphStyle("cell", parent=base, fontSize=8, leading=10)
    return {
        "base": base,
        "company": ParagraphStyle(
            "company",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            alignment=TA_RIGHT,
        ),
        "title": ParagraphStyle(
            "title",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=22,
            alignment=TA_CENTER,
        ),
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
        "cell_bold": ParagraphStyle("cell_bold", parent=cell, fontName="Helvetica-Bold"),
        "cell_bold_right": ParagraphStyle(
            "cell_bold_right",
            parent=cell,
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
        ),
        "head": ParagraphStyle(
            "head",
            parent=cell,
            fontName="Helvetica-Bold",
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
        "muted": ParagraphStyle("muted", parent=base, textColor=MUTED),
    }


def _logo(path):
    if not path:
        return ""
    try:
        width, height = ImageReader(path).getSize()
        target_height = 20 * mm
        target_width = target_height * width / height
        if target_width > 50 * mm:
            target_width = 50 * mm
            target_height = target_width * height / width
        return Image(path, width=target_width, height=target_height, hAlign="LEFT")
    except Exception:
        return ""


def _header(styles, company, logo_path):
    table = Table(
        [[_logo(logo_path), Paragraph(escape(company), styles["company"])]],
        colWidths=[55 * mm, CONTENT_WIDTH - 55 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return [
        table,
        HRFlowable(
            width="100%",
            thickness=1.2,
            color=colors.black,
            spaceBefore=6,
            spaceAfter=12,
        ),
    ]


def _category_table(categories, styles):
    cells = [
        Paragraph(
            f"{escape(c['label'].upper())} - {money(c['amount'])} ({c['percent']}%)",
            styles["base"],
        )
        for c in categories
    ]
    if len(cells) % 2:
        cells.append("")
    rows = [cells[i : i + 2] for i in range(0, len(cells), 2)]
    table = Table(rows, colWidths=[CONTENT_WIDTH / 2] * 2, hAlign="LEFT")
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
    table = Table(
        [
            [
                Paragraph("Total Expenditure:", styles["base"]),
                Paragraph(f"<b>TZS {money(total)}</b>", styles["base"]),
            ]
        ],
        colWidths=[CONTENT_WIDTH / 2, CONTENT_WIDTH / 2],
    )
    table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _payments_table(methods, total, styles):
    cells = [(m["label"], m["amount"]) for m in methods]
    while len(cells) % 3 != 2:
        cells.append(("", None))
    cells.append(("Paid Total:", total))

    rows = []
    for i in range(0, len(cells), 3):
        row = []
        for label, amount in cells[i : i + 3]:
            row.append(Paragraph(f"{escape(label)}" if label else "", styles["base"]))
            row.append(
                Paragraph(money(amount), styles["cell_right"]) if amount is not None else ""
            )
        rows.append(row)

    table = Table(rows, colWidths=[22 * mm, 38 * mm] * 3, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (1, 0), (1, -1), 14),
                ("RIGHTPADDING", (3, 0), (3, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _records_table(rows, total, styles):
    widths = [20 * mm, 50 * mm, 36 * mm, 20 * mm, 26 * mm, 28 * mm]
    header = [
        Paragraph(text, styles["head"])
        for text in ("Date", "Description", "Category", "Payment", "Amount (TZS)", "Reference")
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
    data.append(
        [
            Paragraph("TOTAL", styles["cell_bold"]),
            "",
            "",
            "",
            Paragraph(money(total), styles["cell_bold_right"]),
            "",
        ]
    )

    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("VALIGN", (0, 1), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("BACKGROUND", (0, -1), (-1, -1), SOFT),
                ("SPAN", (0, -1), (3, -1)),
            ]
        )
    )
    return table


def render_expense_pdf(data, start, end, printed, company, logo_path):
    styles = _styles()
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=12 * mm,
        bottomMargin=18 * mm,
        title=f"Expense Report {start:%d %b %Y} to {end:%d %b %Y}",
        author=company,
    )
    frame = Frame(
        MARGIN,
        18 * mm,
        CONTENT_WIDTH,
        A4[1] - 30 * mm,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="body",
    )
    doc.addPageTemplates([PageTemplate(id="report", frames=[frame])])

    story = _header(styles, company, logo_path)
    story.append(Paragraph("EXPENSE REPORT", styles["title"]))
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            f"Report Period: {start:%d %b %Y} TO {end:%d %b %Y}", styles["base"]
        )
    )
    story.append(Paragraph(f"Printed: {printed:%d/%m/%Y %H:%M}", styles["base"]))

    story.append(Paragraph("Summary", styles["heading"]))
    if data["categories"]:
        story.append(_category_table(data["categories"], styles))
    story.append(_total_table(data["total"], styles))

    story.append(Paragraph("Payments (TZS)", styles["heading"]))
    story.append(_payments_table(data["methods"], data["total"], styles))
    story.append(Spacer(1, 10))

    if data["rows"]:
        story.append(_records_table(data["rows"], data["total"], styles))
    else:
        story.append(
            Paragraph("No expenses were recorded for this period.", styles["muted"])
        )

    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()