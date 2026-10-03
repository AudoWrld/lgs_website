from decimal import Decimal, ROUND_HALF_UP


def quantize_half_up(value, decimals):
    if value is None:
        return None
    return Decimal(value).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def format_reportable(value, decimals):
    rounded = quantize_half_up(value, decimals)
    return "" if rounded is None else format(rounded, "f")


def decimals_for(result_type, is_carbon=False):
    if result_type in ("gold", "copper", "silver"):
        return 0 if is_carbon else 2
    return 0
