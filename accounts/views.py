from django.contrib.auth import authenticate, login, get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages

from .forms import EmailAuthenticationForm

User = get_user_model()


def login_view(request):
    if request.user.is_authenticated:
        return redirect("post_login_redirect")

    if request.method == "POST":
        form = EmailAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect("accounts:post_login_redirect")
    else:
        form = EmailAuthenticationForm(request)

    return render(request, "accounts/login.html", {"form": form})


@login_required
def post_login_redirect(request):
    user = request.user

    if user.must_change_password:
        return redirect("accounts:force_password_change")

    if user.is_customer:
        return redirect("client:customer_dashboard")
    if user.is_reception:
        return redirect("reception:reception_dashboard")
    if user.is_reception:
        return redirect("chemist:chemist_dashboard")
    if user.is_administrator or user.is_superuser:
        return redirect("administrator_dashboard")

    return redirect("login")


@login_required
def force_password_change(request):
    if not request.user.must_change_password:
        return redirect("accounts:post_login_redirect")

    if request.method == "POST":
        form = SetPasswordForm(request.user, request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.must_change_password = False
            user.initial_temp_password = form.cleaned_data["new_password1"]
            user.save()

            update_session_auth_hash(request, user)

            messages.success(request, "Your password has been updated.")
            return redirect("accounts:post_login_redirect")
    else:
        form = SetPasswordForm(request.user)

    return render(request, "accounts/force_password_change.html", {"form": form})
