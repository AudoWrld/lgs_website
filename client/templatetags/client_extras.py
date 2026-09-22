from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def nav_active(context, *url_names):
    request = context.get("request")
    if not request:
        return ""

    match = getattr(request, "resolver_match", None)
    if not match:
        return ""

    return "active" if match.url_name in url_names else ""