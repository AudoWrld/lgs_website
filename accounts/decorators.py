from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from functools import wraps


def reception_required(view):
    @wraps(view)
    @login_required(login_url="accounts:login")
    def wrapped(request, *args, **kwargs):
        if not request.user.is_reception:
            raise PermissionDenied("Reception access is required.")
        return view(request, *args, **kwargs)

    return wrapped


def chemist_required(view):
    @wraps(view)
    @login_required(login_url="accounts:login")
    def wrapped(request, *args, **kwargs):
        if not request.user.is_chemist:
            raise PermissionDenied("Chemist access is required.")
        return view(request, *args, **kwargs)

    return wrapped
