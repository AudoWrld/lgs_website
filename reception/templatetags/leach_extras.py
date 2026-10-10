from django import template

register = template.Library()

SPECIAL_ROW_TYPES = ("BLANK", "CRM")


def _sample_key(row):
    mapping = getattr(row, "lab_sample_mapping", None)
    return getattr(mapping, "lab_sample_id", None)


@register.filter
def collapse_sample_ids(rows):
    rows = list(rows)
    grouped = []
    index = 0
    while index < len(rows):
        row = rows[index]
        if row.row_type in SPECIAL_ROW_TYPES:
            grouped.append({"row": row, "span": 1, "show": True})
            index += 1
            continue
        key = _sample_key(row)
        end = index + 1
        while (
            end < len(rows)
            and rows[end].row_type not in SPECIAL_ROW_TYPES
            and _sample_key(rows[end]) == key
        ):
            end += 1
        span = end - index
        for position in range(index, end):
            grouped.append(
                {"row": rows[position], "span": span, "show": position == index}
            )
        index = end
    return grouped
