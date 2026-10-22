from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def nav_active(context, *url_names):
    request = context.get("request")
    match = getattr(request, "resolver_match", None)
    if not match:
        return ""

    for name in url_names:
        if name.endswith(":"):
            if match.namespace == name[:-1]:
                return "active"
        elif match.url_name == name:
            return "active"
    return ""
