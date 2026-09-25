from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def nav_active(context, *url_names):
    request = context.get("request")
    if not request or not request.resolver_match:
        return ""
    return "active" if request.resolver_match.url_name in url_names else ""