from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
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

LAB_NAME = "LGS MINERAL ASSAY LABORATORY"
LAB_NAME_TITLE_CASE = "LGS Mineral Assay Laboratory"

BLACK = colors.black
INK = colors.HexColor("#222222")
GREY = colors.HexColor("#555555")
HEADER_BG = colors.HexColor("#DCE3EA")
TOTAL_BG = colors.HexColor("#EEF1F4")
STRIPE_BG = colors.HexColor("#F8F9FA")

MARGIN = 15 * mm
CONTENT_WIDTH = A4[0] - 2 * MARGIN
FIRST_TOP = 78 * mm
LATER_TOP = 52 * mm
FOOTER_HEIGHT = 20 * mm
LOGO_BOX = (46 * mm, 24 * mm)
CONTACT_KEYS = ("tel", "phone", "email", "@", "web", "www")


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


def _split_contacts(lines):
    left = [line for line in lines if any(k in line.lower() for k in CONTACT_KEYS)]
    right = [line for line in lines if line not in left]
    if not right and len(left) > 2:
        half = (len(left) + 1) // 2
        left, right = left[:half], left[half:]
    return left, right


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
        center = A4[0] / 2
        meta = self._meta

        if self._logo:
            path, width, height = self._logo
            try:
                self.drawImage(
                    path,
                    center - width / 2,
                    top - 8 * mm - height,
                    width=width,
                    height=height,
                    mask="auto",
                )
            except Exception:
                pass

        y = top - 37 * mm
        name = meta["company"]
        size = 13
        while stringWidth(name, "Times-Bold", size) > CONTENT_WIDTH and size > 8:
            size -= 0.5
        self.setFillColor(BLACK)
        self.setFont("Times-Bold", size)
        self.drawCentredString(center, y, name)
        y -= 6 * mm

        if self._pageNumber != 1:
            return

        left_lines, right_lines = _split_contacts(meta["contact_lines"])
        y -= 3 * mm
        self.setFont("Times-Bold", 9.5)
        line_y = y
        for line in left_lines:
            self.drawString(MARGIN, line_y, line)
            line_y -= 4.4 * mm
        line_y = y
        for line in right_lines:
            self.drawRightString(right, line_y, line)
            line_y -= 4.4 * mm
        y -= 4.4 * mm * max(len(left_lines), len(right_lines), 1)

        self.setFont("Times-Bold", 11)
        self.drawCentredString(center, y - 2 * mm, meta["title"])
        if meta.get("subtitle"):
            self.setFont("Times-Bold", 10)
            self.drawCentredString(center, y - 7 * mm, meta["subtitle"])

    def _draw_footer(self, total):
        meta = self._meta
        self.setFont("Times-Italic", 8.5)
        self.setFillColor(GREY)
        center = A4[0] / 2
        self.drawCentredString(center, 13 * mm, f"Confidential - {meta['company']}")
        self.drawCentredString(center, 9 * mm, f"Generated on {meta['generated']}")
        self.drawCentredString(center, 5 * mm, f"Page {self._pageNumber}/{total}")


def _styles():
    base = ParagraphStyle(
        "base", fontName="Times-Roman", fontSize=10, leading=13, textColor=INK
    )
    cell = ParagraphStyle("cell", parent=base, fontSize=9.5, leading=11.5)
    head = ParagraphStyle("head", parent=cell, fontName="Times-Bold", textColor=BLACK)
    bold = ParagraphStyle(
        "cell_bold", parent=cell, fontName="Times-Bold", textColor=BLACK
    )
    return {
        "base": base,
        "base_right": ParagraphStyle("base_right", parent=base, alignment=TA_RIGHT),
        "label": ParagraphStyle(
            "label", parent=base, fontName="Times-Bold", textColor=BLACK
        ),
        "heading": ParagraphStyle(
            "heading",
            parent=base,
            fontName="Times-Bold",
            fontSize=11,
            leading=14,
            textColor=BLACK,
            spaceBefore=12,
            spaceAfter=5,
        ),
        "cell": cell,
        "cell_right": ParagraphStyle("cell_right", parent=cell, alignment=TA_RIGHT),
        "cell_bold": bold,
        "cell_bold_right": ParagraphStyle(
            "cell_bold_right", parent=bold, alignment=TA_RIGHT
        ),
        "head": head,
        "head_right": ParagraphStyle("head_right", parent=head, alignment=TA_RIGHT),
        "muted": ParagraphStyle("muted", parent=base, textColor=GREY),
    }


def heading(title, styles):
    return Paragraph(f"<u>{escape(title)}</u>", styles["heading"])


def details_table(rows, styles):
    data = [
        [Paragraph(escape(a), styles["label"]), Paragraph(escape(b), styles["base"])]
        for a, b in rows
    ]
    table = Table(data, colWidths=[38 * mm, CONTENT_WIDTH - 38 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    return table


def records_style():
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE_BG]),
            ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
            ("VALIGN", (0, 1), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.6, BLACK),
            ("LINEBELOW", (0, 0), (-1, 0), 1.2, BLACK),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def amount_table(
    headers, rows, styles, widths=None, total=None, right=None, bold_rows=()
):
    ncols = len(headers)
    right = set(range(1, ncols)) if right is None else set(right)
    if widths is None:
        first = CONTENT_WIDTH * 0.6
        rest = (CONTENT_WIDTH - first) / (ncols - 1) if ncols > 1 else 0
        widths = [first] + [rest] * (ncols - 1)

    data = [
        [
            Paragraph(
                escape(text),
                styles["head_right"] if index in right else styles["head"],
            )
            for index, text in enumerate(headers)
        ]
    ]

    def build(row, bold):
        cells = []
        for index, value in enumerate(row):
            if index in right:
                style = styles["cell_bold_right"] if bold else styles["cell_right"]
            else:
                style = styles["cell_bold"] if bold else styles["cell"]
            cells.append(Paragraph(escape(str(value)), style))
        return cells

    for index, row in enumerate(rows):
        data.append(build(row, index in bold_rows))
    if total is not None:
        data.append(build(total, True))

    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = records_style()
    if total is not None:
        last = len(data) - 1
        style.add("BACKGROUND", (0, last), (-1, last), TOTAL_BG)
        style.add("LINEABOVE", (0, last), (-1, last), 1.2, BLACK)
    table.setStyle(style)
    return table


def signature_block(styles, printed):
    column = CONTENT_WIDTH / 2

    def cell(role):
        return [
            Paragraph("Signed:", styles["label"]),
            Spacer(1, 12 * mm),
            Paragraph(role, styles["label"]),
        ]

    table = Table([[cell("Prepared by"), cell("Approved by")]], colWidths=[column] * 2)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return KeepTogether(
        [
            Spacer(1, 16 * mm),
            table,
            Spacer(1, 6 * mm),
            Paragraph(
                f"<b>Date Issued:</b> {printed:%d %B}, {printed:%Y}", styles["base"]
            ),
        ]
    )


def _clip(text, width, font="Times-Roman", size=9.5):
    if stringWidth(text, font, size) <= width:
        return text
    while text and stringWidth(text + "...", font, size) > width:
        text = text[:-1]
    return text.rstrip() + "..."


def _records_table(rows, styles):
    widths = [17 * mm, 40 * mm, 55 * mm, 20 * mm, 24 * mm, 24 * mm]
    room = [w - 10 for w in widths]
    header = [
        Paragraph("Date", styles["head"]),
        Paragraph("Description", styles["head"]),
        Paragraph("Category", styles["head"]),
        Paragraph("Payment", styles["head"]),
        Paragraph("Amount", styles["head_right"]),
        Paragraph("Reference", styles["head"]),
    ]
    data = [header]
    for row in rows:
        data.append(
            [
                Paragraph(row["date"].strftime("%d/%m/%y"), styles["cell"]),
                Paragraph(escape(_clip(row["description"], room[1])), styles["cell"]),
                Paragraph(
                    escape(_clip(row["category"].upper(), room[2])), styles["cell"]
                ),
                Paragraph(escape(_clip(row["payment"], room[3])), styles["cell"]),
                Paragraph(money(row["amount"]), styles["cell_right"]),
                Paragraph(
                    escape(_clip(row["reference"] or "-", room[5])), styles["cell"]
                ),
            ]
        )

    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(records_style())
    return table


def build_pdf(story, meta, pdf_title):
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=FIRST_TOP,
        bottomMargin=FOOTER_HEIGHT,
        title=pdf_title,
        author=LAB_NAME_TITLE_CASE,
    )

    def frame(top, name):
        return Frame(
            MARGIN,
            FOOTER_HEIGHT,
            CONTENT_WIDTH,
            A4[1] - top - FOOTER_HEIGHT,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
            id=name,
        )

    doc.addPageTemplates(
        [
            PageTemplate(id="first", frames=[frame(FIRST_TOP, "first")]),
            PageTemplate(id="later", frames=[frame(LATER_TOP, "later")]),
        ]
    )
    doc.build(
        [NextPageTemplate("later"), *story],
        canvasmaker=lambda *args, **kwargs: NumberedCanvas(*args, meta=meta, **kwargs),
    )
    return buffer.getvalue()


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
    period = f"{start:%d %b %Y} TO {end:%d %b %Y}"
    meta = {
        "title": "EXPENSE REPORT",
        "subtitle": f"REPORT PERIOD: {period.upper()}",
        "company": LAB_NAME,
        "logo_path": logo_path,
        "contact_lines": tuple(contact_lines),
        "generated": f"{printed:%d %b %Y} {_clock(printed)}",
    }

    story = [
        Spacer(1, 4),
        details_table(
            [
                ("Report Period:", period),
                ("Printed:", f"{printed:%d/%m/%Y} {_clock(printed)}"),
            ],
            styles,
        ),
        heading("Expense Summary", styles),
    ]
    if data["categories"]:
        story.append(
            amount_table(
                ("Category", "Amount (TZS)", "Share"),
                [
                    (c["label"].upper(), money(c["amount"]), f"{c['percent']}%")
                    for c in data["categories"]
                ],
                styles,
                widths=[
                    CONTENT_WIDTH * 0.56,
                    CONTENT_WIDTH * 0.26,
                    CONTENT_WIDTH * 0.18,
                ],
                total=("Total Expenditure", money(data["total"]), ""),
            )
        )
    else:
        story.append(
            Paragraph("No expense categories for this period.", styles["muted"])
        )

    story.append(heading("Payments (TZS)", styles))
    if data["methods"]:
        story.append(
            amount_table(
                ("Payment Method", "Amount (TZS)"),
                [(m["label"], money(m["amount"])) for m in data["methods"]],
                styles,
                widths=[CONTENT_WIDTH * 0.7, CONTENT_WIDTH * 0.3],
                total=("Paid Total", money(data["total"])),
            )
        )
    else:
        story.append(Paragraph("No payments for this period.", styles["muted"]))

    story.append(Spacer(1, 12))
    story.append(heading("Expense Records", styles))
    if data["rows"]:
        story.append(_records_table(data["rows"], styles))
    else:
        story.append(
            Paragraph("No expenses were recorded for this period.", styles["muted"])
        )

    story.append(signature_block(styles, printed))

    return build_pdf(story, meta, f"Expense Report {start:%d %b %Y} to {end:%d %b %Y}")
