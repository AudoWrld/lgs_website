from django import template

register = template.Library()


@register.filter
def split_elements(value):
    if not value:
        return []
    return [e.strip() for e in value.split(",")]