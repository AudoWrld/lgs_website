from django.contrib import messages
from django.contrib.auth import (
    get_user_model,
    login,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import EmailAuthenticationForm
from .models import EmployeeActivity

User = get_user_model()

NEXT_SESSION_KEY = "post_login_next"
PASSWORD_CHANGED_ACTION = "PASSWORD_CHANGED"


def _safe_next(request, target):
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return None


def login_view(request):
    requested = request.POST.get("next") or request.GET.get("next")
    safe = _safe_next(request, requested)

    if request.user.is_authenticated:
        if safe:
            request.session[NEXT_SESSION_KEY] = safe
        return redirect("accounts:post_login_redirect")

    if request.method == "POST":
        form = EmailAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if user.is_staff_role:
                EmployeeActivity.objects.create(
                    employee=user,
                    actor=user,
                    action=EmployeeActivity.LOGIN,
                    detail=f"Signed in from {request.get_meta('HTTP_USER_AGENT', 'unknown')[:200]}.",
                )
            if safe:
                request.session[NEXT_SESSION_KEY] = safe
            return redirect("accounts:post_login_redirect")
    else:
        form = EmailAuthenticationForm(request)

    return render(
        request,
        "accounts/login.html",
        {"form": form, "next": safe or ""},
    )


@login_required
def post_login_redirect(request):
    user = request.user

    if user.must_change_password:
        return redirect("accounts:force_password_change")

    stored = request.session.pop(NEXT_SESSION_KEY, None)
    target = _safe_next(request, stored)
    if target:
        return redirect(target)

    if user.is_customer:
        return redirect("client:customer_dashboard")
    if user.is_reception:
        return redirect("reception:reception_dashboard")
    if user.is_chemist:
        return redirect("chemist:chemist_dashboard")
    if user.is_qc:
        return redirect("qc:qc_dashboard")
    if user.is_accountant:
        return redirect("accountant:dashboard")
    if user.is_administrator or user.is_superuser:
        return redirect("administrator:admin_dashboard")

    return redirect("accounts:login")


@login_required
def force_password_change(request):
    if not request.user.must_change_password:
        return redirect("accounts:post_login_redirect")

    if request.method == "POST":
        form = SetPasswordForm(request.user, request.POST)
        if form.is_valid():
            new_password = form.cleaned_data["new_password1"]
            if request.user.check_password(new_password):
                form.add_error(
                    "new_password1",
                    "Choose a password different from your temporary password.",
                )
            else:
                user = form.save(commit=False)
                user.must_change_password = False
                user.initial_temp_password = None
                with transaction.atomic():
                    user.save()
                    if user.is_staff_role:
                        EmployeeActivity.objects.create(
                            employee=user,
                            actor=user,
                            action=PASSWORD_CHANGED_ACTION,
                            detail="Replaced their temporary password with a new one.",
                        )

                update_session_auth_hash(request, user)

                messages.success(request, "Your password has been updated.")
                return redirect("accounts:post_login_redirect")
    else:
        form = SetPasswordForm(request.user)

    return render(request, "accounts/force_password_change.html", {"form": form})
