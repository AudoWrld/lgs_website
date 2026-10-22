from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

BRANCH_KWARGS = ("branch_id", "branch_pk")


def _role_required(check, message):
    def decorator(view):
        @wraps(view)
        @login_required(login_url="accounts:login")
        def wrapped(request, *args, **kwargs):
            user = request.user

            if not check(user):
                raise PermissionDenied(message)

            if not user.can_view_all_branches:
                for name in BRANCH_KWARGS:
                    requested = kwargs.get(name)
                    if requested is not None and str(requested) != str(user.branch_id):
                        raise PermissionDenied("You do not have access to this branch.")

            request.branch = user.branch
            request.accessible_branches = user.accessible_branches()

            return view(request, *args, **kwargs)

        return wrapped

    return decorator


reception_required = _role_required(
    lambda user: user.is_reception,
    "Reception access is required.",
)

chemist_required = _role_required(
    lambda user: user.is_chemist,
    "Chemist access is required.",
)

qc_required = _role_required(
    lambda user: user.is_qc,
    "Quality Control access is required.",
)

accountant_required = _role_required(
    lambda user: user.is_accountant,
    "Accountant access is required.",
)

administrator_required = _role_required(
    lambda user: user.is_administrator or user.is_superuser,
    "Administrator access is required.",
)
