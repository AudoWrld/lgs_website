from xml.sax.saxutils import escape

from reportlab.lib.units import mm
from reportlab.platypus import CondPageBreak, Paragraph, Spacer, Table, TableStyle

from .expense_pdf import (
    CONTENT_WIDTH,
    _clip,
    _clock,
    _styles,
    build_pdf,
    details_table,
    heading,
    money,
    records_style,
    signature_block,
)

TITLE = "FINANCIAL REPORT"


def _grid(cells, styles, label_width, columns):
    cells = list(cells)
    while len(cells) % columns:
        cells.append(("", None))

    rows = []
    for i in range(0, len(cells), columns):
        row = []
        for label, amount in cells[i : i + columns]:
            row.append(Paragraph(escape(label), styles["base"]) if label else "")
            row.append(
                Paragraph(money(amount), styles["base_right"])
                if amount is not None
                else ""
            )
        rows.append(row)

    pair = CONTENT_WIDTH / columns
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for column in range(columns):
        commands.append(("RIGHTPADDING", (column * 2 + 1, 0), (column * 2 + 1, -1), 8))

    table = Table(
        rows,
        colWidths=[label_width, pair - label_width] * columns,
        hAlign="LEFT",
    )
    table.setStyle(TableStyle(commands))
    return table


def _records(headers, widths, rows, right_columns, styles):
    room = [width - 8 for width in widths]
    data = [
        [
            Paragraph(
                text, styles["head_right"] if index in right_columns else styles["head"]
            )
            for index, text in enumerate(headers)
        ]
    ]
    for row in rows:
        cells = []
        for index, value in enumerate(row):
            if index in right_columns:
                cells.append(Paragraph(escape(value), styles["cell_right"]))
            else:
                cells.append(
                    Paragraph(escape(_clip(value, room[index])), styles["cell"])
                )
        data.append(cells)

    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(records_style())
    return table


def _section(title, styles):
    return [CondPageBreak(35 * mm), heading(title, styles)]


def _dash(value):
    return value if value else "-"


def render_financial_pdf(
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
        "title": TITLE,
        "subtitle": f"REPORT PERIOD: {period.upper()}",
        "company": company,
        "logo_path": logo_path,
        "contact_lines": tuple(contact_lines),
        "generated": f"{printed:%d %b %Y} {_clock(printed)}",
    }

    as_of = f"as of {printed:%d %b %Y}"

    story = [
        Spacer(1, 4),
        details_table(
            [
                ("Report Period:", period),
                ("Printed:", f"{printed:%d/%m/%Y} {_clock(printed)}"),
            ],
            styles,
        ),
        *_section("Summary (TZS)", styles),
        _grid(
            [
                ("Payments Collected:", data["payments_total"]),
                ("Expenses:", data["expenses_total"]),
                ("Net Income:", data["net_total"]),
                ("Outstanding Debt:", data["outstanding_debt"]),
                ("Credit Outstanding:", data["credit_outstanding"]),
            ],
            styles,
            40 * mm,
            2,
        ),
    ]

    channels = [(f"{c['label']}:", c["amount"]) for c in data["channels"]]
    while len(channels) % 3 != 2:
        channels.append(("", None))
    channels.append(("Total:", data["payments_total"]))
    story.extend(_section("Collections by Channel (TZS)", styles))
    story.append(_grid(channels, styles, 22 * mm, 3))

    story.extend(_section("Payments Collected", styles))
    if data["payments"]:
        story.append(
            _records(
                ("Date", "Reference No.", "Method", "Amount (TZS)"),
                [30 * mm, 56 * mm, 42 * mm, 52 * mm],
                [
                    (
                        row["date"].strftime("%d/%m/%y %H:%M"),
                        row["reference"],
                        row["method"],
                        money(row["amount"]),
                    )
                    for row in data["payments"]
                ],
                {3},
                styles,
            )
        )
    else:
        story.append(
            Paragraph("No payments collected in this period.", styles["muted"])
        )

    story.extend(_section("Expenses", styles))
    if data["expenses"]:
        story.append(
            _records(
                ("Date", "Category", "Description", "Amount (TZS)"),
                [16 * mm, 62 * mm, 72 * mm, 30 * mm],
                [
                    (
                        row["date"].strftime("%d/%m/%y"),
                        row["category"].upper(),
                        row["description"],
                        money(row["amount"]),
                    )
                    for row in data["expenses"]
                ],
                {3},
                styles,
            )
        )
    else:
        story.append(Paragraph("No expenses recorded in this period.", styles["muted"]))

    story.extend(_section(f"Credit Outstanding ({as_of})", styles))
    if data["credit"]:
        story.append(
            _records(
                ("Reference No.", "Outstanding (TZS)", "Due Date", "Status"),
                [56 * mm, 44 * mm, 34 * mm, 46 * mm],
                [
                    (
                        row["reference"],
                        money(row["outstanding"]),
                        (
                            row["due_date"].strftime("%d/%m/%y")
                            if row["due_date"]
                            else "-"
                        ),
                        _dash(row["status"]),
                    )
                    for row in data["credit"]
                ],
                {1},
                styles,
            )
        )
    else:
        story.append(Paragraph("No credit outstanding.", styles["muted"]))

    story.extend(_section(f"Outstanding Debt ({as_of})", styles))
    if data["debt"]:
        story.append(
            _records(
                (
                    "Reference No.",
                    "Amount Due (TZS)",
                    "Amount Paid (TZS)",
                    "Outstanding (TZS)",
                ),
                [56 * mm, 41 * mm, 41 * mm, 42 * mm],
                [
                    (
                        row["reference"],
                        money(row["due"]),
                        money(row["paid"]),
                        money(row["outstanding"]),
                    )
                    for row in data["debt"]
                ],
                {1, 2, 3},
                styles,
            )
        )
    else:
        story.append(Paragraph("No outstanding debt.", styles["muted"]))

    story.append(signature_block(styles, printed))

    return build_pdf(
        story, meta, f"Financial Report {start:%d %b %Y} to {end:%d %b %Y}", company
    )
