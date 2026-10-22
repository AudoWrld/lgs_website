from django.conf import settings
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse


class ForcePasswordChangeMiddleware:
    exempt_url_names = (
        "accounts:force_password_change",
        "accounts:logout",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def _exempt_paths(self):
        paths = []
        for name in self.exempt_url_names:
            try:
                paths.append(reverse(name))
            except NoReverseMatch:
                continue
        for prefix in (settings.STATIC_URL, settings.MEDIA_URL):
            if prefix:
                paths.append(prefix)
        return tuple(paths)

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and getattr(user, "must_change_password", False)
            and not request.path.startswith(self._exempt_paths())
        ):
            return redirect("accounts:force_password_change")
        return self.get_response(request)
