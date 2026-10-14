import io
import os
from decimal import Decimal
from xml.sax.saxutils import escape

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
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
from coa.pdf import BLUE, _scaled_reader, draw_stamp
from payments.models import PaymentAccount

ORANGE = colors.HexColor("#F39A2B")
SOFT_BLUE = colors.HexColor("#EAF1F8")
NAVY = colors.HexColor("#123E5B")
SIGNATURE_STATIC = "core/img/lgs-signature.png"
STAMP_STATIC = "core/img/lgs-stamp.png"
STAMP_WIDTH = 42 * mm
MAX_HEADER_REFERENCES = 3


def _verify_base(base_url=None):
    if base_url:
        return str(base_url).rstrip("/")
    hosts = [
        h for h in settings.ALLOWED_HOSTS if h and h != "*" and not h.startswith(".")
    ]
    if settings.DEBUG or not hosts:
        return "http://127.0.0.1:8000"
    return f"https://{hosts[0]}"


def _website(base_url=None):
    base = _verify_base(base_url)
    for prefix in ("https://", "http://"):
        if base.startswith(prefix):
            return base[len(prefix) :]
    return base


class SignatureStamp(Flowable):
    def __init__(self, width, issued_at, signature_path, stamp_path):
        super().__init__()
        self.width = width
        self.issued_at = issued_at
        self.signature_path = signature_path
        self.stamp_path = stamp_path
        self.stamp_height = 0
        if stamp_path:
            iw, ih = _scaled_reader(stamp_path, 700).getSize()
            self.stamp_height = STAMP_WIDTH * ih / iw
        self.height = max(28 * mm, self.stamp_height + 2 * mm)

    def wrap(self, avail_width, avail_height):
        return self.width, self.height

    def draw(self):
        c = self.canv
        line_y = 8 * mm
        sig_x = 0
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(sig_x + 8 * mm, line_y + 14 * mm, "Laboratory Manager")
        if self.signature_path:
            c.drawImage(
                _scaled_reader(self.signature_path, 500),
                sig_x + 8 * mm,
                line_y + 0.5 * mm,
                width=34 * mm,
                height=12.5 * mm,
                preserveAspectRatio=True,
                mask="auto",
                anchor="sw",
            )
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.8)
        c.setDash(1, 2)
        c.line(sig_x, line_y, sig_x + 56 * mm, line_y)
        c.setDash()
        if self.stamp_path:
            draw_stamp(
                c,
                self.stamp_path,
                self.width - STAMP_WIDTH / 2,
                1 * mm,
                STAMP_WIDTH,
                self.issued_at,
            )


def _existing_static(relative):
    path = _static_path(relative)
    if path and os.path.exists(path):
        return path
    return ""


def _money(value):
    value = Decimal(value or 0)
    if value == value.to_integral_value():
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def _p(text, **kw):
    return Paragraph(escape(str(text)), _style(f"p{abs(hash(str(kw)))}", **kw))


def _reference_value(invoice):
    references = invoice.reference_numbers
    if len(references) > MAX_HEADER_REFERENCES:
        return f"{len(references)} references"
    return "\n".join(references)


def _bill_to(invoice, width):
    client = invoice.client
    extra = [
        getattr(client, attr)
        for attr in ("address", "phone", "email")
        if getattr(client, attr, "")
    ]
    left = [
        _p(
            "BILL TO:",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=BLUE,
        ),
        _p(
            client.client_name,
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=NAVY,
        ),
    ] + [_p(line, fontSize=8.5, leading=11) for line in extra]

    meta_rows = [
        ("CLIENT REFERENCE NO.:", _reference_value(invoice)),
        ("INVOICE NO.:", invoice.invoice_number),
        ("INVOICE DATE:", f"{invoice.invoice_date:%d %B %Y}"),
        ("PAYMENT STATUS:", invoice.payment_status),
    ]
    meta_data = []
    for label, value in meta_rows:
        value_paragraph = Paragraph(
            "<br/>".join(escape(part) for part in value.split("\n")),
            _style(
                f"mv{abs(hash(label))}",
                fontName="Helvetica-Bold",
                fontSize=8.5,
                leading=10,
                textColor=ORANGE,
            ),
        )
        meta_data.append(
            [
                _p(label, fontName="Helvetica-Bold", fontSize=8, leading=10),
                value_paragraph,
            ]
        )
    meta = Table(meta_data, colWidths=[width * 0.25, width * 0.25])
    meta.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )

    outer = Table([[left, meta]], colWidths=[width * 0.5, width * 0.5])
    outer.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, 0), SOFT_BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return outer


def _items_table(invoice, width):
    head = _style(
        "ih",
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        alignment=TA_CENTER,
        textColor=colors.white,
    )
    left = _style("il", fontSize=7.5, leading=9)
    center = _style("ic", fontSize=7.5, leading=9, alignment=TA_CENTER)
    right = _style("ir", fontSize=7.5, leading=9, alignment=TA_RIGHT)

    header = [
        "S/N",
        "Client Reference Number",
        "Description of Service",
        "Sample Type",
        "No. of Samples",
        "Unit Price (TZS)",
        "Amount (TZS)",
    ]
    data = [[Paragraph(escape(h), head) for h in header]]
    for index, line in enumerate(invoice.lines.all(), start=1):
        quantity = str(line.quantity) if line.quantity else "-"
        unit = _money(line.unit_price) if line.quantity else "-"
        data.append(
            [
                Paragraph(str(index), center),
                Paragraph(escape(line.reference), left),
                Paragraph(escape(line.description), left),
                Paragraph(escape(line.sample_type), center),
                Paragraph(quantity, center),
                Paragraph(unit, right),
                Paragraph(_money(line.amount), right),
            ]
        )

    widths = [0.06, 0.17, 0.30, 0.11, 0.09, 0.13, 0.14]
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


def _account_label(account):
    if account.bank_name:
        return account.bank_name
    return dict(PaymentAccount.ACCOUNT_TYPE_CHOICES).get(
        account.account_type, "Account"
    )


def _payment_and_totals(invoice, width):
    accounts = list(PaymentAccount.objects.filter(is_active=True))
    names = []
    for account in accounts:
        if account.account_name not in names:
            names.append(account.account_name)

    details = [
        _p(
            "PAYMENT DETAILS",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=BLUE,
        )
    ]
    if names:
        details.append(
            _p(
                f"Account Name: {', '.join(names)}",
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=11,
            )
        )
    for account in accounts:
        details.append(
            _p(
                f"{_account_label(account)}: {account.account_number}",
                fontSize=8,
                leading=11,
            )
        )

    label_style = dict(fontName="Helvetica-Bold", fontSize=8.5, leading=11)
    value_style = dict(
        fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=TA_RIGHT
    )
    totals = Table(
        [
            [
                _p("TOTAL CHARGES (TZS)", **label_style),
                _p(_money(invoice.total_charges), **value_style),
            ],
            [
                _p("AMOUNT PAID (TZS)", **label_style),
                _p(_money(invoice.amount_paid), **value_style),
            ],
            [
                _p(
                    "OUTSTANDING BALANCE (TZS)",
                    fontName="Helvetica-Bold",
                    fontSize=9,
                    leading=12,
                    textColor=colors.white,
                ),
                _p(
                    _money(invoice.outstanding_balance),
                    fontName="Helvetica-Bold",
                    fontSize=11,
                    leading=14,
                    alignment=TA_RIGHT,
                    textColor=colors.white,
                ),
            ],
        ],
        colWidths=[width * 0.28, width * 0.16],
    )
    totals.setStyle(
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

    outer = Table(
        [[details, "", totals]],
        colWidths=[width * 0.50, width * 0.04, width * 0.46],
    )
    outer.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (0, 0), 0.5, GRID),
                ("BACKGROUND", (0, 0), (0, 0), SOFT_BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return outer


def _remarks(width):
    items = [
        _p(
            "PAYMENT REMARKS",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=BLUE,
        ),
        _p(
            "\u2022 This invoice is for laboratory services already completed under the above Client Reference Number(s).",
            fontSize=8,
            leading=11,
        ),
        _p(
            "\u2022 Please quote the Invoice Number or Client Reference Number when making payment.",
            fontSize=8,
            leading=11,
        ),
        _p(
            "\u2022 For any payment enquiries, please contact the laboratory through the provided email or phone number.",
            fontSize=8,
            leading=11,
        ),
    ]
    box = Table([[items]], colWidths=[width])
    box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, GRID),
                ("BACKGROUND", (0, 0), (-1, -1), SOFT_BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return box


def _story(invoice, width):
    title = Table(
        [
            [
                Paragraph(
                    "COMMERCIAL INVOICE",
                    _style(
                        "ct",
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

    return [
        title,
        Spacer(1, 10),
        _bill_to(invoice, width),
        Spacer(1, 10),
        _items_table(invoice, width),
        Spacer(1, 12),
        KeepTogether(
            [
                _payment_and_totals(invoice, width),
                Spacer(1, 12),
                _remarks(width),
                Spacer(1, 10),
                SignatureStamp(
                    width,
                    invoice.invoice_date,
                    _existing_static(SIGNATURE_STATIC),
                    _existing_static(STAMP_STATIC),
                ),
            ]
        ),
    ]


def _build(invoice, pages_total, website):
    buf = io.BytesIO()
    width = PAGE_W - 2 * MARGIN_X
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=FRAME_TOP,
        bottomMargin=FRAME_BOTTOM,
        title=f"Commercial Invoice {invoice.invoice_number}",
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
            "This is a system-generated commercial invoice from LGS Mineral Assay Laboratory.",
        )
        c.drawRightString(
            PAGE_W - MARGIN_X, 10 * mm, f"Page {_doc.page} of {pages_total}"
        )

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])
    doc.build(_story(invoice, width))
    return buf.getvalue(), doc.page


def render_invoice_pdf(invoice, base_url=None):
    website = _website(base_url)
    data, pages = _build(invoice, 1, website)
    if pages != 1:
        data, _ = _build(invoice, pages, website)
    return data
