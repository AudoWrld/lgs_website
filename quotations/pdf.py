import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from accountant.report_pdf import (
    FRAME_BOTTOM,
    FRAME_TOP,
    GRID,
    MARGIN_X,
    PAGE_H,
    PAGE_W,
    _draw_letterhead,
    _static_path,
    _style,
)
from coa.pdf import BLUE
from commercial.pdf import (
    NAVY,
    ORANGE,
    SIGNATURE_STATIC,
    SOFT_BLUE,
    STAMP_STATIC,
    SignatureStamp,
    _existing_static,
    _money,
    _p,
    _website,
)

ZERO = 0


def _multiline(text, **kw):
    html = "<br/>".join(escape(part) for part in str(text).splitlines())
    return Paragraph(html, _style(f"ml{abs(hash(str(kw)))}", **kw))


def _meta(quotation, width):
    rows = [
        ("QUOTATION NO.:", quotation.quotation_number),
        ("QUOTATION DATE:", f"{quotation.quotation_date:%d %B %Y}"),
        ("VALID UNTIL:", f"{quotation.valid_until:%d %B %Y}"),
    ]
    data = [
        [
            _p(label, fontName="Helvetica-Bold", fontSize=8.5, leading=11),
            _p(
                value,
                fontName="Helvetica-Bold",
                fontSize=9,
                leading=11,
                textColor=ORANGE,
            ),
        ]
        for label, value in rows
    ]
    table = Table(data, colWidths=[width * 0.2, width * 0.8])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT_BLUE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _items_table(items, width):
    head = _style(
        "qh",
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        alignment=TA_CENTER,
        textColor=colors.white,
    )
    left = _style("ql", fontSize=8, leading=10)
    sub = _style("qs", fontSize=7, leading=9, textColor=colors.HexColor("#5b666c"))
    center = _style("qc", fontSize=8, leading=10, alignment=TA_CENTER)
    right = _style("qr", fontSize=8, leading=10, alignment=TA_RIGHT)

    header = [
        "S/N",
        "Requested Service",
        "Qty / Samples",
        "Unit Price (TZS)",
        "Amount (TZS)",
    ]
    data = [[Paragraph(escape(h), head) for h in header]]
    for index, item in enumerate(items, start=1):
        service = [Paragraph(escape(item.service), left)]
        if item.description:
            service.append(Paragraph(escape(item.description), sub))
        data.append(
            [
                Paragraph(str(index), center),
                service,
                Paragraph(str(item.quantity), center),
                Paragraph(_money(item.unit_price), right),
                Paragraph(_money(item.line_total), right),
            ]
        )

    widths = [0.07, 0.43, 0.14, 0.18, 0.18]
    table = Table(data, colWidths=[width * w for w in widths], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("GRID", (0, 0), (-1, -1), 0.5, GRID),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _totals(subtotal, discount, total, width):
    label = dict(fontName="Helvetica-Bold", fontSize=8.5, leading=11)
    value = dict(
        fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=TA_RIGHT
    )
    table = Table(
        [
            [_p("SUBTOTAL (TZS)", **label), _p(_money(subtotal), **value)],
            [_p("DISCOUNT (TZS)", **label), _p(_money(discount), **value)],
            [
                _p(
                    "TOTAL QUOTED AMOUNT (TZS)",
                    fontName="Helvetica-Bold",
                    fontSize=9,
                    leading=12,
                    textColor=colors.white,
                ),
                _p(
                    _money(total),
                    fontName="Helvetica-Bold",
                    fontSize=11,
                    leading=14,
                    alignment=TA_RIGHT,
                    textColor=colors.white,
                ),
            ],
        ],
        colWidths=[width * 0.30, width * 0.16],
        hAlign="RIGHT",
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, GRID),
                ("BACKGROUND", (0, 0), (-1, 1), SOFT_BLUE),
                ("BACKGROUND", (0, 2), (-1, 2), ORANGE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _text_box(title, text, width):
    content = [
        _p(title, fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=BLUE),
        _multiline(text, fontSize=8, leading=11),
    ]
    box = Table([[content]], colWidths=[width])
    box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, GRID),
                ("BACKGROUND", (0, 0), (-1, -1), SOFT_BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return box


def _story(quotation, width):
    items = list(quotation.items.all())
    subtotal = sum((item.line_total for item in items), ZERO)
    discount = quotation.discount
    total = max(subtotal - discount, ZERO)

    title = Table(
        [
            [
                Paragraph(
                    "QUOTATION",
                    _style(
                        "qt",
                        fontName="Helvetica-Bold",
                        fontSize=18,
                        leading=22,
                        alignment=TA_CENTER,
                        textColor=colors.white,
                    ),
                )
            ]
        ],
        colWidths=[width * 0.62],
        hAlign="CENTER",
    )
    title.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), ORANGE),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    story = [
        title,
        Spacer(1, 10),
        _meta(quotation, width),
        Spacer(1, 10),
        _items_table(items, width),
        Spacer(1, 10),
        _totals(subtotal, discount, total, width),
    ]

    if quotation.terms:
        story.extend([Spacer(1, 12), _text_box("TERMS", quotation.terms, width)])
    if quotation.notes:
        story.extend([Spacer(1, 8), _text_box("NOTES", quotation.notes, width)])

    story.append(Spacer(1, 8))
    story.append(
        KeepTogether(
            [
                _p(
                    "This quotation is a proposed price only. It is not an invoice, a receipt or money collected.",
                    fontSize=8,
                    leading=11,
                    textColor=NAVY,
                ),
                Spacer(1, 10),
                SignatureStamp(
                    width,
                    quotation.quotation_date,
                    _existing_static(SIGNATURE_STATIC),
                    _existing_static(STAMP_STATIC),
                ),
            ]
        )
    )
    return story


def _build(quotation, pages_total, website):
    buf = io.BytesIO()
    width = PAGE_W - 2 * MARGIN_X
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=FRAME_TOP,
        bottomMargin=FRAME_BOTTOM,
        title=f"Quotation {quotation.quotation_number}",
        author="LGS MINERAL ASSAY LABORATORY",
    )
    frame = Frame(
        MARGIN_X,
        FRAME_BOTTOM,
        width,
        PAGE_H - FRAME_TOP - FRAME_BOTTOM,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    logo = _static_path("core/img/lgs-logo.png")

    def on_page(c, _doc):
        _draw_letterhead(c, logo, website)
        c.setStrokeColor(ORANGE)
        c.setLineWidth(0.9)
        c.line(MARGIN_X, 14 * mm, PAGE_W - MARGIN_X, 14 * mm)
        c.setFillColor(GRID)
        c.setFont("Helvetica", 7.5)
        c.drawString(
            MARGIN_X,
            10 * mm,
            "This is a system-generated quotation from LGS Mineral Assay Laboratory.",
        )
        c.drawRightString(
            PAGE_W - MARGIN_X, 10 * mm, f"Page {_doc.page} of {pages_total}"
        )

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])
    doc.build(_story(quotation, width))
    return buf.getvalue(), doc.page


def render_quotation_pdf(quotation, base_url=None):
    website = _website(base_url)
    data, pages = _build(quotation, 1, website)
    if pages != 1:
        data, _ = _build(quotation, pages, website)
    return data
