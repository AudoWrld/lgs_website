from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def nav_active(context, *url_names):
    request = context.get("request")
    match = getattr(request, "resolver_match", None)
    if match and match.url_name in url_names:
        return "active"
    return ""