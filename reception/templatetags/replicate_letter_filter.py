import string
from django import template

register = template.Library()


@register.filter
def split_elements(value):
    if not value:
        return []
    return [el.strip() for el in value.split(",") if el.strip()]


@register.filter
def replicate_letter(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return ""
    if n < 1:
        return ""
    letters = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        letters = string.ascii_uppercase[remainder] + letters
    return letters
